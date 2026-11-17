# Memory audit: 12.9.166

Scope: follow-up to SQL import memory work in PR #103. No features removed, no browser calculation fallback added, no import economics enabled.

## Implemented

| Path | Previous redundant allocation | Change |
|---|---|---|
| `PyEngine._prepareOzonTyping` | Deep export drafts plus retained full canonical JSON for every pending row | Keep isolated deep drafts, but retain SHA-256 guards instead of full originals. Only one row's canonical JSON is temporary at a time. |
| `PyEngine.enrichRules` | Serialized, special-value-aware snapshots of all supplied rows | SHA-256 of the existing lossless rule encoding; preserve Date/NaN/Infinity change detection. Validate responses as before; do not retain empty patches. Check input/catalog row counts before publication as well. |
| `scenarioProfit`, `WhatIf.run` SQL branch | One monolithic JSON string of the entire catalog held throughout the request, then another for validation | Per-row SHA-256 guards. Validate array identity, length and every index, including sparse deletion. |
| `WhatIf.run` SQL branch | Unused browser tariff/category clones and `Uint32Array(rowCount*3)` | Allocate only after the SQL early return. Avoid 12,000,000 bytes of browser marks for 1,000,000 SQL rows, plus the unused clones. |
| `AnomalyOE.findSql`, `PyEngine._mergeProducts` | Temporary array of all `[key, value]` tuples passed into `new Map()` | Populate the same Map directly; preserve order and last-entry semantics. |

Guard memory remains proportional to row count, but not to the total length of descriptions, custom columns or OE lists. Deep export drafts and nonempty patches remain intentionally staged: removing them without another publication protocol would weaken isolation or atomicity.

## Validation

- Main Node suite: PASS.
- All 29 `*client.js` suites: PASS, including actual SQL scenario/WhatIf methods, nested modifications, insertion/removal/reorder/replacement/sparse deletion, special rule types and export draft isolation.
- Python discovery: 266 tests PASS (engine unchanged).
- Real Chromium + Python HTTP server + temporary SQLite: full paged import, new SKU/OE columns, ambiguous OE, SQLite reload, absence of browser catalog, import without economics: PASS.
- New CDP forced-GC probe on 5,000 generated wide rows: retained JSON snapshot guards **16,920,560 bytes**, compact row guards **360,148 bytes** (about 98% lower). Each approach has its own GC baseline. This is retained JS heap, not peak renderer RSS and not the user's files.
- Existing Chromium source/graph memory probes continue to pass.
- CI includes the new guard suite, export lifecycle and special rule tests.

## Remaining high-priority memory risks (not fixed in this change)

1. **Automatic dimension/OE reconciliation.** `dimensionOeSnapshot` materializes projected rows and arrays of `HVC.parts`, `byOe`, `oe`, `cross`; `dimensionOeRequest` serializes that entire snapshot. Automatic search may be followed by apply with another full snapshot. This is still a high-risk path after a large SQL import. Next step: immutable staged SQLite snapshot/session, bounded upload and session-based find/apply, with existing evidence/signature/revision checks. Do not just remove the snapshot or apply results in place on each request.
2. **Browser XLSX generation.** `OzonExport.generateXlsx` holds `allData`, SheetJS cell objects, styling data and final ZIP/output. Large width times row count can dominate memory. Next step: server/streaming writer with identical field values, numeric/text types, headers and highlighting. CSV already encodes in batches, but retains output chunks until Blob creation; it is not constant-memory disk streaming.
3. **Catalog still resident in the browser.** `S.rows`, underlying HVC maps and UI/worker copies remain. `readSqlCatalog` reconstructs the whole application catalog. A true hard upper bound needs paged SQL-backed views/search and engine-side transformations, not merely smaller upload batches.
4. **Full result staging.** `enrichHvcRows`, rule and Ozon enrichments stage nonempty results until all checks pass. These values are required for atomic publication, but the worst case is O(N) changed data. Replacing this safely needs server staging and an explicit publish/rollback protocol plus a paged UI model.
5. **Calculation/scenario transport.** `recalcAndApply` retains an all-results Map; SQL scenario requests still build complete `scenario_inputs` and their JSON. The snapshot guards fixed here remove one large duplicate, not the result/input collections. Next step: paged scenario inputs and results pinned to one immutable revision; do not weaken stale-result checks or expose partial results on network failure.

No guarantee of eliminating OOM at arbitrary catalog sizes is made. The measured changes remove specific redundant allocations; the remaining paths above need separate protocol/UI work and parity tests.

## Browser-mode follow-up

Implemented in the same 12.9.166 patch:

- FWorker now terminates its previous worker and clears pending callbacks/watchdogs on upload/filter exceptions, worker errors and timeout. Previously those paths discarded the JS reference without terminating the worker holding a catalog projection.
- Revoke the temporary worker script Blob URL after construction (also on constructor failure). Ignore delayed errors from a worker that has already been replaced.
- Memory-pressure refusal and switching to synchronous filtering release the existing worker projection. `applyFilter` no longer continues to filter in an empty/recreated worker if projection upload was refused or failed.
- Ozon XLSX standard-dimension highlighting rows are local to the export instead of retained globally as `_stdExportRows`. An export with no standard dimensions can no longer reuse a prior export's row list.

