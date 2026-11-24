#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.data.ingest.manifest

Merging the downloader's per-month manifest.db files (ported from the old
fxtapps.dataprep.consolidator.manifest_tools).

Every manifest holds one table (financial_files) with identical columns. The
merge goes into an in-memory db with the same DDL and indices, and rewrites
each row's `path` (stored relative to its own manifest's folder) to be relative
to a `base` folder you choose, e.g. the downloads root. The old version made
paths relative to the current working directory, so the merged manifest
depended on where the command was run from.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import os
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from sqlite_utils import Database

__all__ = [
    "MANIFEST_NAME", "CONSOLIDATED_MANIFEST_NAME", "MANIFEST_TABLE", "INFO_TABLE",
    "write_info", "read_info",
    "Conflict", "ManifestError", "SchemaMismatchError",
    "find_manifests", "validate_schemas", "merge_to_memory", "write_to_file", "unique_values",
]

MANIFEST_NAME = "manifest.db"
CONSOLIDATED_MANIFEST_NAME = "consolidated-manifest.db"
MANIFEST_TABLE = "financial_files"
INFO_TABLE = "manifest_info"          # key/value description of a merged manifest

Conflict = Literal["latest", "error", "ignore", "replace"]


class ManifestError(Exception):
    """ A manifest is missing, unreadable, or inconsistent. """

class SchemaMismatchError(ManifestError):
    """ A manifest's table is missing or differs from the first manifest's. """


def _q(name: str) -> str:
    """ Quote an SQL identifier. """
    return '"' + name.replace('"', '""') + '"'


def _open_readonly(path: Path) -> Database:
    if not path.is_file():
        raise FileNotFoundError(path)
    return Database(sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True))


#!================================================================================(80)
#! public
#!--------------------------------------------------------------------------------(80)
def find_manifests(folder: Path, name: str = MANIFEST_NAME) -> list[Path]:
    """ Every `name` file under `folder`, sorted (e.g. one per month of a year). """
    return sorted(folder.rglob(name)) if folder.is_dir() else []


def _schema(db: Database, table: str) -> dict[str, tuple]:
    if table not in db.table_names():
        raise SchemaMismatchError(f"table {table!r} not found")
    return {c.name: (c.type.upper(), c.notnull, c.default_value, c.is_pk) for c in db[table].columns}


def validate_schemas(paths: Sequence[Path], table: str = MANIFEST_TABLE) -> dict[str, tuple]:
    """ Every manifest has `table`, with exactly the first manifest's columns.
        Returns that schema; raises SchemaMismatchError listing every problem.
    """
    if not paths:
        raise ManifestError("no manifests given")
    errors: list[str] = []
    reference: dict[str, tuple] | None = None
    for p in paths:
        db = _open_readonly(p)
        try:
            schema = _schema(db, table)
        except SchemaMismatchError as e:
            errors.append(f"{p}: {e}")
            continue
        finally:
            db.close()
        if reference is None:
            reference = schema
            continue
        for c in sorted(reference.keys() - schema.keys()):
            errors.append(f"{p}: missing column {c!r}")
        for c in sorted(schema.keys() - reference.keys()):
            errors.append(f"{p}: unexpected column {c!r}")
        for c in sorted(reference.keys() & schema.keys()):
            if reference[c] != schema[c]:
                errors.append(f"{p}: column {c!r}: {schema[c]} != {reference[c]}")
    if errors:
        raise SchemaMismatchError(f"manifest schema problems (reference: {paths[0]}):\n  "
                                  + "\n  ".join(errors))
    assert reference is not None
    return reference


