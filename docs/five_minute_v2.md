# Five-minute collector v2: activation and failure rules

The existing Main logger is authoritative while the protected collection mode
is `legacy`. A replacement cron-job.org entry targeting the new dispatcher is
prepared at minutes 03, 08, …, 58 but remains disabled. The old Main cron is
still enabled; no production cutover has occurred.

## Data contract

* Exactly one external cron request must go to the dispatcher for each slot;
  cron must never trigger Main 1, Main 2, or Main 3 directly. Invoke the
  dispatcher early enough to start its runner before the slot, provisionally
  two minutes ahead. At ten seconds before the slot, it inspects queued and
  running jobs, picks Main, Main 2, then Main 3, and creates one exclusive
  private claim for that slot. If Main finishes after Main 2 was claimed,
  Main 2 still owns the slot. An unassigned slot is reported to the persistent
  GitHub issue and must appear in the gap audit. Cron itself can silently miss
  an invocation, so an independent checker must enumerate expected UTC slots
  from a durable watermark rather than infer expected slots from workflow runs.
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
  one small ledger for the UTC slot. It does not rewrite the 102 growing
  monthly CSVs at every run. A changed remote head causes a fresh replay;
  force push is forbidden.
  A blank writer input reconciles up to 50 unapplied inbox receipts; run it
  again if a larger backlog remains. The collector queues this reconciliation
  after each durable receipt publication.
* The migration produces static per-symbol/year/month CSV baselines from
  the legacy file. A monthly closeout combines the baselines with the
  immutable receipts, verifies each ledger and gap, and builds 102 coin CSVs
  plus a manifest. A manual workflow stages the assets, uploads a draft
  private Release, downloads all 103 assets, and verifies their SHA-256 values
  before publication. A partial month stays labelled PARTIAL. Complete v2
  slot coverage still awaits exchange source comparison; a pre-cutover month
  is labelled BASELINE_ONLY_UNAUDITED.
  Migration also records a hashed six-hour history seed. Each v2 collector
  reads that seed and verified recent slot ledgers into a small local snapshot
  for provider consensus. It does not run a full legacy CSV preflight, copy
  price_log.csv, or run the complete test suite in every five-minute job.
  A synthetic 29-day benchmark measured about 54 MB of monthly content
  rewritten by one 102-coin update; that design is not suitable for active
  five-minute commits.
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
2. Rehearse migration on a frozen copy while legacy collection continues.
   Verify every original row, source hash, partition hash and generation.
   Keep price_log.csv and csv_state.json.
3. Run manual dispatcher tests on a disposable dataset for each lane,
   partial 99/102, whole-slot failure, duplicate, stale quote, concurrent push,
   and damaged partition. Inject delayed and stale GitHub run listings; verify
   that a busy Main cannot be assigned when Main 2 is free. Confirm writer
   commits and remote SHAs.
4. Before enabling the replacement cron, replace the current run-list-only
   lane choice with a durable lane occupancy record and completion or lease
   expiry/fencing rules. A stale Actions run list can otherwise assign an
   already busy Main while Main 2 is free, causing Main to queue. Test this
   with delayed API visibility, cancellation, late completion, and concurrent
   claims. Keep one exclusive claim per slot.
5. Exercise the independent
   expected-slot watchdog with a durable audit watermark, alert delivery,
   claimed-but-undispatched recovery, and outage replay. Test missed cron calls,
   a discarded queued Actions run, and a multi-day outage. The watchdog must
   inspect receipts and committed coverage, not merely green workflow results;
   it must never advance its watermark past an unaudited slot. Monitor writer
   backlog separately. This is a cutover gate, not a claim of punctuality.
6. Add actual per-market observation timing and provider/source provenance.
   The legacy timestamp assigned before provider calls is a batch label,
   not proof of the precise minute for every coin. Benchmark one month of
   receipt intake and test the closeout and restore before relying on it.
7. Verify the 48-hour repair horizon against
   actual Binance/Kraken source availability. A missed five-minute spot quote
   cannot be recreated as an identical quote after its instant has passed.
8. Test a monthly Release using disposable data and verify every downloaded
   asset. Complete source repair, partition-aware Audit and Maintenance,
   an independent backup, and a restore rehearsal before retiring legacy CSV.
9. After all gates pass, stop the old cron and drain old Main. Migrate the
   unchanged final CSV snapshot, verify the rows and hashes, set protected
   `v2` mode with the exact
    `first_slot_utc`, and enable the prepared dispatcher cron. A direct call
    to old Main or an unclaimed collector will then fail closed. Never switch
    the mode while an old Main run is still active.

## Failure and recovery

| Condition | Required outcome |
| --- | --- |
| Main/Main 2 occupied | Choose the next free lane only after cross-checking durable occupancy; an API list alone can be stale. |
| Cron request absent or GitHub drops a queued run | Independent watchdog records the expected slot as missing, alerts, and starts verified archival repair when available; do not report a fresh quote for an elapsed instant. |
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
claim is the assignment record; the API is only an occupancy hint. The
current draft has no durable per-lane occupancy record yet, so reliable
handoff under stale API visibility remains unimplemented. A direct
manual trigger or a late API response cannot authorize a different lane for
the same slot. Duplicate or conflicting receipts remain visible, and the
writer's receipt identity and slot checks are the final data guard.

## Reliability boundary

An exclusive private claim can enforce one assigned lane per slot when the
claim store is available. It cannot force cron-job.org or GitHub Actions to
start at an exact second. Both services can delay work; GitHub can discard a
queued job. The operational objective is therefore no silent missing slot,
no duplicate authoritative row, and bounded detection and repair once the
providers recover. A true wall-clock guarantee needs an always-on collector
and scheduler with independent power/network paths; even those cannot
manufacture an exchange quote that was never captured.

