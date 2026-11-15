# Five-minute collector v2: activation and failure rules

The existing Main logger is authoritative until a verified cutover. The four
new workflows are manual-only. No production schedule is configured.

## Data contract

* The dispatcher names a UTC five-minute slot and tries Main, Main 2, Main 3.
  It checks queued and running collector jobs. An unassigned slot is reported
  to the persistent GitHub issue and must appear in the gap audit.
* Each collector uses the same pinned private source, VPN, provider consensus,
  and 102-market roster. It writes one immutable receipt containing its slot,
  dispatch and observation times, valid rows, missing-symbol complement,
  source SHA and producer run ID. A partial receipt is published before the
  workflow fails visibly. A canceled run may have no receipt.
* All three collectors publish receipts to the private runtime-data branch
  using fast-forward commits. They never write the partition CSVs directly.
  The writer is a separate concurrency group with a maximum pending queue.
* The writer replays the selected receipt from the current branch head,
  validates the dataset generation and deletion tombstones, and commits
  per-symbol/year/month CSVs, daily ledgers and a hash manifest. A changed
  remote head causes a fresh replay; force push is forbidden.
  A blank writer input reconciles up to 50 unapplied inbox receipts; run it
  again if a larger backlog remains. The collector queues this reconciliation
  after each durable receipt publication.
* A receipt that finishes after its named slot is stored as late evidence.
  It does not count as an on-time observation in the gap audit.
* A five-minute quote and a reconstructed one-minute candle close are distinct
  observations. The current candidate assessor requires Binance and Kraken
  prices at the missing minute and observed five-minute anchors at -10, -5,
  +5 and +10 minutes. It rejects disagreement and has no automatic promotion
  into the price CSV. Source release retrieval, per-market tolerance review,
  publication, and later official archive verification remain to implement.

## Cutover gates

1. Merge and pin the tested private source commit in the protected public
   release manifest. Keep the old Main workflow active until the cutover.
2. Choose a cutover slot and stop the legacy Main dispatcher at that point.
   Do not reset or delete the existing CSV. Ensure no legacy run is still
   writing before starting migration.
3. Run the one-time migration against an unchanged runtime-data snapshot.
   It verifies every legacy row, the source hash, partition hashes and the
   generation. If the source changes during migration, it aborts; rerun from
   a fresh snapshot. Preserve price_log.csv and csv_state.json.
4. Verify the partition copy against the original count and SHA, including
   the deliberate deletion state. Run manual dispatcher tests for each lane,
   partial 99/102, whole-slot failure, duplicate, stale quote, concurrent push,
   and damaged partition. Confirm writer commits and remote SHAs.
5. Only then decide a dispatch frequency. Audit an explicit UTC slot range;
   a green workflow is not proof that 102 prices were observed. Monitor
   receipt backlog and pending-writer queue independently.
6. Implement and verify archival repair and monthly Releases before removing
   the legacy CSV. Keep an independent backup and a restore rehearsal.

## Failure and recovery

| Condition | Required outcome |
| --- | --- |
| Main/Main 2 occupied | Choose the next free lane. |
| All lanes occupied, dispatcher delayed, API unavailable | Fail the dispatch and record the slot; audit all 102 markets. |
| 99 valid prices | Persist those 99 with three named gaps; fail visibly after saving. |
| Collector canceled before receipt push | Audit marks the whole slot absent. |
| Receipt upload response lost | Fetch latest runtime-data; identical receipt is idempotent, conflicting bytes fail. |
| Writer push races with Main or another update | Fetch/reset and replay the same immutable receipt; never overwrite remote state. |
| Two different observations claim one symbol and slot | Stop and review both; never choose by arrival order. |
| Partition or ledger corruption, generation mismatch | Stop the writer/audit; restore from verified source and manifest. |
| Intentional deletion tombstone | Reject replay of that timestamp in the same generation. |
| Late quote | Preserve provenance but keep the nominal slot gap open. |
| Only one exchange or unmatched anchor | Keep the gap open; no interpolation or guessed value. |
| Writer queue exceeds GitHub's 100 pending maximum | Receipts remain durable; reconcile unprocessed receipts explicitly. |

The dispatcher sees GitHub's run API, which may lag. It is a routing hint,
not an atomic lock. Duplicate or conflicting receipts remain visible; the
writer's receipt identity and slot checks are the final data guard.
