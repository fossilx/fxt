from __future__ import annotations

import sqlite3

import polars as pl
import pytest

from fxt.core.versioned import TYPE_KEY
from fxt.data.ingest import migrate
from fxt.data.models import DownloadedMeta

from ..conftest import OLD_DOWNLOADED_JSON, tick_frame, write_old_daily


@pytest.fixture
def daily(tmp_path, store):
    p = tmp_path / "AUDCAD/TICK/2013/01/AUDCAD-2013-01-01.parquet"
    return write_old_daily(store, p, tick_frame())


def _row(path):
    con = sqlite3.connect(path.parent / "manifest.db")
    try:
        return con.execute("SELECT digest, size FROM financial_files").fetchone()
    finally:
        con.close()


def _convert(path, meta_io, **kw):
    return migrate.convert_download(path, meta_io=meta_io, **kw)


def test_dry_run_changes_nothing(daily, meta_io):
    before = daily.read_bytes()
    r = _convert(daily, meta_io, dry=True)
    assert (r.file, r.manifest) == ("would-convert", "would-update")
    assert daily.read_bytes() == before
    assert _row(daily) == ("olddigest", 1)


def test_convert_then_rerun(daily, meta_io, store):
    df_before = pl.read_parquet(daily)
    r = _convert(daily, meta_io)
    assert (r.file, r.manifest) == ("converted", "updated")

    assert store.read_meta(daily)[TYPE_KEY] == "DownloadedMeta@1"
    meta = meta_io.read_meta_as(daily, DownloadedMeta)
    assert meta.dataset.symbol == "AUDCAD" and meta.rows == df_before.height
    assert pl.read_parquet(daily).equals(df_before)
    assert _row(daily) == (migrate._file_digest(daily, "sha256"), daily.stat().st_size)
    assert not daily.with_name(daily.name + ".new").exists()

    r2 = _convert(daily, meta_io)
    assert (r2.file, r2.manifest) == ("already", "ok")


def test_manifest_fixed_on_rerun_after_crash(daily, meta_io):
    _convert(daily, meta_io, manifest=False)       # file converted, manifest stale
    assert _row(daily) == ("olddigest", 1)
    r = _convert(daily, meta_io)
    assert (r.file, r.manifest) == ("already", "updated")


def test_missing_manifest_row(tmp_path, store, meta_io):
    p = write_old_daily(store, tmp_path / "AUDCAD-2013-01-02.parquet", tick_frame(), manifest=False)
    (tmp_path / "manifest.db").touch()
    with pytest.raises(Exception):
        _convert(p, meta_io)


def test_unknown_typeid(tmp_path, store, meta_io):
    p = tmp_path / "x.parquet"
    store.write(tick_frame(), p, metadata={"type": "Nope@1", "json": "{}"})
    with pytest.raises(migrate.MigrationError, match="unexpected type id"):
        _convert(p, meta_io)


def test_convert_tree(tmp_path, store, meta_io):
    import json
    base = json.loads(OLD_DOWNLOADED_JSON)
    for day in (1, 2, 3):
        js = {**base, "start": f"2013-01-{day:02d}T00:00:00Z", "end": f"2013-01-{day + 1:02d}T00:00:00Z"}
        write_old_daily(store, tmp_path / f"m/AUDCAD-2013-01-{day:02d}.parquet", tick_frame(), json.dumps(js))
    results, errors = migrate.convert_tree(tmp_path, meta_io=meta_io)
    assert not errors
    assert [r.file for r in results] == ["converted"] * 3
    again, _ = migrate.convert_tree(tmp_path, meta_io=meta_io)
    assert [(r.file, r.manifest) for r in again] == [("already", "ok")] * 3
