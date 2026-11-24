from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fxt.data.models import DATA_MODELS, DownloadedMeta, get_meta_io
from fxt.data.models.legacy import (
    ConsolidatedDataMeta, DownloadedDataMeta, LegacyModelError, upgrade_downloaded,
)

from ..conftest import OLD_CONSOLIDATED_JSON, OLD_DOWNLOADED_JSON


def test_reads_real_old_footers():
    d = DATA_MODELS.validate_json("DownloadedDataMeta@1", OLD_DOWNLOADED_JSON)
    c = DATA_MODELS.validate_json("ConsolidatedDataMeta@1", OLD_CONSOLIDATED_JSON)
    assert isinstance(d, DownloadedDataMeta) and d.dataset.symbol == "AUD/CAD"
    assert isinstance(c, ConsolidatedDataMeta)
    assert c.consolidation_tests[0].status == "passed"


def test_legacy_is_read_only(tmp_path, meta_io):
    d = DATA_MODELS.validate_json("DownloadedDataMeta@1", OLD_DOWNLOADED_JSON)
    with pytest.raises(LegacyModelError):
        d.serialize()


def test_upgrade_downloaded():
    old = DATA_MODELS.validate_json("DownloadedDataMeta@1", OLD_DOWNLOADED_JSON)
    new = upgrade_downloaded(old, rows=5)  # type: ignore[arg-type]
    assert isinstance(new, DownloadedMeta)
    assert new.dataset.symbol == "AUDCAD"
    assert (new.dataset.source, new.dataset.market, new.dataset.interval) == ("dukascopy", "forex", "TICK")
    assert new.start == datetime(2013, 1, 1, tzinfo=UTC)
    assert new.created_at == datetime(2026, 11, 22, 12, 42, 38, 180968, tzinfo=UTC)
    assert new.rows == 5 and new.method == "dukascopy-python"


def test_upgrade_rejects_non_success():
    old = DATA_MODELS.validate_json("DownloadedDataMeta@1",
                                    OLD_DOWNLOADED_JSON.replace('"success"', '"empty"'))
    with pytest.raises(ValueError, match="status"):
        upgrade_downloaded(old, rows=5)  # type: ignore[arg-type]


