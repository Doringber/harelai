from typing import Protocol
from approval.core.models import Document, Extraction

class Extractor(Protocol):
    identity: str
    def extract(self, document: Document) -> Extraction: ...
