from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from fxt.core.versioned import from_kv, to_kv
from fxt.data.models import (
    DATA_MODELS, BarsMeta, CheckedMeta, CheckRecord, DatasetKey, DownloadedMeta,
    InputRef, RawMeta, Transform,
)

KEY = DatasetKey(source="dukascopy", market="forex", symbol="AUDCAD", interval="TICK")
Y0, Y1 = datetime(2013, 1, 1, tzinfo=UTC), datetime(2014, 1, 1, tzinfo=UTC)


def test_registered_ids():
    for cls, typeid in [(DownloadedMeta, "DownloadedMeta@1"), (RawMeta, "RawMeta@1"),
                        (BarsMeta, "BarsMeta@1")]:
        assert cls.get_id() == typeid
        assert DATA_MODELS.get_model(typeid) is cls


def test_round_trip_and_utc():
    est = timezone(timedelta(hours=-5))
    m = DownloadedMeta(dataset=KEY, start=Y0, end=Y0 + timedelta(days=1),
                       created_at=datetime(2026, 11, 22, 7, 42, tzinfo=est),
                       rows=5, method="dukascopy-python")
    assert m.created_at.utcoffset() == timedelta(0)
    assert from_kv(DATA_MODELS, to_kv(m)) == m


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        DownloadedMeta(dataset=KEY, start=Y0, end=Y1, rows=1, method="x", other={})  # type: ignore


def test_raw_is_checked_and_failed_checks():
    m = RawMeta(dataset=KEY, start=Y0, end=Y1, rows=10, days=250, method="dukascopy-python",
                manifest_sha256="ab", checks=(
                    CheckRecord(name="gap check", status="fail", detail="2012-01-02..02-09"),
                    CheckRecord(name="time order", status="pass"),
                ))
    assert isinstance(m, CheckedMeta)
    assert not m.passed
    assert [c.name for c in m.failed_checks] == ["gap check"]


def test_bars_still_build():
    m = BarsMeta(dataset=KEY.with_interval("1MIN"), start=Y0, end=Y1, rows=3,
                 inputs=(InputRef(path="raw/x.parquet", typeid="RawMeta@1", sha256="ab"),),
                 transform=Transform(name="ticks_to_bars", version=1))
    assert m.passed and isinstance(m, CheckedMeta)
    assert m.identity == (m.dataset, Y0, Y1)


#! DatasetKey.from_refdata: official names come from refdata, not the input
@pytest.mark.parametrize("spelling", ["AUD-CAD", "AUDCAD", "audcad", "AUD/CAD", "aud_cad"])
def test_from_refdata_symbol_spellings(spelling):
    k = DatasetKey.from_refdata("dukascopy", "forex", spelling, "TICK")
    assert k == DatasetKey(source="dukascopy", market="forex", symbol="AUDCAD", interval="TICK")


def test_from_refdata_alias():
    from fxt.data.refdata import symbols
    sym = next(s for s in symbols() if s.aliases)
    k = DatasetKey.from_refdata("dukascopy", sym.market, sym.aliases[0], "TICK")
    assert k.symbol == sym.name


@pytest.mark.parametrize("args", [
    ("nope", "forex", "AUDCAD", "TICK"),       # unknown source
    ("dukascopy", "nope", "AUDCAD", "TICK"),   # unknown market
    ("dukascopy", "forex", "XXX/YYY", "TICK"), # unknown symbol
    ("dukascopy", "forex", "AUDCAD", "7MIN"),  # unknown interval
])
def test_from_refdata_rejects_unknown(args):
    with pytest.raises(KeyError):
        DatasetKey.from_refdata(*args)