Additional validation:
- `browser-worker-memory-client.js`: 60 lifecycle/failure cycles covering constructor, upload, filter, runtime error, timeout and explicit release; checks worker termination, callback/watchdog cleanup, Blob URL revocation and pressure fallback. No heap byte estimate is inferred from mock tests.
- `browser-worker-memory-e2e.js`: real Chromium workers, 30,001 projected rows, three successful filtering/release cycles with exact index checks; fourth worker released on simulated memory pressure. Four created, four terminated. This proves lifecycle cleanup, not a bound on transient allocation peaks.
- All eight existing IndexedDB suites pass (staged sources, key pages, streamed HVC, HVC pages, Apply checkpoint/rollback, catalog lookup, persistence and key reconciliation).
- Real Chromium `browser-enrichment-parity-e2e.js`: full array-vs-staged Apply parity, 4,110 source rows, four subsequent files and reopening pass. First price is not enriched, custom fields and conflict handling agree, economics remains pending.
- Real Chromium `browser-export-e2e.js`: 1,000 rows, CSV and XLSX readback pass, leading-zero articles retained, long OE CSV and Excel overflow/retry behavior unchanged.

Remaining browser-specific risks: worksheet/ZIP materialization described above, catalog + worker projection during normal active filtering, and unacknowledged queued worker upload chunks (transferable buffers avoid a structured clone but are not backpressure). Browser checkpoint/source staging is paged; this is not a guarantee that the live catalog, graph, generated file or rendering/filter scratch arrays fit arbitrary RAM. Next safe improvements require bounded byte-budget batches/worker acknowledgements and a streaming export writer with exact parity, not removing rollback or silently truncating fields.

## Follow-up: acknowledged Worker and streamed Ozon XLSX

The earlier unacknowledged-upload and Ozon worksheet-materialization issues above have now been addressed:

- Exactly one Worker upload chunk is in flight. The Worker sends an ACK with upload ID, part, version and last-part flag only after parsing and indexing that chunk. The producer waits before encoding the next one. Each chunk is at most 2,000 rows and a conservative 1 MiB UTF-8 bound; an individually oversized row refuses Worker filtering and uses the unchanged synchronous path instead of truncation.
- Filtering is queued until the final ACK. Only the latest UI filter is kept during upload. Missing/wrong ACKs time out and terminate the projection; stale catalog revision/size aborts the transfer. Release clears upload/filter timers and queues.
- Worker keeps one uppercase search string, a boolean OE-presence flag and required filter/sort fields. Article/name/OE source strings already represented in the search string are dropped unless needed for the active sort. The main catalog is not changed.
- Default `OzonExport.generateXlsx` now serializes product rows incrementally to worksheet XML and synchronously incrementally compresses the archive. No asynchronous compression-worker backlog, whole product AOA, or whole product SheetJS cell graph is built. `_generateXlsxLegacy` is used with an empty product list to build only the four-row template and remains available as a parity oracle in tests.
- Template headers, column widths, markers, values, numeric/text types, ranges and conditional-formatting rules are retained. No full-archive unzip/re-zip after writing product rows: XML patching touches only the tiny empty template.
- Where OPFS is available, compressed ZIP bytes are flushed to `uc-export-temp-v1` in the browser's temporary file storage every 100 product rows; generation returns a disk-backed File. This is a generated export, not a persisted application catalog or checkpoint. Temporary files have the same ten-minute lifetime as the download retry link. A new export also removes expired own files older than 24 hours after interrupted sessions. Quota/write/cancellation errors abort and remove the temporary file rather than silently switching mid-write to memory.
- Where OPFS is unavailable (e.g. some local-file/private browser contexts), compatibility remains via compressed Blob parts; progress reports this limitation. That fallback still retains compressed output proportional to file size. The disk-backed guarantee is conditional on OPFS availability, not universal.

Validation added/updated:
- `browser-worker-memory-client.js`: ACK backpressure, 1 MiB bound, final-ACK filter dispatch, changed-catalog abort, upload/filter timeouts and lifecycle cleanup.
- Real Chromium Worker filtering on 30,001 rows continues to pass with ACK transfer.
- `browser-ozon-stream-xlsx-e2e.js`: 1,001 actual product rows; exact readback value and cell-type comparison against the legacy writer; exact conditional-formatting and worksheet-dimension comparison; leading-zero article, Unicode, XML characters and multiline values. OPFS returns File; portable Blob fallback also passes. A SheetJS instrumentation assertion confirms at most four header rows are materialized.
- `export-spool-client.js`: disk flush/close, expiry cleanup confined to own generated names, quota error/abort and no-OPFS fallback.
- Existing full Chromium browser enrichment and CSV/XLSX export suites continue to pass.

**Still not out-of-core:** neither `S.rows` nor the synchronous HVC Maps were removed. They are accessed synchronously throughout filtering, rendering, matching, donor selection and rule execution. Removing them requires changing those APIs and the UI to asynchronous paged access, with immutable snapshots for exact enrichment/rollback semantics. This patch does not pretend that terminating a Worker, streaming a file or persisting a checkpoint solves the live-catalog limit. Other XLSX producers (notably formula/economics workbooks) retain their existing implementation; their streaming ZIP paths must also be assessed separately.
