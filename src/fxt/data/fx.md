

# Basic setup when first setting this up
```
fxt/data/
    refdata/            # leaf: imports nothing else in fxt.data
    sources/
        __init__.py     # get_source("dukascopy") → adapter
        base.py         # Source protocol
        dukascopy.py    # fetch_day(symbol, day) -> DataFrame
    ingest/
        download.py     # adapter → daily files + manifest.db
        consolidate.py  # daily → lake/raw (temp file, checks, rename)
        verify.py
    derived/
        bars.py         # TICK → 1MIN → 1HOUR (current lake/derived code)
    models/
        base.py         # shared meta base, DatasetIdentity
        manifest.py     # FileRecord, FinancialFileRecord, Manifest
        downloaded.py   # DownloadedDataMeta
        raw.py          # ConsolidatedDataMeta
        bars.py         # BarsMeta
    paths.py            # Lake/Ingest path builders, optional root
```

This may change as time goes on.



