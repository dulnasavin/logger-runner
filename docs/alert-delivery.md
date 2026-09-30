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
