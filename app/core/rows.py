"""Conversion typée des lignes JSON renvoyées par Supabase (PostgREST)."""

from datetime import date
from decimal import Decimal

JsonValue = str | int | float | bool | None
Row = dict[str, JsonValue]


def as_int(value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError(f"Entier attendu, reçu {value!r}")
    return int(value)


def as_str(value: JsonValue) -> str:
    if not isinstance(value, str):
        raise TypeError(f"Texte attendu, reçu {value!r}")
    return value


def as_decimal(value: JsonValue) -> Decimal:
    if value is None or isinstance(value, bool):
        raise TypeError(f"Nombre attendu, reçu {value!r}")
    # Passer par str() évite les artefacts binaires des float (0.1 → 0.1000000000000000055…).
    return Decimal(str(value))


def as_optional_decimal(value: JsonValue) -> Decimal | None:
    return None if value is None else as_decimal(value)


def as_date(value: JsonValue) -> date:
    return date.fromisoformat(as_str(value))


def as_optional_date(value: JsonValue) -> date | None:
    return None if value is None else as_date(value)
