# Five-minute collector v2: activation and failure rules

The existing Main logger is authoritative while the protected collection mode
is `legacy`. The new workflows are manual-only. No production schedule is
configured.

## Data contract

* Exactly one external cron request must go to the dispatcher for each slot;
  cron must never trigger Main 1, Main 2, or Main 3 directly. Invoke the
  dispatcher early enough to start its runner before the slot, provisionally
  two minutes ahead. At ten seconds before the slot, it inspects queued and
  running jobs, picks Main, Main 2, then Main 3, and creates one exclusive
  private claim for that slot. If Main finishes after Main 2 was claimed,
  Main 2 still owns the slot. An unassigned slot is reported to the persistent
  GitHub issue and must appear in the gap audit.
* A collector verifies that the private claim names its lane, slot, and
  dispatcher run before it starts. The protected mode file makes legacy Main
  and v2 mutually exclusive at invocation time. Completion estimates may be
  updated from recent runs for capacity planning, but the actual occupied state at the
  handoff decides routing. GitHub runner startup can be delayed, so a ten
  second check is a target, not a guaranteed execution time.
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
   release manifest. Keep the protected collection mode at `legacy` until
   cutover; v2 dispatches will fail closed meanwhile.
2. Stop the old cron URL that directly dispatches legacy Main, then wait for
   every legacy run to finish. Do not reset or delete the existing CSV.
3. Run the one-time migration against an unchanged runtime-data snapshot.
   It verifies every legacy row, the source hash, partition hashes and the
   generation. If the source changes during migration, it aborts; rerun from
   a fresh snapshot. Preserve price_log.csv and csv_state.json.
4. Verify the partition copy against the original count and SHA, including
   the deliberate deletion state. Run manual dispatcher tests for each lane,
   partial 99/102, whole-slot failure, duplicate, stale quote, concurrent push,
   and damaged partition. Confirm writer commits and remote SHAs.
5. Change the protected collection mode to `v2` and retarget the one external
   cron job to the dispatcher. An accidental call to old Main now fails before
   collection. An accidental direct call to a v2 collector fails without a
   valid private slot claim. The previous Main run must be drained before
   this switch because a run that already passed its gate can finish later.
6. Only then decide a dispatch frequency. Audit an explicit UTC slot range;
   a green workflow is not proof that 102 prices were observed. Monitor
   receipt backlog and pending-writer queue independently.
7. Implement and verify archival repair and monthly Releases before removing
   the legacy CSV. Keep an independent backup and a restore rehearsal.

## Failure and recovery

| Condition | Required outcome |
| --- | --- |
| Main/Main 2 occupied | Choose the next free lane. |
| Main finishes after Main 2's claim | Keep Main 2 as owner; Main does not start this slot. |
| Old cron still calls legacy Main after mode switch | Reject before collection and alert; retarget cron to the dispatcher. |
| Claim saved but workflow dispatch fails | Keep the claim and raise an incident. Check Actions for an existing run. If none exists, manually dispatch the claimed lane with the original claim run ID; do not assign a new lane. |
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

The dispatcher sees GitHub's run API, which may lag. The exclusive private
claim is the assignment record; the API is only an occupancy hint. A direct
manual trigger or a late API response cannot authorize a different lane for
the same slot. Duplicate or conflicting receipts remain visible, and the
writer's receipt identity and slot checks are the final data guard.