def merge_to_memory(
    paths: Sequence[Path],
    *,
    base: Path,
    table: str = MANIFEST_TABLE,
    on_conflict: Conflict = "error",
    path_column: str = "path",
    recency_column: str = "ingested_at",
    batch_size: int = 5000,
) -> Database:
    """ Merge manifests into a new in-memory db.

        base:         rewritten paths are relative to this folder (posix)
        on_conflict:  two rows with the same primary key:
            "error"   raise sqlite3.IntegrityError (default: a day downloaded twice
                      into two manifests is a problem worth seeing)
            "latest"  keep the row with the greater `recency_column`
            "ignore"  keep the first row seen
            "replace" keep the last row seen
    """
    paths = [Path(p) for p in paths]
    validate_schemas(paths, table)
    base = base.resolve()

    first = _open_readonly(paths[0])
    try:
        table_ddl = first[table].schema
        index_ddl = [r[0] for r in first.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL",
            [table]).fetchall()]
        columns = [c.name for c in first[table].columns]
        pks = first[table].pks  # type: ignore[attr-defined]
    finally:
        first.close()

    if path_column not in columns:
        raise ManifestError(f"manifests have no {path_column!r} column")
    path_idx = columns.index(path_column)

    col_sql = ", ".join(_q(c) for c in columns)
    marks = ", ".join("?" for _ in columns)
    if on_conflict == "latest":
        if pks == ["rowid"] or recency_column not in columns:
            raise ManifestError(f"'latest' needs a primary key and a {recency_column!r} column")
        sets = ", ".join(f"{_q(c)} = excluded.{_q(c)}" for c in columns if c not in pks)
        insert = (f"INSERT INTO {_q(table)} ({col_sql}) VALUES ({marks}) "
                  f"ON CONFLICT ({', '.join(_q(p) for p in pks)}) DO UPDATE SET {sets} "
                  f"WHERE excluded.{_q(recency_column)} > {_q(table)}.{_q(recency_column)}")
    else:
        verb = {"error": "INSERT INTO", "ignore": "INSERT OR IGNORE INTO",
                "replace": "INSERT OR REPLACE INTO"}[on_conflict]
        insert = f"{verb} {_q(table)} ({col_sql}) VALUES ({marks})"

    mem = Database(memory=True)
    mem.execute(table_ddl)
    for p in paths:
        folder = p.parent.resolve()
        src = _open_readonly(p)
        try:
            cur = src.execute(f"SELECT {col_sql} FROM {_q(table)}")
            with mem.conn:                          # one transaction per manifest
                while batch := cur.fetchmany(batch_size):
                    rows = []
                    for r in batch:
                        r = list(r)
                        if r[path_idx] is not None:
                            full = Path(os.path.normpath(folder / str(r[path_idx])))
                            r[path_idx] = full.relative_to(base).as_posix()
                        rows.append(tuple(r))
                    mem.conn.executemany(insert, rows)
        finally:
            src.close()
    for sql in index_ddl:
        mem.execute(sql)
    mem.conn.commit()
    return mem


def write_to_file(db: Database, path: Path, *, overwrite: bool = False) -> Path:
    """ Copy a (typically in-memory) db to a file. """
    path = Path(path)
    if path.exists():
        if not overwrite:
            raise FileExistsError(path)
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    db.conn.commit()
    dest = sqlite3.connect(path)
    try:
        db.conn.backup(dest)
    finally:
        dest.close()
    return path


def write_info(db: Database, info: dict[str, Any]) -> None:
    """ (Re)write the key/value INFO_TABLE describing this manifest.
        Values are stored as text (None -> NULL).
    """
    with db.conn:
        db.execute(f"DROP TABLE IF EXISTS {_q(INFO_TABLE)}")
        db.execute(f"CREATE TABLE {_q(INFO_TABLE)} (key TEXT PRIMARY KEY NOT NULL, value TEXT)")
        db.conn.executemany(f"INSERT INTO {_q(INFO_TABLE)} (key, value) VALUES (?, ?)",
                            [(k, None if v is None else str(v)) for k, v in info.items()])


def read_info(path: Path) -> dict[str, str | None]:
    """ INFO_TABLE of a manifest file as a dict ({} if it has none, e.g. month manifests). """
    db = _open_readonly(Path(path))
    try:
        if INFO_TABLE not in db.table_names():
            return {}
        return dict(db.execute(f"SELECT key, value FROM {_q(INFO_TABLE)} ORDER BY rowid").fetchall())
    finally:
        db.close()


def unique_values(db: Database, column: str, table: str = MANIFEST_TABLE) -> list[Any]:
    return [r[0] for r in db.execute(f"SELECT DISTINCT {_q(column)} FROM {_q(table)}").fetchall()]
#-
