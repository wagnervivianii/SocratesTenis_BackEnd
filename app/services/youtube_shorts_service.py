from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from cachetools import TTLCache

SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")

# ✅ Cache 1h: a mesma “palavra da hora” reaproveita resultados
_cache = TTLCache(maxsize=64, ttl=3600)

# ✅ Lista inicial de palavras (a gente ajusta depois com base no resultado)
KEYWORDS: list[str] = [
    # PT
    "saque tenis",
    "voleio tenis",
    "forehand tenis",
    "backhand tenis",
    "slice tenis",
    "topspin tenis",
    "footwork tenis",
    "split step tenis",
    "devolucao de saque tenis",
    "movimentacao lateral tenis",
    # EN (melhora muito a qualidade)
    "tennis serve drill shorts",
    "tennis volley drill shorts",
    "tennis footwork drill shorts",
    "tennis return drill shorts",
]

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)


def parse_iso8601_duration_to_seconds(duration: str) -> int | None:
    """
    Ex: PT1M32S, PT45S, PT2M, PT1H2M (não esperado aqui, mas tratamos)
    """
    if not duration:
        return None
    m = _DURATION_RE.match(duration.strip())
    if not m:
        return None

    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def keyword_of_the_hour(now: datetime | None = None) -> str:
    """
    Palavra determinística por hora (SP). Assim:
    - cache funciona
    - todos veem o mesmo “tema da hora”
    """
    if now is None:
        now = datetime.now(tz=SAO_PAULO_TZ)
    hour_index = now.year * 1000000 + now.month * 10000 + now.day * 100 + now.hour
    return KEYWORDS[hour_index % len(KEYWORDS)]


def _pick_thumb(snippet: dict[str, Any]) -> str | None:
    thumbs = (snippet or {}).get("thumbnails") or {}
    # tenta qualidade melhor primeiro, cai para default
    for key in ("maxres", "standard", "high", "medium", "default"):
        u = thumbs.get(key, {}).get("url")
        if u and u.startswith("https://"):
            return u
    return None


@dataclass
class YoutubeConfig:
    api_key: str
    region_code: str = "BR"
    relevance_language: str = "pt"
    safe_search: str = "strict"  # "moderate" se ficar restritivo demais
    max_results: int = 25


def _get_config() -> YoutubeConfig:
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY não configurada no ambiente.")
    return YoutubeConfig(api_key=api_key)


def _is_syndicable_embed(cfg: YoutubeConfig, v: dict[str, Any]) -> bool:
    """
    Filtros para reduzir vídeos que falham no iframe (Erro 153 / embed bloqueado).
    Além de status.embeddable, o grande diferencial é buscar vídeos "syndicated"
    (via search.videoSyndicated=true) e validar informações do player quando existirem.

    Regras:
    - status.embeddable precisa ser True
    - status.privacyStatus precisa ser public
    - age restricted costuma falhar em embed
    - regionRestriction (quando existir) não pode bloquear o region_code
    - player.embedHtml (quando disponível) deve existir
    """
    status = v.get("status") or {}
    if status.get("embeddable") is not True:
        return False

    privacy = (status.get("privacyStatus") or "").lower()
    if privacy and privacy != "public":
        return False

    content = v.get("contentDetails") or {}

    # age restriction tende a quebrar embed / exigir login
    content_rating = content.get("contentRating") or {}
    if content_rating.get("ytRating") == "ytAgeRestricted":
        return False

    rr = content.get("regionRestriction") or {}
    blocked = rr.get("blocked") or []
    if isinstance(blocked, list) and cfg.region_code in blocked:
        return False

    allowed = rr.get("allowed") or []
    if isinstance(allowed, list) and allowed and (cfg.region_code not in allowed):
        return False

    # Quando pedimos part=player, alguns vídeos não trazem embedHtml.
    # Se não vier, descartamos (mais conservador, porém reduz erros).
    player = v.get("player") or {}
    embed_html = (player.get("embedHtml") or "").strip()
    if not embed_html:
        return False

    return True


