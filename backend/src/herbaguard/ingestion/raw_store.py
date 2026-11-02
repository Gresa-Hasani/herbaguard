"""Content-addressed store for raw source snapshots (``data/raw/``, git-ignored).

Files are stored exactly as received, addressed by the SHA-256 of the raw bytes:
``<root>/<source_code>/<sha[:2]>/<sha><ext>``. Text formats are gzip-compressed on disk
(``.gz`` suffix); the hash always refers to the uncompressed bytes.
"""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

_COMPRESS = {".json", ".xml", ".html", ".txt"}


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extension_for(content_type: str | None, url: str) -> str:
    ct = (content_type or "").lower()
    if "json" in ct:
        return ".json"
    if "xml" in ct:
        return ".xml"
    if "html" in ct:
        return ".html"
    if "pdf" in ct or url.lower().endswith(".pdf"):
        return ".pdf"
    if "spreadsheet" in ct or url.lower().endswith(".xlsx"):
        return ".xlsx"
    if ct.startswith("text/"):
        return ".txt"
    return ".bin"


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, source_code: str, digest: str, ext: str) -> Path:
        suffix = f"{ext}.gz" if ext in _COMPRESS else ext
        return self.root / source_code / digest[:2] / f"{digest}{suffix}"

    def save(self, source_code: str, content: bytes, ext: str) -> tuple[str, Path]:
        """Store bytes (idempotent). Returns (sha256, path)."""
        digest = sha256(content)
        path = self.path_for(source_code, digest, ext)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(gzip.compress(content, mtime=0) if ext in _COMPRESS else content)
            tmp.replace(path)
        return digest, path

    def load(self, path: Path) -> bytes:
        data = path.read_bytes()
        return gzip.decompress(data) if path.suffix == ".gz" else data
