# First-price startup fix — 12.9.167

## Identified path

The screenshot's exact progress string, `Обогащение Ozon и подготовка справочника · SKU …`, comes from `runPipeline(true)`'s SQL enrichment loop. `UI.boot` called the full pipeline for every restored row, with `skipEconomics` derived from `uc.econPending`. That flag disables economics, **not** name/category/Ozon enrichment or policies/rules. Thus the saved first price could enter an unrelated full-catalog enrichment during initialization even though its Import.apply price branch correctly skipped enrichment.

Initialization could additionally request deferred economics, and the post-boot hash restoration called normal `UI.go`, which could request it again for a restored calculation view. Navigating to Data also requested deferred economics despite being a source-data table.

## Changes

- Initialization restores storage, settings and existing HVC indexes, then prepares filters/table. It does **not** call the enrichment/calculation pipeline.
- Saved `uc.econPending` is retained. Initialization does not consume pending economics, including when a calculation route was restored.
- `UI.go(v, {restore:true})` restores a route without automatically starting pending economics. Pending calculation views show a notice and open Data instead of rendering/calculating stale output. A pending default dashboard also opens Data, so the first price is immediately visible; explicit calculation navigation remains available.
- Data navigation displays the imported source data without requesting economics. Explicit navigation to calculation sections still requests deferred calculation, and manual recalculation/enrichment and export calculation paths remain available.
- Avoid rendering the dashboard aggregation during startup when another section is active.
- The first-price import branch and subsequent enrichment algorithms are unchanged. Metadata initialization/migrations, storage checks, checkpoint recovery, saved registry loading, OE indexing and visibility synchronization retain their existing behavior. This is not an entirely mutation-free storage boot or a fully out-of-core implementation.

## Verification

`tests/browser-first-price-boot-e2e.js` starts a real Python HTTP engine with a temporary SQLite database, uses separate fresh Chromium processes for browser and SQL modes, applies a generated first-price CSV through the real mapping/Apply methods, opens Data, **reloads the document** with Data, Unit and Dashboard hash routes, checks persisted values and the pending flag. Instrumentation counts full pipeline, economics ensure, HVC enrichment, SQL Ozon enrichment and SQL recalculation calls: all zero throughout first import and startup. The test separately confirms that explicit calculation navigation still calls economics (stubbed only for that final check).

Local 60,000-row generated CSV run:

| Mode | Read + mapping + first Apply + Data | Real Data reload | Real Unit-route reload | Real Dashboard-route reload |
|---|---:|---:|---:|---:|
| Browser / IndexedDB | 31.179 s | 4.559 s | 6.830 s | 4.800 s |
| SQL / SQLite | 15.080 s | 8.279 s | 8.534 s | 8.454 s |

Times are from the test environment, include instrumentation and UI waits, and do not predict timings for the user's unavailable input files. No before/after claim is made against a measured old-build run. The important regression assertion is zero enrichment/economics calls during initialization, including after real reloads.

Other checks:
- Main Node suite and all 31 client suites: PASS.
- Real Chromium full array-vs-staged browser enrichment parity: PASS (4,110 source rows, four subsequent files, conflicts/custom fields/dimensions and reopening).
- Real Chromium + Python/SQLite paged SQL import/enrichment/new SKU/OE columns and persistence: PASS.
- Volatile-storage boot/import guard regression: PASS.
- The new 60,000-row browser+SQL first-price/reload test is registered in CI.
