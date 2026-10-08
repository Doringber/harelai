from pathlib import Path
from typing import Protocol
from approval.core.models import Page

class DocumentReader(Protocol):
    def read(self, path: Path) -> list[Page]: ...
