"""Lecture et affichage des montants au format français (1 250,50 €)."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CENT = Decimal("0.01")
# numeric(12,2) en base : au-delà, l'insertion échouerait.
_LIMIT = Decimal("1e10")
_IGNORED_CHARS = str.maketrans("", "", "   €")


def parse_amount(text: str) -> Decimal | None:
    """Accepte « 1250,50 », « 1 250.50 € », « -80 ». Renvoie None si ce n'est pas un montant."""
    cleaned = text.translate(_IGNORED_CHARS).replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite() or abs(value) >= _LIMIT:
        return None
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def format_eur(value: Decimal, *, signed: bool = False) -> str:
    rounded = value.quantize(_CENT, rounding=ROUND_HALF_UP)
    if rounded < 0:
        sign = "-"
    elif signed and rounded > 0:
        sign = "+"
    else:
        sign = ""
    digits = f"{abs(rounded):,.2f}".replace(",", " ").replace(".", ",")
    return f"{sign}{digits} €"
