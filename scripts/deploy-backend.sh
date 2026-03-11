#!/usr/bin/env bash
set -euo pipefail

BASE="/opt/socratestenis"
REPO="$BASE/repos/backend"
BRANCH="main"
LOG="$BASE/logs/deploy-backend.log"

HEALTH_URL="http://127.0.0.1:5000/api/v1/health"
REQ_FILE="$REPO/requirements.txt"
REQ_HASH_FILE="$BASE/.last_requirements_hash"

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "=============================="
echo "[DEPLOY BACKEND] $(date -Is)"
echo "=============================="

# evita 2 deploys ao mesmo tempo
exec 9>/tmp/deploy-backend.lock
flock -n 9 || { echo "[INFO] Deploy já em execução. Saindo."; exit 0; }

fail() {
  echo "[ERRO] $1"
  echo "[ERRO] Últimas linhas do log da API:"
  cd "$BASE" && docker compose logs --tail=80 api || true
  exit 1
}

echo "[1/5] Atualizando código (git)..."
cd "$REPO"
git fetch --prune origin
git reset --hard "origin/$BRANCH"
git clean -fd

# Se requirements.txt mudou, força build sem cache
NEW_HASH="$(sha256sum "$REQ_FILE" | awk '{print $1}')"
OLD_HASH="$(cat "$REQ_HASH_FILE" 2>/dev/null || echo '')"

NO_CACHE_FLAG=""
if [[ "$NEW_HASH" != "$OLD_HASH" ]]; then
  echo "[INFO] requirements.txt mudou → build --no-cache"
  NO_CACHE_FLAG="--no-cache"
  echo "$NEW_HASH" > "$REQ_HASH_FILE"
else
  echo "[INFO] requirements.txt não mudou → build com cache normal"
fi

echo "[2/5] Build da imagem do serviço api..."
cd "$BASE"
# shellcheck disable=SC2086
docker compose build --pull $NO_CACHE_FLAG api || fail "Falha no build da imagem da API."

echo "[3/5] Subindo api (sem derrubar dependências)..."
docker compose up -d --no-deps api || fail "Falha ao subir o container da API."

echo "[4/5] Aguardando container da API ficar disponível..."
for i in {1..20}; do
  if docker compose exec -T api sh -lc 'exit 0' >/dev/null 2>&1; then
    echo "[INFO] Container da API disponível."
    break
  fi

  if [[ "$i" -eq 20 ]]; then
    fail "Container da API não ficou disponível a tempo."
  fi

  sleep 2
done

echo "[5/5] Aplicando migrations..."
docker compose exec -T api alembic upgrade head || fail "Falha ao aplicar migrations com Alembic."

echo "[CHECK] Validando health..."
for i in {1..30}; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[CHECK] OK"
    echo "[OK] Status:"
    docker compose ps
    exit 0
  fi

  if [[ "$i" -eq 30 ]]; then
    fail "Health check falhou após aplicar migrations."
  fi

  sleep 2
done