async def _search_videos(client: httpx.AsyncClient, cfg: YoutubeConfig, query: str) -> list[str]:
    """
    Busca IDs de vídeos curtos e incorporáveis.
    Atenção: não existe filtro perfeito de Shorts, então buscamos curto e filtramos por duração depois.
    """
    params = {
        "key": cfg.api_key,
        "part": "snippet",
        "type": "video",
        "q": query,
        "maxResults": cfg.max_results,
        "safeSearch": cfg.safe_search,
        "videoDuration": "short",
        "regionCode": cfg.region_code,
        "relevanceLanguage": cfg.relevance_language,
        "order": "relevance",
        # ✅ já filtra embed no SEARCH (ajuda)
        "videoEmbeddable": "true",
        # ✅ MUITO importante: força vídeos que podem tocar fora do youtube.com
        # (reduz drasticamente erro 153)
        "videoSyndicated": "true",
    }

    r = await client.get(YOUTUBE_SEARCH_URL, params=params)
    r.raise_for_status()
    data = r.json()

    ids: list[str] = []
    for item in data.get("items", []):
        vid = (((item or {}).get("id") or {}).get("videoId")) or None
        if vid:
            ids.append(vid)

    # dedup preservando ordem
    seen = set()
    out = []
    for vid in ids:
        if vid not in seen:
            seen.add(vid)
            out.append(vid)

    return out


async def _fetch_video_details(
    client: httpx.AsyncClient, cfg: YoutubeConfig, video_ids: list[str]
) -> list[dict[str, Any]]:
    if not video_ids:
        return []

    # ✅ pedimos player também para validar embedHtml
    params = {
        "key": cfg.api_key,
        "part": "snippet,contentDetails,status,player",
        "id": ",".join(video_ids[:50]),
        "maxResults": 50,
    }
    r = await client.get(YOUTUBE_VIDEOS_URL, params=params)
    r.raise_for_status()
    data = r.json()
    return data.get("items", []) or []


def _build_item(keyword: str, v: dict[str, Any]) -> dict[str, Any] | None:
    vid = v.get("id")
    if not vid:
        return None

    snippet = v.get("snippet") or {}
    content = v.get("contentDetails") or {}

    title = (snippet.get("title") or "").strip()
    channel = (snippet.get("channelTitle") or "").strip()

    published_at_raw = snippet.get("publishedAt")
    published_at = None
    if published_at_raw:
        try:
            published_at = datetime.fromisoformat(
                published_at_raw.replace("Z", "+00:00")
            ).astimezone(UTC)
        except Exception:
            published_at = None

    dur = content.get("duration") or ""
    duration_seconds = parse_iso8601_duration_to_seconds(dur)

    # ✅ filtro forte pra manter padrão "Shorts-like"
    if duration_seconds is None:
        return None
    if duration_seconds > 180:
        return None

    thumb = _pick_thumb(snippet)

    watch_url = f"https://www.youtube.com/watch?v={vid}"
    # ✅ embed padrão (mais compatível que nocookie em muitos cenários)
    embed_url = f"https://www.youtube.com/embed/{vid}"

    return {
        "keyword": keyword,
        "video_id": vid,
        "title": title[:160],
        "channel": channel[:120],
        "published_at": published_at,
        "thumb": thumb,
        "watch_url": watch_url,
        "embed_url": embed_url,
        "duration_seconds": duration_seconds,
    }


async def get_shorts_for_keyword(keyword: str, limit: int = 8) -> dict[str, Any]:
    keyword = (keyword or "").strip()
    if not keyword:
        keyword = keyword_of_the_hour()

    # ✅ versão do cache (mude ao alterar lógica / embed)
    cache_key = f"k:{keyword}:v3"
    if cache_key in _cache:
        cached = _cache[cache_key]
        return {
            "keyword": cached["keyword"],
            "updated_at": datetime.now(tz=UTC),
            "items": cached["items"][:limit],
        }

    cfg = _get_config()

    # ✅ aumenta o pool pra compensar filtros (syndicated/embeddable/player/duração)
    cfg.max_results = min(50, max(cfg.max_results, limit * 8))

    headers = {
        "User-Agent": "SocratesTenisShorts/1.0",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
        video_ids = await _search_videos(client, cfg, query=keyword)
        details = await _fetch_video_details(client, cfg, video_ids)

    items: list[dict[str, Any]] = []

    for v in details:
        if not _is_syndicable_embed(cfg, v):
            continue

        item = _build_item(keyword, v)
        if item:
            items.append(item)

        if len(items) >= limit:
            break

    payload = {
        "keyword": keyword,
        "updated_at": datetime.now(tz=UTC),
        "items": items,
    }
    _cache[cache_key] = payload
    return payload


async def get_shorts_of_the_hour(limit: int = 8) -> dict[str, Any]:
    kw = keyword_of_the_hour()
    return await get_shorts_for_keyword(kw, limit=limit)
