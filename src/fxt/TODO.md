---
title: TODO / Ideas
purpose: Running list of ideas and to-dos that aren't scheduled in a spec yet, so they don't get forgotten. Once an item is planned, it moves into the relevant spec's next-steps section.
version: 1.8
last_modified: 2026-11-21
status: active
---

# TODO / Ideas

## Data prep

- [ ] **Merge all data code under `fxt.data`** (replaces "move the dataprep stages over to the new library design"). Built in a **new repo directory**, so the current repo keeps running its multi-symbol downloads untouched.

  ```
  fxt/data/
      refdata/    # sources, markets, symbols, aliases (sqlite); a leaf: imports nothing else in fxt.data
      sources/    # one small adapter per source (dukascopy: fetch a day → frame)
      ingest/     # download → daily files + manifest, consolidate → yearly, promote → lake/raw (was fxt.dataprep)
      lake/       # current fxt.lake: Lake paths, models, bars (TICK → 1MIN → 1HOUR)
      models/     # meta models (downloaded, consolidated, raw, bars), if not kept under lake/
  ```
  
  - `fxt.dataprep`'s class hierarchies (BaseSource + one class per source) go away: a source protocol (e.g. `fetch_day(symbol, day) -> DataFrame`) plus plain functions; ingest stays generic.
  - `refdata` stays a leaf (research uses it too, e.g. base/quote currencies for `cross`), so it can move out later with an import change.
  - Path builders take an optional data root (default: the main data root), same layout everywhere.
  - **Cutover:** run the new ingest beside the old one; it must produce identical consolidated files for a pair already downloaded before the old code is deleted. Point the new repo at its own data root (or read-only at the lake) while the old downloader is still writing manifests.
- [ ] Build a tool/script that verifies every stage of the data generation process for a given `(source, market, symbol)`: downloads → consolidated → lake/raw → derived bars.
- [ ] **Gap check (after the pipeline is complete):** a verification script or built-in check that flags any stretch of **3+ days without data** (markets close at most ~3 days: weekend + holiday). Could live in the consolidator (on days that actually have ticks), in the bar checks (largest gap between hourly bars), or in the verifier above. Test case: EURJPY 2012, one day of data on 2012-01-02 and then nothing until 2012-02-09.
  - Found while checking: the consolidator's year check doesn't enforce anything. In `process_year` (`consolidator/con.py`), `missing = self.missing_days(...)` is computed but never used, and `days` includes days resolved as `"empty"` (the `status = "success"` filter is commented out), so a year with weeks of empty days still passes. Fix in the new ingest.
- [ ] Once the process is stable, build a runner that executes the whole data generation process end to end for a given `(source, market, symbol)` (and optional years).
- [ ] Split the `fxtapps` dataprep reader into its own app: a general reader for the library's metadata-stamped files.
- [ ] **Maybe: switch to the new dukascopy-python API** (`fetch_ticks()`; should make downloading through a proxy easier). It has an extra `tickVolume` field. Before re-downloading anything, fetch one day with the new API and compare against the stored ticks: Dukascopy's raw tick files only carry time, bid, ask, bid volume and ask volume, so `tickVolume` is most likely derived (e.g. bid + ask volume) and can be computed from existing data. It becomes the dukascopy adapter in `fxt.data.sources`; a new column means a new raw meta version.

## Research pipeline

- [x] One-command chain runner: `pixi run research-chain SYMBOL [SYMBOL …]` (2026-11-18; ML pipeline spec §3.4). Default configs only; non-default chains still use the individual commands.
- [x] **Repeat runs inflated the trial count** (fixed 2026-11-19; ML pipeline spec §9.6): runs store `trades_hash`, and runs with identical trades count as one trial. Earlier runs need `pixi run registry backfill`.
- [ ] Maybe later: count *effective* trials by clustering correlated (but not identical) return series, as López de Prado suggests, instead of counting every distinct trade set fully.
- [ ] **Potential next step, after the JPY-cross test (ML pipeline spec §9.7): full-basket cross-pair analysis.** Every pair of `n` currencies (nC2 targets; 28 for the 8 majors) is the target in turn, with the other pairs as inputs. Assumes every pair's bars and default chain are built. Don't evaluate on any JPY-test pair (GBPJPY, AUDJPY, CHFJPY, CADJPY) before the pre-registered run.
  - **Already mostly there:** the `cross` feature set (spec §4.4) with `basket` = all nC2 pairs gives each target AB `base_str` from AC, AD, … and `quote_str` from BC, BD, …, with AB left out (2(n−2) related pairs per target).
  - **Strength panel:** compute per-currency sums of signed z once for the whole basket (`S_X = Σ_Y z_XY`, hourly), then each target's leave-one-out value by subtracting its own term, instead of reloading every basket pair's bars for each of the 28 targets. One config hash for the basket.
  - **Coverage rule across pairs:** a currency's strength at `bar_time` needs a minimum share of its pairs present (like `min_coverage`).
  - **Option: least-squares strength.** Also use pairs that touch neither A nor B (CD helps separate "A moved" from "C moved" in AC). On a complete set of pairs the solution is closed-form: `s_X = (1/n) Σ_Y r_XY`.
  - **Batch driver:** `research-chain` over all pairs → `features --set cross` → `registry sync`; pooled `evaluate` already takes any number of symbols.
  - **Statistics (the hard part):**
    - Only ~n independent drivers, not nC2: a yen move appears in every JPY pair at once. Pooled `n_eff` / `t_eff` only account for overlap within a pair; needs cross-pair uniqueness or clustering trades by currency.
    - Position cap per **currency**, not just per symbol (long GBPJPY + AUDJPY + CADJPY is one short-yen bet).
    - Minor crosses (e.g. NZDCHF, CADCHF) cost several times EURJPY's ~1 bp: makes open question 2 (labels net of cost) matter.
    - One pre-registered pooled run, not one trial per pair.
  - **Alternative design:** the currency as the target (n strength series instead of nC2 pair labels; trade strongest vs weakest). A new sampler + label type rather than a feature set.

