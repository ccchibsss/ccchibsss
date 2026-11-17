# SQL import memory — 12.9.165

## Implemented

- SQL catalog import retains only a 200-row preview. Apply and its whole-file collision preflight request repeatable 4,000-row SQLite pages, not a complete parsed matrix. Auxiliary legacy parse callers keep their existing array contract.
- Source collision guards retain SHA-256 signatures of standard fields rather than references to entire input rows. Duplicate SKU conflicts are discovered before Apply, including duplicates on different pages. OE accumulation remains excluded from conflict signatures.
- HVC reference upload iterates existing Maps/Sets lazily instead of copying the entire graph into arrays. Per-row concurrent-change guards retain SHA-256 hashes rather than complete JSON snapshots.
- Ozon preferred-enrichment guards retain short canonical field values or hashes of large fields, preserving changed-field diagnostics without retaining complete large JSON snapshots. Empty Ozon patches are not retained.
- Ozon identity Maps/Sets are streamed as JSON arrays; reference upload makes bounded chunks rather than one full-graph JSON string. UTF-16 length accounting, Unicode surrogate boundaries, server validation, session reuse and release remain unchanged. A catalog/graph revision change during upload rejects the session before commit.
- Input signature maps are cleared immediately after preflight, and conflict/OE lookup/page data is released before HVC processing.
- HVC responses are still staged until all requests and concurrency checks pass. A late request failure or concurrent row edit does not publish partial enrichment. Empty patches are not retained.
- SQL catalog persistence remains SQLite-only; no source/catalog IndexedDB fallback or import economics was introduced.

## Reproducible checks

- `node tests/sql-memory-client.js`: 20,001 source rows, repeat iteration/page validation, SHA-256 comparison with Node crypto, lazy graph conversion, late HVC request failure and direct concurrent mutation.
- `node tests/hvc-chunked-client.js`: bounded upload, cleanup and atomic publication.
- `NODE_PATH=.arena/browser-tests/node_modules node tests/browser-sql-paged-import-e2e.js`: real Python HTTP server with a disposable SQLite database and real Chromium. Imports a 1,200-SKU price into an empty catalog, then 5,001 enrichment rows; checks cross-page conflicts, custom fields, leading-zero barcodes, OE accumulation, persisted reload, absent browser catalog/source and pending economics.
- The browser test also compares the legacy full-array parse API with the paged API on the same generated 20,001-row wide CSV. Each measurement uses CDP forced GC and the delta in retained JavaScript heap against its own baseline. Local Chromium run: **26,197,744 bytes legacy vs 217,104 bytes paged** (about 99% reduction for retained parsed-source heap). This is not renderer peak RSS or a measurement of the user's unavailable CSV.
- A second Chromium/CDP probe on 6,000 wide graph entries measured **20,179,804 bytes** for the retained monolithic JSON vs **400,056 bytes** maximum retained delta at streamed chunk boundaries. This measures GC-retained JS heap, not allocation peaks between chunk boundaries or total renderer RSS.
- All **27 `*client.js` suites**, main Node suite, import/export fixes and SQL catalog storage tests pass. Python discovery: **266 tests pass**.

The browser test uses playwright-core and @sparticuz/chromium (same dependency convention as existing browser tests). Local Linux environments may need Chromium's bundled shared libraries in LD_LIBRARY_PATH; GitHub Ubuntu uses its installed browser libraries. Tests are registered in tests.yml.

## Remaining limits — not a complete out-of-core implementation

The application still retains `S.rows`, HVC's underlying graph, per-SKU collision maps, and nonempty staged HVC result patches in browser memory. SQL catalog reload and persistence have not been redesigned here. Very large enriched catalogs can therefore still exceed browser memory. These changes remove demonstrated redundant source/graph/snapshot allocations; they do **not** prove that every SQL enrichment OOM is eliminated. Server-side result staging/publication and bounded catalog views would require further protocol/UI work without weakening rollback or conflict checks.

The import-status test was updated to match the existing restore/conflict action markup and bind the correct Apply handler (rather than the last handler in its extracted block); its mock now supplies boot/mode state. It passes in the 27-suite sweep.

## Enrichment keys and new columns

The import wizard accepts an OE-only enrichment file when a price catalog already exists; the first price still requires an article. Exact SKU matching has priority, followed by the existing OE fallback. Values from enabled new columns are registered in `S.custom` and written to the matched product's `custom` fields; source article/brand do not overwrite the price identity when matched through OE. No extra SKU is created by a subsequent enrichment file. Existing article-only compatibility mode is retained.

OE fallback now checks all supplied codes, not just the first matching code: a shared/ambiguous OE or codes pointing to different price rows reject that fallback. The same rule applies to the in-memory index and the paged IndexedDB catalog lookup.

`tests/import-enrichment-keys-client.js` checks both lookup implementations. The real Chromium/Python/SQLite integration additionally imports an OE-only Color column, a SKU+brand Material column and a supplier SKU matched by OE; validates unmatched/conflicting OE skips, preserved price identity/custom data and SQLite reload. The full client sweep now contains 28 passing suites.
