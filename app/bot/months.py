"""Noms de mois en français : affichage et lecture d'une date « mois + année »."""

import re
import unicodedata
from datetime import date

MONTH_NAMES = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
_ABBREVIATIONS = [
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
]
_MAX_YEARS_AHEAD = 50
_NUMERIC = re.compile(r"^(\d{1,2})\s*[/\-. ]\s*(\d{2}|\d{4})$")


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char)).strip(" .")


_MONTH_BY_PLAIN_NAME = {_plain(name): index + 1 for index, name in enumerate(MONTH_NAMES)} | {
    _plain(abbr): index + 1 for index, abbr in enumerate(_ABBREVIATIONS)
}


def month_name(month: date) -> str:
    return f"{MONTH_NAMES[month.month - 1]} {month.year}"


def month_abbr(number: int) -> str:
    return _ABBREVIATIONS[number - 1]


def of_month(month: date) -> str:
    """« de novembre 2026 », « d'avril 2027 »."""
    name = month_name(month)
    return f"d'{name}" if name[0] in "aeiou" else f"de {name}"


def parse_future_month(text: str, current_month: date) -> date | None:
    """Lit « 06/2027 », « 6/27 », « juin 2027 » ou « juin » (prochain juin). None si invalide ou passé."""
    cleaned = text.strip()
    numeric = _NUMERIC.match(cleaned)
    if numeric is not None:
        month_number, year = int(numeric.group(1)), int(numeric.group(2))
        year += 2000 if year < 100 else 0
    else:
        words = cleaned.split()
        if not words or len(words) > 2:
            return None
        found = _MONTH_BY_PLAIN_NAME.get(_plain(words[0]))
        if found is None:
            return None
        month_number = found
        if len(words) == 2:
            if not words[1].isdigit():
                return None
            year = int(words[1])
        else:
            year = current_month.year if month_number >= current_month.month else current_month.year + 1
    if not 1 <= month_number <= 12 or not current_month.year <= year <= current_month.year + _MAX_YEARS_AHEAD:
        return None
    result = date(year, month_number, 1)
    return result if result >= current_month else None