## Structure

- [ ] **Possible restructure after the JPY analysis:** shared functionality easy to reach, each major research attempt self-contained, one question per project (e.g. "how do I set up the analysis for one pair?" → "how do I generalize it to all pairs?"). Layout not decided; the working plan:
  - **Three layers:** market data (`fxt.data`: refdata, ingest, lake; one shared copy by default) → research framework (hashing, `StageConfig`, stages, harness, registry code; shared library) → projects (the question, pre-registrations, own samplers/features, research outputs, `experiments.db`, write-up; self-contained).
  - **Path builders take an optional root**, defaulting to the main data root, so any project can point at its own lake with the same layout if it needs different data. `Lake` / `Research` already have roots; mostly a settings change.
  - **Monorepo first, separate repos later:** one library + a module and research folder per project now; split into repos once the library/project boundary has held up through a project or two.
  - **Sketch:**
    ```
    fxt-pixi/
        pixi.toml                  # one workspace, shared tasks
        src/fxt/                   # library: core, data (refdata, sources, ingest, lake), research
        src/fxtapps/               # shared CLIs
        projects/
            p01_single_pair/       # README (question, pre-registrations, results), own code, tests
            p02_all_pairs/
    data/                          # gitignored
        dataprep/  lake/           # shared
        projects/<name>/research/  # per-project config-hash tables
        projects/<name>/experiments.db
        lockbox.db                 # shared ledger of lockbox looks
    ```
  - **Rules:** imports only go one way (project → research → data → core), checkable with import-linter; projects use the library's public names only; project-specific config classes get a namespaced registry name (e.g. `p02.BasketStrengthConfig@1`) so projects can't collide; code starts in a project and moves into the library once a second project needs it; tag the commit when a project concludes (runs already store `code_version`).
  - **Cross-project statistics:** trials aren't independent across projects (p02 exists because of p01's results), and a lockbox look in one project affects related questions. Keep a shared lockbox ledger and have each project's README list the projects it builds on.
  - **Open:** per-project research tables (simpler) vs a shared hash-keyed cache with per-project registries (no rebuilding identical touch passes, less self-contained). Start per-project; share only if rebuild time hurts.

## Later / maybe

- 

root/
    pixi.toml
    
    #data storage
    data/                 # symlink → nvme, gitignored as /data
        ingest/
            downloads/source=…/market=…/symbol=…/interval=…/year=…/month=…/
        lake/
            raw/          # consolidator writes here directly
            derived/
    runs/
        p01_first/
            data/ #project-specific datalake?
            run.py #project-specific-code?
            experiments.db
            …
        lockbox.db 
    
    
    
    
    #code
    projects/
       p01_first/
       ...
       
    src/
        fxt/
            core/
            data/
                refdata/
                lake/ #move data.lake.models to data.models
                    derived/
                        bars.py
                        etc
                ingest/
                    downloaderapp.py
                    ConsolidatorApp.py
                    StorageManager.py
                    etc
                    
                sources/
                models/
                
            term/  #terminal utils
            research/  #shared research constructs
            
            fxt.toml
            settings.py
            .env
            notify.py
            descriptors.py
            ...
            
        fxtapps/
            reader/
                cli.py
            ingest/
                cli.py   #combine dl + con + verify into one app - eep
                #all shared assets should go to: fxt.data.ingest (storage manager, etc)
                
            derived/
                bars...
                
            research/
                ...
                
                
             


