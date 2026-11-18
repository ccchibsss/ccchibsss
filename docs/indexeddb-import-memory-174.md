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

## Conflict follow-up

Exact unchanged baseline verification now preserves the existing catalog revision when products, custom metadata, settings and tariffs match. Previously the verification itself published a new revision and could invalidate another loaded tab without a catalog edit. Real stale revisions still fail closed; no automatic token adoption or overwrite was added. The conflict message describes a revision mismatch rather than asserting an unproven other-tab cause.

Validated with the IndexedDB persistence probe (unchanged token assertions) and real Chromium `browser-import-conflict-e2e.js`: no-op verification retains the token, a genuine second-tab write blocks stale Apply, and new-tab recovery preserves staged file/mapping/options and stale RAM. This does not establish which writer caused the user's screenshot.

## Follow-up: ordinary saves, own queue and WAL writer reservation

- Ordinary full browser saves now request exact unchanged verification by default (explicit `verifyUnchanged:false` remains available). This also covers pagehide saves: a no-op no longer rewrites the entire catalog or publishes a needless revision. Partial changed-list writes retain their existing fast path.
- Baseline verification now reads byte-budgeted batches (up to 1000 records / estimated 4 MiB), rather than issuing one read per 32 small products. Values are still compared exactly; neither catalogVersion nor fingerprints authorize skipping a write.
- Apply drains this tab's existing persistence queue and cancels its debounce before the first freshness check. The baseline save captures those pending edits; no external revision is silently accepted.
- Reproduced a separate Chromium SQL failure: `/catalog/enrich-category-kind` returned `database is locked`. Top-level enrichment previously opened a deferred SAVEPOINT, permitting a WAL read-to-write upgrade failure. It now starts `BEGIN IMMEDIATE` before reference/schema reads and commits/rolls back only its own transaction. Existing caller transactions keep savepoint semantics. Engine version: 12.9.174-pyengine-45.
- Updated large browser import assertions to inspect immutable `pages-v2` keys rather than assuming numeric v1 IDs. Registered byte-batch regression coverage in CI.

Validation for this follow-up:
- 277 Python tests passed, including a real two-connection/thread WAL test: enrichment waits before reading, sees the committed writer's value, and preserves caller work on failure.
- All 32 client suites and all eight CI IndexedDB integration suites passed.
- Real Chromium multi-tab conflict test passed, including default no-op save and dispatched pagehide retaining the revision; genuine concurrent edits still reject stale Apply, and new-tab recovery retains the source/mapping/options and old RAM.
- Real Python+Chromium paged SQL import passed after writer reservation (1200 products, 5001 enrichment source rows, further SKU/OE custom columns, no browser product persistence).
- Remaining browser smoke sequence passed through 60k first-price browser+SQL imports/reopen, volatile boot, key index, exact enrichment parity, both wide-value variants, repeated imports, abort/recovery, conflict and export, and 1000-row Apply. Its old v1-only 30k test assertion failed and was then corrected; that 30k full Apply/HVC reload/24k partial write test passed on rerun.
- Million-row source staging, preflight and target-index test passed (~167 seconds, no catalog Apply). This is not a million-row full-import claim.
- Initial worker-memory, Ozon streaming XLSX and 20k browser IO tests passed before the latest follow-up. No original user CSVs were available, so the screenshot's exact trigger remains unproven.
