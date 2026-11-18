# Key-index failure and checkpoint recovery follow-up

Reported screenshots show `Индекс ключей повреждён`, followed by a failed rollback reporting that no matching checkpoint exists. The user's database/CSV files are unavailable; the exact origin of either condition has not been established.

## Changes

- Key-page structural failures now carry `KeyIndexError` and bounded diagnostic context (run, first key, row count), not product payloads.
- Source-key reads can rebuild a malformed/incomplete derived index once from the immutable saved source and retry the read. The catalog Apply loop is never replayed. Original input pages, product data and undo remain untouched by the repair. Missing/unreadable source data still fails closed. A second repair request for the same retained run fails rather than looping.
- Target lookup indexes similarly get at most one rebuild from the lookup's frozen row-reference vector. Duplicate/ambiguous key semantics remain unchanged; boolean/ordering validation is not relaxed.
- Atomic restore writes an owner-specific durable receipt in the same transaction that removes its checkpoint/undo. Retrying a completed restore succeeds without replay only when there is no active checkpoint, no undo data, the receipt owner matches, and the catalog metadata still matches. Another owner or subsequent catalog revision is rejected.
- Preparation markers and old restore receipts are excluded from new metadata backups. Restoring application state no longer restores a transient preparation marker.
- Startup and Apply preparation reject orphan undo data without a checkpoint manifest rather than silently clearing the only backup on the next import. No manifest is fabricated from partial rows.
- Missing checkpoints get a distinct error and no automatic/manual retry-loop UI. Messages no longer assert that a missing checkpoint has been preserved. Writes remain blocked after failed rollback.

## Validation

- Main Node suite and all 32 client suites passed.
- Eight IndexedDB integration suites exercised. The key-page suite exposed a fixture without an immutable source; repair now verifies source availability before deleting any derived pages, and that suite passed on rerun. The other seven passed in the same run.
- Source-index test corrupts an actual stored record, rebuilds from the saved CSV and verifies cross-batch conflicts remain protected.
- Target-index test corrupts an actual page and verifies rebuilding retains RAM-lookup parity, duplicate and OE semantics.
- Checkpoint test injects an AbortError *after* atomic restore has committed. Retry uses the receipt, preserving restored data. Wrong owner and changed catalog are rejected; orphan backups survive startup/Apply refusal unchanged.
- Real Chromium `browser-import-abort-e2e.js` passed, including existing real transaction abort/manual recovery scenarios plus a malformed source index after an applied batch (read repair without Apply replay), and a late post-commit restore abort followed by receipt recovery and reload.
- HVC packed-page/Apply undo suite passed with the recovery receipt present.
- `git diff --check` passed.

This is synthetic fault injection, not reproduction of the user's exact database state. No guarantee that a genuinely missing checkpoint can be recreated is made. The application must retain orphan undo rows for diagnosis rather than clear them or guess their meaning.
