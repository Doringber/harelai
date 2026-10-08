import unicodedata

def normalize(text: str) -> str:
    # Preserve symbols and non-Latin scripts; normalize only Unicode composition/whitespace.
    return " ".join(unicodedata.normalize("NFC", text).split())

def text_quality(text: str) -> tuple[bool, list[str]]:
    compact = normalize(text)
    if not compact: return False, ["no_extracted_text"]
    bad = sum(c == "\ufffd" or (unicodedata.category(c) == "Cc" and not c.isspace()) for c in text)
    if bad / max(len(text), 1) > .01: return False, ["corrupt_characters"]
    if len(compact) < 12: return False, ["very_sparse_text"]
    return True, []
