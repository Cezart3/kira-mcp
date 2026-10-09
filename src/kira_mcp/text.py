"""Text helpers: diacritics folding, HTML stripping, slugs, contact redaction."""
import html as html_lib
import re
import unicodedata

_WS_RE = re.compile(r"\s+")
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def squash_ws(s: str | None) -> str:
    return _WS_RE.sub(" ", s or "").strip()


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = _BR_RE.sub(" ", s)
    s = _TAG_RE.sub(" ", s)
    return squash_ws(html_lib.unescape(s))


def fold(s: str | None) -> str:
    """Lowercase + strip diacritics (ă→a, ș→s, ț→t...) for robust Romanian matching."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def slugify(s: str, sep: str = "-") -> str:
    """'Târgu Mureș' -> 'targu-mures'."""
    return _NON_SLUG.sub(sep, fold(s)).strip("-")


# --- personal-data redaction --------------------------------------------------
# Results carry the rental facts and a link to the original ad. Contact details
# stay on the source site: phone numbers and emails are stripped from any text
# we return.
# separators people use to dodge scrapers: "0756 // 33 // 44 // 31", "0740.123.456"
_SEP = r"[\s./\\()\-]{0,4}"
_PHONE_RE = re.compile(rf"(?<!\d)(?:\+?40|0){_SEP}7(?:{_SEP}\d){{8}}(?!\d)")
_PHONE_LANDLINE_RE = re.compile(rf"(?<!\d)(?:\+?40|0){_SEP}[23](?:{_SEP}\d){{8}}(?!\d)")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_REDACT = "[contact pe site]"


def redact_personal(s: str | None) -> str:
    """Remove phone numbers + emails from listing text."""
    if not s:
        return ""
    s = _PHONE_RE.sub(_REDACT, s)
    s = _PHONE_LANDLINE_RE.sub(_REDACT, s)
    return _EMAIL_RE.sub(_REDACT, s)
