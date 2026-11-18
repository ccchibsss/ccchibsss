# Enrichment key-index sorting — 12.9.168

The reported screenshot is in `BrowserImportSources.prepareKeys`, during external merge sorting of the enrichment source's conflict-detection keys. This is distinct from the boot enrichment fixed in 12.9.167. The source file is not available, so its specific 514-second runtime is not reproduced or explained solely by this test.

## Changes

- Build sorted runs spanning up to 16 source-page equivalents instead of one run per page. Also flush at an estimated 8 MiB of descriptor strings/overhead (key, brand, signature). Individual oversized descriptors remain intact. This is an allocation bound heuristic, not a browser heap guarantee.
- Keep output leaf size/format unchanged (`BATCH`, normally 1000), flushing writes in bounded batches of at most 16 initial leaves and eight merge leaves.
- Only await reads/writes at page boundaries in the merge hot loop, instead of two async calls for each key.
- Delete consumed runs in one transaction per merge group. Remove cleanup tracking only after successful commit.
- Show current merge group and group count, so progress updates even if local deduplication keeps each group below 16000 keys.

Conflict detection is not skipped. Signature strings are not truncated or replaced by hashes. Stable ordering and first representative selection are retained. No changes to match keys, economics, SQL/browser mode selection, import enrichment algorithms or database schemas. No catalog clearing.

## Verification

Sequential real Chromium runs against HEAD (12.9.167) and changed HTML, generated CSV with 962000 random rows / 523170 unique keys; independent expected signatures/brands/conflict flags verified for **every** unique key. Catalog pair/article lookup and temporary-index cleanup verified too.

| Phase | Before | After |
|---|---:|---:|
| Source staging | 6.350 s | 6.629 s |
| Source conflict-key index | 47.271 s | 37.663 s |
| Source lookups | 1.328 s | 1.556 s |
| Catalog indexes | 51.013 s | 39.864 s |
| Catalog lookups | 2.649 s | 2.829 s |
| Entire benchmark | 117.902 s | 98.146 s |

This benchmark is **not full Import.apply** and does not include actual enrichment/economics. Large-run lookups were ordered by key in both builds to measure index construction without random cache thrashing. Reproduce with `PERF_ROWS=962000 PERF_KEYS=700000 PERF_SORTED=1` and `tests/browser-key-index-perf-e2e.js`; `E2E_HTML` selects the comparison HTML. `PERF_TRACE=1` prints intermediate merge progress. The default CI probe still uses unordered queries.

Two earlier large probes with concurrent browsers/unordered queries were stopped before completing; their intermediate timings are not the before/after table above. Large randomized lookup workloads can still be slow once the bounded page cache is exceeded; this patch does not claim to fix that separate issue or all causes of slow imports.

Additional passing checks:
- fake-indexeddb key-page suite: exact cross-batch conflict/stable representative parity, cleanup on output failure and cancellation, persisted/reopened reads, cache invalidation, fewer sort runs, and new wide-signature byte-cap test.
- Default real Chromium performance/parity probe (30000 rows, unordered queries): PASS.
- Full staged-vs-array browser enrichment Apply parity, 4110 source rows / four subsequent files and reopening: PASS.
- Real Chromium + Python/SQLite paged import/enrichment/persistence: PASS.
- 31 client suites, main Node suite and `git diff --check`: PASS.
