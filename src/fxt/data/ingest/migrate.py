#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.data.ingest.migrate

One-off: convert daily download files from DownloadedDataMeta@1 (old dataprep
models) to DownloadedMeta@1, in place, and keep each month's manifest.db in
sync with the rewritten files.

Per file:
    1. already DownloadedMeta@1?   -> skip the rewrite (still syncs the manifest)
    2. read legacy meta + frame, build the new meta (legacy.upgrade_downloaded;
       symbol etc. become refdata's official names)
    3. write data + new meta to "<file>.new"
    4. read it back: frame must equal the original, meta must equal the new one
    5. replace the original with it
    6. manifest.db row for the file: check `rows`, update `digest` + `size`

Safe to re-run: converted files are skipped, and step 6 runs for every file,
so a crash between 5 and 6 gets fixed by the next run.

BACK UP THE DOWNLOADS FIRST. This rewrites every file.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import polars as pl

from fxt.core.versioned import TYPE_KEY, VersionedModelIO
from fxt.data.models import DownloadedMeta, get_meta_io
from fxt.data.models.legacy import DownloadedDataMeta, upgrade_downloaded

import logging
logger = logging.getLogger(__name__)

__all__ = [
    "MigrationError", "ManifestError", "Result",
    "convert_download", "sync_manifest", "iter_downloads", "convert_tree",
]

MANIFEST_NAME = "manifest.db"
MANIFEST_TABLE = "financial_files"
NEW_SUFFIX = ".new"


class MigrationError(RuntimeError):
    """ A file couldn't be converted (unknown type id, frame mismatch, ...). """

class ManifestError(MigrationError):
    """ The manifest row for a file is missing, duplicated, or disagrees with it. """


FileAction = Literal["converted", "already", "would-convert"]
ManifestAction = Literal["updated", "ok", "would-update", "skipped"]

@dataclass(frozen=True, slots=True)
class Result:
    path: Path
    file: FileAction
    manifest: ManifestAction
#


#!================================================================================(80)
#! manifest
#!--------------------------------------------------------------------------------(80)
def _file_digest(path: Path, algo: str) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, algo).hexdigest()


def sync_manifest(path: Path | str, *, rows: int | None = None, dry: bool = False) -> ManifestAction:
    """ Make the file's row in `<dir>/manifest.db` match the file on disk
        (digest + size). Record paths are relative to the manifest's dir.
        `rows`: if given, must equal the row's `rows` (sanity check).
    """
    path = Path(path)
    db_path = path.parent / MANIFEST_NAME
    if not db_path.exists():
        raise ManifestError(f"{path}: no {MANIFEST_NAME} beside it")

    rel = path.name
    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        found = con.execute(
            f"SELECT rowid, * FROM {MANIFEST_TABLE} WHERE path = ? OR path LIKE ?",
            (rel, f"%/{rel}"),
        ).fetchall()
        if len(found) != 1:
            raise ManifestError(f"{path}: expected 1 manifest row, found {len(found)}")
        row = found[0]

        if rows is not None and row["rows"] is not None and row["rows"] != rows:
            raise ManifestError(f"{path}: manifest says rows={row['rows']}, file has {rows}")
        if row["status"] != "success":
            raise ManifestError(f"{path}: file exists but manifest status={row['status']!r}")

        algo = row["algo"] or "sha256"
        digest = _file_digest(path, algo)
        size = path.stat().st_size
        if row["digest"] == digest and row["size"] == size:
            return "ok"
        if dry:
            return "would-update"
        with con:
            con.execute(
                f"UPDATE {MANIFEST_TABLE} SET digest = ?, size = ? WHERE rowid = ?",
                (digest, size, row["rowid"]),
            )
        return "updated"
    finally:
        con.close()
#


