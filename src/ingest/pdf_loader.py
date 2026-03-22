from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass
class LoadedPdf:
    path: Path
    document: fitz.Document

    @property
    def page_count(self) -> int:
        return self.document.page_count


def load_pdf(path: Path) -> LoadedPdf:
    return LoadedPdf(path=path, document=fitz.open(path))
