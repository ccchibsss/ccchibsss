# IndexedDB import persistence: bounded writes and safe publication

The reported 96% / 740-second stall is not reproduced: the user's large CSVs are unavailable. That label previously covered products, auxiliary tables and HVC persistence without identifying the active phase.

## Changes

- Product writes use both a row ceiling and a 4 MiB estimated structured-clone payload budget. Estimation walks fields without a full JSON string. Oversized individual records are written alone, never truncated. Full and partial atomic paths also use the batch builder. A write exceeding the estimated byte budget uses short transactions even below the row-count threshold. Unchanged-baseline verification reads 32 records at a time.
- Large HVC saves use immutable pages and `pages-v2` metadata pointing to the active pages. Each changed page has its own transaction. All four registries are published by one small metadata transaction only after every page is written. Unchanged pages are reused. Old pages are garbage-collected in 100-key transactions after publication; cleanup failure does not report a committed generation as uncommitted. Failed pre-publication writes delete their own new pages. Abandoned pages from crashes are reclaimed on a later successful save.
- The HVC publication transaction verifies both catalog freshness and the previous HVC pointer, rejecting competing publications. Web Locks serialize HVC writers where supported; an in-tab promise queue is used otherwise. Readers load the pointer and pages in one readonly transaction. Legacy row and packed-v1 formats remain readable.
- Apply checkpoint creation no longer copies the entire catalog in one write transaction. It first reserves a preparation marker, then copies 32-record windows in short transactions, then publishes the complete checkpoint. Other-tab writers are blocked by the marker. Apply cannot mutate the catalog before preparation completes. Failure removes only its own preparation marker/backup. Startup discards interrupted *preparation* without replaying partial backup; completed checkpoints still use the existing confirmed recovery path.
- Checkpoint page sizing no longer allocates JSON strings. Progress identifies product writes, HVC preparation/writes and checkpoint table/position. Cancellation checks and event-loop yields occur between large HVC preparation/write batches and checkpoint windows.

## Checks

- `tests/product-byte-batches-client.js`: exact full/partial order/values, wide records, oversized record, cycles, binary and Map/Set estimation.
- `tests/product-key-reconcile-indexeddb.js`: bounded key reads, rollback, cancellation, retries, quota and stale revisions.
- `tests/persist-indexeddb-probe.js`: economy/staged, reopen/readback, injected auxiliary/registry failures. Also passed with `LARGE_PRICE_PROBE=1` (124,236 products), before the final baseline-read-window reduction.
- `tests/hvc-pages-indexeddb.js`: legacy migration, 20,003-entry registries, exact reopen, unchanged/delta page writes, late-failure rollback, corrupt/duplicate/missing pages, Apply undo of page pointers, shrink/empty and wide records.
- `tests/browser-apply-checkpoint-indexeddb.js`: bounded backup, atomic restore failures, quota/cancellation, cross-tab guard, crash/reopen, interrupted preparation discard, legacy undo and malformed backups.
- All 32 `tests/*client.js` suites passed (the initial run exposed a stale test stub; corrected and rerun).
- `node tests/run-tests.js` and `git diff --check` passed.

## Limits

These are synthetic Node/fake-indexeddb checks, not a Chromium RSS measurement or reproduction of the user's browser failure. A payload estimate is not a hard total-memory cap: original rows, import/enrichment maps, browser internals and an individually enormous record can still exhaust RAM. Small auxiliary metadata (including applicability/settings), full in-memory enrichment state and the atomic *restore* transaction are not converted into a fully out-of-core representation in this change. Crash leftovers can require extra disk until the next successful registry save. No original database was cleared. Do not interpret these changes as a guarantee against every browser OOM or disk failure.
