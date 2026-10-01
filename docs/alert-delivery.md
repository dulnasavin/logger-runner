# Repair and verify Crypto Logger email alerts

Logger data collection, CSV persistence, Neon sync, and email delivery have separate results. Check each job in the linked GitHub Actions run. A green logger job does not establish that an email reached the inbox. An email sent before the Neon job cannot report its final result.

## Repair the reported Make connection failure

For `Failed to verify connection ' Email send connection'. "invalid_grant"`:

1. In Make, open **Credentials > Connections** and locate **Email send connection**.
2. Choose **Reauthorize**, complete sign-in with the intended sending account, and then use **Verify**. A successful verification shows a green check.
3. Open the **Crypto Logger Email Alerts** scenario and confirm its email module uses that connection.
4. Review the failed executions in [scenario history](https://us2.make.com/2723330/scenarios/5967130/logs). A generic HTTP 500 in GitHub does not identify the connection failure by itself.

A GitHub restart or VPN change cannot renew the Make connection's OAuth grant. Do not copy passwords, API keys, webhook URLs, or tokens into issues or chat.

Source: [Make connection management documentation](https://help.make.com/connect-an-application).

## Required acknowledgment contract

Place Make's **Webhook response** module **after the email module succeeds**, with HTTP 200, JSON content type, and this body:

```json
{"ok": true}
```

Do not send that success response before the email module, from an ignored-error route, or when only queuing the webhook. Failure paths must return a non-success response. If a failure response can include an error code, use only a sanitized code such as `invalid_grant`, never raw credentials or the complete email.

The sender rejects an empty response, Make's plain `Accepted` response, malformed JSON, and any response without literal boolean `ok: true`. These leave the provider event pending and trigger the existing GitHub Issue fallback. This is an intentional change: configure the final response module before relying on the new sender. Otherwise even sent emails can remain unconfirmed and be retried.

An explicit success response confirms only what the configured Make scenario asserts. It cannot prove mailbox delivery. Check that the response is on the correct route and check the receiving mailbox during an authorized delivery test. Deduplicate successful sends by `event_id` if the scenario supports this, since a lost response can cause a retry of an email that was already sent. Do not deduplicate an attempt that failed before sending.

## Verify after repair and release

1. Complete an authorized alert test or inspect the next real incident notification. Confirm the email module and final response module both succeed in Make history, then confirm mailbox receipt.
2. In GitHub, verify the notification status and the separate logger/CSV/Neon results. Failed or unconfirmed provider events remain pending for an eligible retry with the same event ID; the existing retry interval is 30 minutes.
3. Check the trusted GitHub fallback issue if email is unavailable. It includes sanitized delivery diagnosis, CSV verification and Neon results, and the scenario-history link. GitHub fallback is best effort and requires working GitHub notifications to draw attention.
4. Confirm an incident email includes the actual provider/FX decision, selected price, trading gate, recorded VPN recovery attempts, event identity and timing, and action steps. Retries must retain those details.

Offline tests cover delivery acknowledgment and fallback behavior without sending mail. They do not reauthorize Make or verify real inbox delivery. Keep the dispatcher paused if functioning email alerts are a prerequisite for unattended operation.

## Failure coverage and limits

| Failure | Result and action |
| --- | --- |
| Production validation fails before collection | The separate fallback job records the validation failure and skipped downstream jobs. Open the validation job's first failed step. |
| Logger or Neon job fails or is cancelled | The fallback records each job's actual result. A failed email does not overwrite the data result. Cancellation reporting is best effort while GitHub still allows the fallback to run. |
| Expired/revoked Outlook authorization or rejected webhook credentials | No false delivery acknowledgment. Inspect Make's exact error and repair the affected connection or credential. A restart cannot renew revoked authorization. |
| HTTP 429 rate limit | Up to three attempts, with bounded delay (at most five seconds between attempts) and the same event ID. Make documents these requests as rejected by its rate-limit check. |
| Timeout, connection interruption, ambiguous HTTP error, or missing success JSON | Do not immediately repeat the POST: the email may already have been sent. Trigger fallback, keep provider events pending for the existing 30-minute eligible retry, and inspect Make history. This trades rapid recovery for fewer duplicate emails. |
| Email succeeds but the delivery checkpoint cannot be saved | Keep the accepted email result and report a separate checkpoint failure. The event can be retried later, so duplicate emails remain possible. |
| GitHub Issues API/permission failure | Attempt both applicable fallback reports, then fail the fallback job and add a clear run summary. Completed CSV and Neon jobs keep their own results. A failed workflow can notify only through configured, working GitHub notifications. |
| Error-code output file cannot be written | Preserve a sanitized failure in the log and return failure; the workflow's delivery status still routes to fallback. |

Automatic pending-event retries apply to provider incidents; workflow/Neon failures are also recorded through their separate fallback path. A saved GitHub issue/comment confirms storage only, not that somebody received or read a notification.

This is not an exactly-once or never-fail delivery system. The current three-module Make scenario has no persistent `event_id` deduplication, so a lost response or checkpoint can still produce a later duplicate. Make/Outlook outages, quotas, mailbox filtering, and revoked permissions can interrupt email. Invalid workflow YAML, a disabled dispatcher, exhausted runner capacity, forced cancellation, or a GitHub-wide outage can prevent the fallback from running at all. Detecting a system that never starts requires an independent heartbeat monitor outside GitHub and Make, with a separately authorized notification destination; that monitor is not configured by this change.

Sources: [Make webhook responses, queue limits and rate limits](https://help.make.com/webhooks), [GitHub cancellation behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-cancellation), [GitHub Actions notifications](https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-github-actions-notifications).

## Audit schedule and other workflow failures

cron-job.org owns the independent audit schedules in `Pacific/Auckland`:

| Job | Schedule | Dispatch operation |
| --- | --- | --- |
| CSV Audit | Daily, 02:45 (`45 2 * * *`) | `repair` |
| Neon Audit | Daily, 03:00 (`0 3 * * *`) | Existing `scheduled-apply` policy |

The user authorized recurring CSV `repair`, which publishes eligible verified recovery to `runtime-data`. Both audit schedules run daily. Conflicting data, changed runtime snapshots, pending maintenance or failed provenance checks stop repair rather than forcing changes. The cron jobs are not chained, so Neon is still dispatched if CSV Audit fails. A 15-minute head start is not a completion guarantee: runner capacity, queued same-workflow runs and service delays can affect execution time. Different workflow concurrency groups allow overlap; shared database locks and stale-data checks still prevent unsafe concurrent changes. Neon retains its own CSV pre-audit and stops unsafe reconciliation if that check fails.

Cron notification success means GitHub accepted the dispatch request, not that the workflow passed. `Workflow Failure Alerts` separately watches completed CSV Audit, CSV Maintenance, Neon Audit, Neon Maintenance, Neon Schema, Staging, Workflow Security and CodeQL runs in this runner repository. On failure, cancellation, timeout, startup failure or action-required conclusion it records a trusted GitHub issue and independently attempts email through the existing Make connection. Main keeps its in-run incident emails and fallback. Failed or interrupted Main runs now also receive a distinct FINAL workflow-outcome email with the first stopped stage and final job results, including downstream Neon failures. Successful Main runs do not trigger this final-failure alert.

The monitor reports the original run and attempt and the first stopped step in each failed job. It reads job metadata only and never downloads triggering-run artifacts, caches, raw logs or code. Public notification code comes from the default-branch `github.sha`; the email helper comes from the reviewed private release pin. Issues failure does not prevent email, and email setup/delivery failure does not remove the issue. If both channels fail, the notifier job fails visibly. Native GitHub notifications remain the backup for a failure of the notifier itself. Manual reruns can repeat an email after an uncertain prior send; event identity remains stable.

This coverage becomes active only after the notifier workflow is merged into the public default branch. It does not monitor the separate private repository's CI or a workflow that never starts, and it cannot guarantee inbox receipt. Keep GitHub Actions notifications enabled for those cases and use an independent heartbeat monitor for missing starts.

## Specific subjects and outcome evidence

Provider emails now name the affected symbols, missing/disagreeing sources and selected fallback or FX outcome. NEW, CHANGED, SEVERITY change, REMINDER, DELIVERY RETRY and RECOVERED are distinct subject markers. Recovery names the preceding incident when retained context is available. Unknown codes remain visible with an explicit unknown-cause explanation. Main passes only fixed stage names and outcome strings to the notifier; the final-workflow monitor also includes its first stopped stage in the subject. Existing delivery acknowledgment and provider deduplication are preserved. See the pinned private `ALERT_OUTCOMES.md` for the outcome matrix.
