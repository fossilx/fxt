#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.core.io.hash_cache

sha256 of files, cached by (resolved path, size, mtime_ns) in a small sqlite db,
so a multi-GB file is hashed once until it changes. Used to check that a derived
file's InputRef still matches its input without rehashing every raw year.

    hasher = HashCache(lake_root / ".sha256-cache.db")
    hasher.sha256(path)

A changed file always gets a new size or mtime in practice, so a stale entry is
never returned. Delete the db to reset; it only holds hashes.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

__all__ = ["HashCache", "sha256_uncached"]


def sha256_uncached(path: Path | str) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


class HashCache:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()          # the picker hashes from a worker thread

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path, timeout=30)
        con.execute("CREATE TABLE IF NOT EXISTS sha256 ("
                    " path TEXT PRIMARY KEY, size INTEGER NOT NULL,"
                    " mtime_ns INTEGER NOT NULL, sha256 TEXT NOT NULL)")
        return con

    def cached(self, path: Path | str) -> str | None:
        """ The cached hash if the file is unchanged, else None (never hashes). """
        p = Path(path).resolve()
        st = p.stat()
        with self._lock:
            con = self._connect()
            try:
                row = con.execute("SELECT size, mtime_ns, sha256 FROM sha256 WHERE path = ?",
                                  (str(p),)).fetchone()
            finally:
                con.close()
        if row and row[0] == st.st_size and row[1] == st.st_mtime_ns:
            return row[2]
        return None

    def sha256(self, path: Path | str) -> str:
        p = Path(path).resolve()
        if (hit := self.cached(p)) is not None:
            return hit
        st = p.stat()
        digest = sha256_uncached(p)
        if p.stat().st_mtime_ns != st.st_mtime_ns:     # changed while hashing: don't cache
            return digest
        with self._lock:
            con = self._connect()
            try:
                with con:
                    con.execute("INSERT OR REPLACE INTO sha256 VALUES (?, ?, ?, ?)",
                                (str(p), st.st_size, st.st_mtime_ns, digest))
            finally:
                con.close()
        return digest
#-
