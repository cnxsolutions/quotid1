import re
from datetime import date, timedelta

CATEGORIES = ["Food", "Transport", "Logement", "Business", "Charges", "Abonnement", "Loisir", "Santé", "Autre"]
_CATEGORIES_LOWER = {c.lower(): c for c in CATEGORIES}
_CATEGORIES_HINT = ", ".join(CATEGORIES)


def normalize_category(raw: str) -> str | None:
    return _CATEGORIES_LOWER.get(raw.strip().lower())


def parse_account_tag(text: str) -> tuple[str, str | None]:
    pattern = re.compile(r'\s*\bcompte:(\S+)', re.IGNORECASE)
    match = pattern.search(text)
    if match:
        account_name = match.group(1).lower()
        clean_text = pattern.sub("", text).strip()
        return clean_text, account_name
    return text, None


def parse_category_tag(text: str) -> tuple[str, str | None]:
    pattern = re.compile(r'\s*\bcat:(\S+)', re.IGNORECASE)
    match = pattern.search(text)
    if match:
        raw = match.group(1)
        clean_text = pattern.sub("", text).strip()
        category = normalize_category(raw)
        if category is None:
            raise ValueError(f"Catégorie inconnue : '{raw}'\nAutorisées : {_CATEGORIES_HINT}")
        return clean_text, category
    return text, None


def parse_project_tag(text: str) -> tuple[str, str | None]:
    pattern = re.compile(r'\s*\bprojet:(\S+)', re.IGNORECASE)
    match = pattern.search(text)
    if match:
        project_name = match.group(1).upper()
        clean_text = pattern.sub("", text).strip()
        return clean_text, project_name
    return text, None


def parse_date(text: str) -> date | None:
    t = text.strip().lower()
    if t in ("aujourd'hui", "today"):
        return date.today()
    if t == "hier":
        return date.today() - timedelta(days=1)
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d/%m"):
        try:
            import time as _time
            parsed = date(*_time.strptime(t, fmt)[:3])
            if fmt == "%d/%m":
                parsed = parsed.replace(year=date.today().year)
            return parsed
        except ValueError:
            continue
    return None
