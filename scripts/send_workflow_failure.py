"""Send one sanitized workflow alert using the protected private email helper."""

import os
import sys
from pathlib import Path


def send_failure(send, environment):
    for key in ("FAILED_RUN_ID", "FAILED_RUN_ATTEMPT", "FAILED_RUN_NUMBER"):
        value = environment.get(key, "")
        if not value.isdecimal() or int(value) <= 0:
            raise ValueError("Missing or invalid failed-run identity")
    subject = environment.get("FAILURE_SUBJECT", "")
    body = environment.get("FAILURE_BODY", "")
    if not subject or not body:
        raise ValueError("Missing sanitized workflow alert content")
    # These are the original run's fields, so the helper's run URL, event ID
    # and email buttons point to the failing workflow rather than this monitor.
    environment.update({
        "GITHUB_RUN_ID": environment["FAILED_RUN_ID"],
        "GITHUB_RUN_ATTEMPT": environment["FAILED_RUN_ATTEMPT"],
        "GITHUB_RUN_NUMBER": environment["FAILED_RUN_NUMBER"],
        "GITHUB_WORKFLOW": environment.get("FAILED_WORKFLOW_NAME", "Workflow"),
        "CRYPTO_LOGGER_ENVIRONMENT": "WORKFLOW_MONITOR",
    })
    send(subject=subject, body=body, alert_type="WORKFLOW_EXECUTION_FAILED", severity="CRITICAL")


def main():
    helper_root = Path("private_notifier/Crypto Logger-Private Repo").resolve()
    sys.path.insert(0, str(helper_root))
    try:
        from vpn_auth_recovery.alert_email import send_high_priority_alert_email
        send_failure(send_high_priority_alert_email, os.environ)
    except Exception as error:
        known_codes = {"MAKE_EMAIL_AUTH_INVALID_GRANT", "MAKE_WEBHOOK_AUTH_REJECTED",
                       "MAKE_DELIVERY_UNCONFIRMED", "MAKE_HTTP_ERROR", "MAKE_NETWORK_ERROR",
                       "MAKE_TIMEOUT", "ALERT_CONFIGURATION_OR_CONTENT_ERROR"}
        code = getattr(error, "code", "ALERT_INTERNAL_ERROR")
        if code not in known_codes:
            code = "ALERT_INTERNAL_ERROR"
        print(f"WORKFLOW_ALERT_ERROR [{code}]: Email not confirmed; inspect notifier setup and Make history.", file=sys.stderr)
        return 1
    print("Make confirmed email-module success; inbox receipt is not verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
