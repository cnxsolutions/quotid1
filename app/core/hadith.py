import html
import random
import httpx
from app.core.config import HADITH_API_KEY


def esc(value) -> str:
    return html.escape(str(value), quote=False) if value is not None else ""

BOOKS = [
    "sahih-bukhari",
    "sahih-muslim",
    "al-tirmidhi",
    "abu-dawood",
    "ibn-e-majah",
    "sunan-nasai",
]

BOOK_NAMES = {
    "sahih-bukhari": "Sahih Al-Bukhari",
    "sahih-muslim": "Sahih Muslim",
    "al-tirmidhi": "Jami' Al-Tirmidhi",
    "abu-dawood": "Sunan Abu Dawood",
    "ibn-e-majah": "Sunan Ibn-e-Majah",
    "sunan-nasai": "Sunan An-Nasa'i",
}


def get_random_hadith() -> dict | None:
    book = random.choice(BOOKS)
    page = random.randint(1, 50)
    url = (
        f"https://hadithapi.com/api/hadiths"
        f"?apiKey={HADITH_API_KEY}"
        f"&book={book}"
        f"&status=Sahih"
        f"&paginate=10"
        f"&page={page}"
    )
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        hadiths = data.get("hadiths", {}).get("data", [])
        if not hadiths:
            return None
        h = random.choice(hadiths)
        return {
            "book": BOOK_NAMES.get(book, book),
            "number": h.get("hadithNumber", "?"),
            "arabic": h.get("hadithArabic", ""),
            "english": h.get("hadithEnglish", ""),
            "chapter": h.get("chapter", {}).get("chapterEnglish", "") if isinstance(h.get("chapter"), dict) else "",
        }
    except Exception:
        return None


def format_hadith(h: dict) -> str:
    lines = ["<b>🕌 Hadith du jour</b>", ""]
    if h["arabic"]:
        lines.append(f"<blockquote>{esc(h['arabic'])}</blockquote>")
        lines.append("")
    if h["english"]:
        lines.append(f"<blockquote>{esc(h['english'])}</blockquote>")
        lines.append("")
    source = f"— {esc(h['book'])} n°{esc(h['number'])}"
    if h["chapter"]:
        source += f" · {esc(h['chapter'])}"
    lines.append(source)
    return "\n".join(lines)
