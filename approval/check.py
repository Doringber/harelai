"""Text normalization and evidence checks shared by the workflow."""
import re
from datetime import datetime

_NUMBER = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
_PERCENT = re.compile(r"\s*(?:%|％|percent\b)", re.IGNORECASE)
_BOUND = re.compile(r"(?:[<>≤≥]=?|=<|=>)\s*$")
_MAX_LABEL_GAP = 80


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def to_iso(text: str) -> str | None:
    """'03/15/1952', 'March 15, 1952' and '1952-03-15' all become '1952-03-15'."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def same_name(a: str, b: str) -> bool:
    """'JOHNSON, MARGARET A.' and 'Margaret A Johnson' are the same name."""
    words = lambda s: sorted(re.sub(r"[.,]", " ", s).casefold().split())
    return words(a) == words(b)


def display_name(name: str) -> str:
    """'JOHNSON, MARGARET A.' -> 'Margaret A. Johnson'. Mixed-case and Hebrew names are unchanged."""
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first.strip()} {last.strip()}"
    return name.title() if name.isupper() else name


def _labels(quote: str, terms: list[str]):
    """Field labels in the quote. FEV1/FVC is a different measurement from FEV1."""
    cleaned = [term.strip() for term in terms if term and term.strip()]
    if not cleaned:
        return []
    pattern = re.compile("|".join(re.escape(term) for term in sorted(set(cleaned), key=len, reverse=True)), re.IGNORECASE)
    return [match for match in pattern.finditer(quote) if quote[match.end():match.end() + 1] != "/"]


def _gap(label, number) -> int:
    if label.end() <= number.start():
        return number.start() - label.end()
    if number.end() <= label.start():
        return label.start() - number.end()
    return 0


def number_supports_field(value, quote: str, terms: list[str] | tuple[str, ...] = (), *, percent: bool = False) -> bool:
    """The value must be the measured number for this field, not a nearby measurement or a threshold."""
    if not isinstance(value, (int, float)):
        return False
    numbers = [item for item in _NUMBER.finditer(quote) if not _BOUND.search(quote[:item.start()])]
    eligible = [item for item in numbers if not percent or _PERCENT.match(quote[item.end():])]
    hits = [item for item in eligible if float(item.group().replace(",", "")) == value]
    if not hits:
        return False
    labels = _labels(quote, list(terms))
    if not labels:
        return not terms

    def nearest(item) -> int:
        return min(_gap(label, item) for label in labels)

    best_hit = min(nearest(item) for item in hits)
    best_any = min(nearest(item) for item in eligible)
    return best_hit <= best_any and best_hit <= _MAX_LABEL_GAP
