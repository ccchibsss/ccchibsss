# 12.9.161: Failed to read large IndexedDB value

## Report and confidence

User 12.9.160 log: first price Apply saved 122941 SKU. Second Apply completed
pre-save (0 changed products), then failed before reporting checkpoint completion.
Later attempts showed Connection is closing, revision conflicts and file-read
failures. The screenshot contains DatabaseClosedError → AbortError → DataError:
Failed to read large IndexedDB value.

This is not proof of another tab, quota exhaustion or an ordinary transient
abort. Exact failing store/key and the user's original data are unavailable.
An inaccessible Chromium/IndexedDB large-value backing file can have other
causes, including disk/profile problems. The original low-level Chromium error
has NOT been reproduced on the user's profile. Existing inaccessible records
are NOT repaired by this patch.

## Mitigation

Count-only packed pages could put 1000 wide rows into one stored value. Narrow
synthetic million-row checks did not cover that shape. New writes now use an
estimated UTF-16 JSON payload target of 512 KiB:

- Source row pages split by estimated bytes as well as row count. Existing
  variable-position pages-v1 readers require no source schema migration.
- Apply undo pages split similarly, using pages-v2 with row and page counts.
  Atomic restore validates positions/counts and still accepts old pages-v1 and
  row-per-record checkpoints. Failure leaves backup and pre-restore DB intact.
- Packed HVC chooses fixed pageSize 1..1000 from its widest logical row; load
  validates and uses the stored pageSize instead of hard-coding 1000. Existing
  pageSize=1000 registries remain readable. A save atomically replaces pages
  together with format metadata.
- Large-value read failures nested in DatabaseClosedError text are not treated
  as transient read errors. Auxiliary writes are not attempted after persistence
  reports a closing connection/large-value read failure. No freshness guard is
  bypassed and no stale revision is automatically accepted.
- File-picker rejection is caught after the existing error UI instead of being
  left as an additional unhandled promise rejection.

The byte estimate is NOT exact structured-clone/disk size. A SINGLE logical
row larger than the target is kept whole to preserve data. Such rows and large
individual metadata values still require separate treatment if implicated.
This change does not promise a hard per-record limit or fix arbitrary storage
corruption. Older app builds cannot necessarily read new checkpoint/layout
metadata; avoid concurrent old/new versions against one profile.

## Verification

- Node and console regression suites PASS.
- Eight fake-indexeddb integration suites PASS, including new wide Cyrillic
  source rows, variable undo page restore, HVC adaptive-page reopen and existing
  corruption/atomic rollback/legacy recovery checks.
- Real Chromium normal import smoke, enrichment parity, AbortError/atomic
  restore/manual restore, cross-tab conflict and CSV/XLSX export PASS.
- New real Chromium `tests/browser-wide-values-e2e.js` PASS: 1200 SKU with long
  Cyrillic names, 24 source pages and 28 product undo pages, followed by OE Apply.
  All names, prices and OE verified after DB reopen; no undo leftovers;
  economics remains pending. Added to CI.
- No new full 122941-SKU benchmark on the user's wide input was possible.

## Safe user recovery

Do not delete IndexedDB or keep pressing Apply. In the failing tab first try
Export → loaded/enriched data without economics → CSV (browser path reads RAM).
Keep the downloaded file and original inputs. Preserve the old profile/tab.
If this works, test the updated build in a separate clean browser profile with
no other app tabs, import the saved catalog as first price, then enrichment.
This isolates the old storage; it does not recover unexported data. Check free
system disk space as well as browser quota. If export fails, do not clear the
old storage: preserve originals and collect the full error for diagnosis.

## PR #98 CI follow-up

The full local Chromium CI sequence reproduced the red app check in the
30000-SKU partial-write scenario: `HVC page count mismatch`. The end-to-end
assertion still assumed `ceil(count / 1000)` after the writer switched to
adaptive page sizes. This was not a new observed field-loss or restore failure.
The assertion now validates pageSize (integer 1..1000), derives the page count
from stored metadata and checks every page's marker and exact length, including
the tail. The 30000-SKU partial-write/reopen scenario passes with these checks.
All preceding Chromium cases (index performance, enrichment parity, wide
values, repeat memory, abort/recovery, conflict, export, 1000-SKU smoke) and
Node/console regressions passed on this recheck. The million-row preflight is
rerun separately; its outcome and the new remote CI must be checked before merge.
