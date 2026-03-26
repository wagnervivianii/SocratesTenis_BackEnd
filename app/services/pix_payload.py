from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

_PIX_GUI = "br.gov.bcb.pix"
_CURRENCY_BRL = "986"
_COUNTRY_CODE_BR = "BR"
_CRC_POLY = 0x1021
_CRC_INIT = 0xFFFF
_TXID_FALLBACK = "***"
_TXID_ALLOWED = re.compile(r"^[A-Za-z0-9]{1,25}$")


class PixPayloadError(ValueError):
    """Raised when Pix payload input data is invalid."""


def _only_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _normalize_spaces(value: str) -> str:
    return " ".join(value.split())


def _normalize_text(
    value: str, *, field_name: str, max_length: int, uppercase: bool = False
) -> str:
    cleaned = _normalize_spaces(_only_ascii(value).strip())
    if uppercase:
        cleaned = cleaned.upper()
    if not cleaned:
        raise PixPayloadError(f"{field_name} nao pode ficar vazio.")
    return cleaned[:max_length]


def _normalize_pix_key(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise PixPayloadError("A chave Pix nao pode ficar vazia.")
    if len(cleaned) > 77:
        raise PixPayloadError("A chave Pix nao pode ter mais de 77 caracteres.")
    return cleaned


def _normalize_amount(value: Decimal | float | int | str | None) -> str | None:
    if value is None:
        return None
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise PixPayloadError("O valor do Pix deve ser maior que zero.")
    return f"{amount:.2f}"


def _normalize_txid(value: str | None) -> str:
    if not value:
        return _TXID_FALLBACK
    cleaned = value.strip()
    if cleaned == _TXID_FALLBACK:
        return cleaned
    if not _TXID_ALLOWED.fullmatch(cleaned):
        raise PixPayloadError(
            "O txid do QR Code estatico deve conter apenas letras e numeros, com ate 25 caracteres."
        )
    return cleaned


def _field(field_id: str, value: str) -> str:
    size = len(value)
    if size > 99:
        raise PixPayloadError(
            f"O campo {field_id} excedeu o tamanho maximo permitido pelo BR Code."
        )
    return f"{field_id}{size:02d}{value}"


def _merchant_account_information(*, pix_key: str) -> str:
    payload = "".join(
        [
            _field("00", _PIX_GUI),
            _field("01", pix_key),
        ]
    )
    return _field("26", payload)


def _additional_data_field(*, txid: str) -> str:
    return _field("62", _field("05", txid))


def _crc16_ccitt_false(data: str) -> str:
    crc = _CRC_INIT
    for byte in data.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _CRC_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def generate_pix_payload(
    *,
    pix_key: str,
    merchant_name: str,
    merchant_city: str,
    amount: Decimal | float | int | str | None = None,
    txid: str | None = None,
) -> str:
    """Generate a static Pix BR Code payload.

    The resulting string can be rendered as a QR Code or offered as a
    copy-and-paste Pix code.
    """

    normalized_key = _normalize_pix_key(pix_key)
    normalized_name = _normalize_text(
        merchant_name,
        field_name="merchant_name",
        max_length=25,
    )
    normalized_city = _normalize_text(
        merchant_city,
        field_name="merchant_city",
        max_length=15,
        uppercase=True,
    )
    normalized_amount = _normalize_amount(amount)
    normalized_txid = _normalize_txid(txid)

    parts = [
        _field("00", "01"),
        _merchant_account_information(pix_key=normalized_key),
        _field("52", "0000"),
        _field("53", _CURRENCY_BRL),
    ]

    if normalized_amount is not None:
        parts.append(_field("54", normalized_amount))

    parts.extend(
        [
            _field("58", _COUNTRY_CODE_BR),
            _field("59", normalized_name),
            _field("60", normalized_city),
            _additional_data_field(txid=normalized_txid),
        ]
    )

    without_crc = "".join(parts) + "6304"
    crc = _crc16_ccitt_false(without_crc)
    return without_crc + crc


def generate_pix_copy_and_paste(
    *,
    pix_key: str,
    merchant_name: str,
    merchant_city: str,
    amount: Decimal | float | int | str | None = None,
    txid: str | None = None,
) -> str:
    return generate_pix_payload(
        pix_key=pix_key,
        merchant_name=merchant_name,
        merchant_city=merchant_city,
        amount=amount,
        txid=txid,
    )
