"""Evidence snapshot store (req. 6).

Snapshots are immutable (write-once, made read-only on disk) and
retained for at least the configured number of years - they are what
makes a finding usable in a claims discussion years later. File names
include a content hash, so re-capturing identical evidence is
idempotent and never overwrites.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(name: str) -> str:
    return _SAFE_RE.sub("_", name)[:100]


class EvidenceStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save(self, source_module: str, item_id: str, content: bytes, ext: str = "json") -> str:
        """Store raw evidence and return its path. Existing snapshots are
        never modified; identical content maps to the same file."""
        digest = hashlib.sha256(content).hexdigest()[:16]
        now = datetime.now(timezone.utc)
        directory = self.root / _safe(source_module) / f"{now:%Y}" / f"{now:%m}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{_safe(item_id)}_{digest}.{ext}"
        if not path.exists():
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(content)
            os.chmod(tmp, 0o444)
            os.replace(tmp, path)
        return str(path)
