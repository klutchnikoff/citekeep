"""Filesystem operations with explicit concurrency and metadata guarantees."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path


class ConcurrentModification(OSError):
    """A file changed after the operation using it was planned."""


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_atomically(path, text, expected_digest=None):
    path = Path(path).expanduser()
    target = path.resolve() if path.is_symlink() else path

    mode = None
    if target.exists():
        if expected_digest is not None and digest(target) != expected_digest:
            raise ConcurrentModification(
                f"{path}: changed since the operation was planned"
            )
        mode = stat.S_IMODE(target.stat().st_mode)

    # Entered as a context manager below; the name is needed first, and
    # delete=False is what allows the atomic rename.
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115
        "w", encoding="utf-8", delete=False, dir=target.parent, prefix=target.name + "."
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode if mode is not None else 0o644)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