#!================================================================================(80)
#! one file
#!--------------------------------------------------------------------------------(80)
def convert_download(
    path: Path | str,
    *,
    meta_io: VersionedModelIO | None = None,
    dry: bool = False,
    manifest: bool = True,
) -> Result:
    """ Convert one daily file in place (see module docstring). """
    path = Path(path)
    io = meta_io or get_meta_io()
    new_id = DownloadedMeta.get_id()
    old_id = DownloadedDataMeta.get_id()

    typeid = io.backend.read_meta(path).get(TYPE_KEY)
    if typeid == new_id:
        df_rows = None
        action: FileAction = "already"
    elif typeid == old_id:
        old = io.read_meta_as(path, DownloadedDataMeta)
        df = pl.read_parquet(path, hive_partitioning=False)
        new = upgrade_downloaded(old, rows=df.height)
        df_rows = df.height

        if dry:
            action = "would-convert"
        else:
            tmp = path.with_name(path.name + NEW_SUFFIX)
            try:
                io.write(df, tmp, new, overwrite=True)
                back = pl.read_parquet(tmp, hive_partitioning=False)
                if back.schema != df.schema or not back.equals(df):
                    raise MigrationError(f"{path}: rewritten frame differs from the original")
                if io.read_meta_as(tmp, DownloadedMeta) != new:
                    raise MigrationError(f"{path}: rewritten meta differs from the built meta")
                os.replace(tmp, path)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
            action = "converted"
    else:
        raise MigrationError(f"{path}: unexpected type id {typeid!r} (want {old_id} or {new_id})")

    if not manifest:
        return Result(path, action, "skipped")
    if action == "would-convert":
        #! the digest will change once converted; just check the row exists + rows match
        sync_manifest(path, rows=df_rows, dry=True)
        return Result(path, action, "would-update")
    return Result(path, action, sync_manifest(path, rows=df_rows, dry=dry))
#


#!================================================================================(80)
#! many files
#!--------------------------------------------------------------------------------(80)
def iter_downloads(root: Path | str) -> Iterator[Path]:
    """ Every daily parquet file under `root`, sorted (leftover *.new files skipped). """
    yield from sorted(p for p in Path(root).rglob("*.parquet") if p.is_file())


def _convert_worker(path: Path, dry: bool, manifest: bool) -> Result:
    return convert_download(path, dry=dry, manifest=manifest)   # default meta_io per process


def convert_tree(
    root: Path | str,
    *,
    dry: bool = False,
    manifest: bool = True,
    workers: int = 1,
    meta_io: VersionedModelIO | None = None,
    on_result: Callable[[Result], None] | None = None,
    on_error: Callable[[Path, BaseException], None] | None = None,
    stop_on_error: bool = True,
) -> tuple[list[Result], list[tuple[Path, BaseException]]]:
    """ convert_download() for every file under `root`.

        workers > 1 uses a process pool (each process builds its own store from
        the project settings, so `meta_io` must be None then).
        A frame/meta mismatch always stops the run, whatever `stop_on_error` says.
    """
    paths = list(iter_downloads(root))
    results: list[Result] = []
    errors: list[tuple[Path, BaseException]] = []

    def _handle_error(p: Path, e: BaseException) -> bool:
        errors.append((p, e))
        if on_error:
            on_error(p, e)
        hard = isinstance(e, MigrationError) and not isinstance(e, ManifestError)
        return stop_on_error or hard

    if workers <= 1:
        for p in paths:
            try:
                r = convert_download(p, meta_io=meta_io, dry=dry, manifest=manifest)
            except Exception as e:
                if _handle_error(p, e):
                    break
                continue
            results.append(r)
            if on_result:
                on_result(r)
        return results, errors

    if meta_io is not None:
        raise ValueError("meta_io can't be passed to worker processes; use workers=1")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_convert_worker, p, dry, manifest): p for p in paths}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                r = fut.result()
            except Exception as e:
                if _handle_error(p, e):
                    for f in futures:
                        f.cancel()
                    break
                continue
            results.append(r)
            if on_result:
                on_result(r)
    return results, errors
#-
