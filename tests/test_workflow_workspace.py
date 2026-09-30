"""Regression checks for job-local helper availability and snapshot persistence."""
import unittest
import json
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[1] / '.github' / 'workflows'


class WorkflowWorkspaceTests(unittest.TestCase):
    def test_neon_maintenance_is_manual_and_passes_approval_values_as_data(self):
        workflow = (WORKFLOWS / 'neon_maintenance.yml').read_text()
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('schedule:', workflow)
        self.assertIn('--capability neon', workflow)
        self.assertIn('ref: ${{ steps.release.outputs.private_code_sha }}', workflow)
        self.assertNotIn('git push', workflow)
        self.assertNotIn('persist-credentials: true', workflow)
        step = workflow.split('name: Execute controlled archived-data maintenance', 1)[1]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1].split('      - name:', 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / 'private_source/Neon Weekly Audit/neon_maintenance.py'
            capture.parent.mkdir(parents=True)
            capture.write_text('import json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            reason = 'Review $(touch MUST_NOT_EXIST); literal input'
            env = dict(os.environ, OPERATION='purge-archived', GENERATION='4',
                       APPROVED_PLAN_ID='nmp-v1-' + 'a'*64, CONTINUATION_TOKEN='',
                       CONFIRMATION='PURGE_ARCHIVED_NEON_GENERATION', CHANGE_REASON=reason)
            result = subprocess.run(['bash', '-c', script], cwd=root, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = json.loads(result.stdout)
            self.assertEqual(args[args.index('--reason') + 1], reason)
            self.assertFalse((root / 'MUST_NOT_EXIST').exists())

    def test_maintenance_uses_verified_private_helpers_before_data_checkout(self):
        workflow = (WORKFLOWS / 'csv_maintenance.yml').read_text()
        job = workflow.split('  maintain-runtime-data:', 1)[1]
        source_checkout, rest = job.split('name: Checkout private runtime data', 1)
        self.assertIn('ref: ${{ env.PRIVATE_CODE_SHA }}', source_checkout)
        self.assertIn('path: private_source', source_checkout)
        self.assertIn('persist-credentials: false', source_checkout)
        self.assertIn('test "$(git -C private_source rev-parse HEAD)" = "$PRIVATE_CODE_SHA"', source_checkout)
        self.assertIn('test -s "private_source/Crypto Logger-Private Repo/manage_csv_file_lifecycle.py"', source_checkout)
        self.assertIn('python "private_source/Crypto Logger-Private Repo/manage_csv_file_lifecycle.py"', rest)

    def test_every_lifecycle_caller_uses_its_job_local_pinned_private_copy(self):
        for filename, source_dir, helper, expected_calls in (
            ('crypto_runner.yml', 'private_logger', 'manage_csv_file_lifecycle.py', 1),
            ('crypto_runner.yml', 'private_logger', 'csv_audit.py', 1),
            ('csv_maintenance.yml', 'private_source', 'manage_csv_file_lifecycle.py', 2),
            ('neon_reconciliation.yml', 'private_source', 'csv_audit.py', 1),
        ):
            with self.subTest(workflow=filename):
                workflow = (WORKFLOWS / filename).read_text()
                call = f'python "{source_dir}/Crypto Logger-Private Repo/{helper}"'
                self.assertEqual(workflow.count(call), expected_calls)
                self.assertNotIn('scripts/manage_csv_file_lifecycle.py', workflow)
                self.assertLess(workflow.index(f'path: {source_dir}'), workflow.index(call))

    def test_staging_runs_all_public_tests_at_the_triggering_commit(self):
        workflow = (WORKFLOWS / 'provider_resilience_gate.yml').read_text()
        checkout = workflow.split('02 Checkout public staging read-only', 1)[1]
        checkout = checkout.split('03 Validate', 1)[0]
        self.assertIn('ref: ${{ github.sha }}', checkout)
        self.assertIn("python -m unittest discover -s tests -p 'test_*.py' -v", workflow)

    def test_manual_csv_audit_preserves_preview_and_private_release_boundary(self):
        workflow = (WORKFLOWS / 'csv_audit.yml').read_text()
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('schedule:', workflow)
        self.assertIn('default: preview', workflow)
        self.assertNotIn('NEON_DATABASE_URL', workflow)
        self.assertIn('--capability runtime_maintenance', workflow)
        self.assertIn('ref: ${{ steps.release.outputs.private_code_sha }}', workflow)
        self.assertIn('merge-base --is-ancestor "$SOURCE_SHA" HEAD', workflow)
        preview, repair = workflow.split('name: Preview CSV recovery without saving', 1)[1].split(
            'name: Repair CSV and verify the saved commit', 1)
        self.assertNotIn('--publish', preview)
        self.assertNotIn('PRIVATE_DATA_TOKEN', preview)
        self.assertIn('--publish --github-summary', repair)
        self.assertNotIn('persist-credentials: true', workflow)
        self.assertNotIn('git push', workflow)
        self.assertNotIn('git rebase', workflow)
        self.assertIn('group: csv-audit', workflow)

    def test_current_neon_apply_requires_explicit_confirmation_and_no_stale_plan(self):
        workflow = (WORKFLOWS / 'neon_reconciliation.yml').read_text()
        step = workflow.split('name: "01 Validate protected request"', 1)[1].split(
            '      - name:', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        env = dict(os.environ, GITHUB_REF='refs/heads/main', OPERATION='check-and-apply',
                   APPROVED_PLAN_ID='', CONFIRMATION='APPLY_NEON_RECONCILIATION',
                   CHANGE_REASON='Check current data')
        def request(**changes):
            return subprocess.run(['bash', '-c', script], env={**env, **changes},
                                  capture_output=True, text=True)
        self.assertEqual(request().returncode, 0)
        for changes in ({'CONFIRMATION': ''}, {'APPROVED_PLAN_ID': 'nrp-v1-' + 'a' * 64},
                        {'CHANGE_REASON': '   '}, {'CHANGE_REASON': 'a' * 201},
                        {'CHANGE_REASON': 'line\nbreak'}, {'GITHUB_REF': 'refs/heads/staging'}):
            with self.subTest(changes=changes):
                self.assertNotEqual(request(**changes).returncode, 0)
        self.assertIn('--mode check-and-apply', workflow)

    def test_maintenance_refuses_to_rebase_stale_data(self):
        for name in ('csv_maintenance.yml',):
            with self.subTest(workflow=name):
                workflow = (WORKFLOWS / name).read_text()
                self.assertNotRegex(workflow, r'git rebase\b')
                self.assertIn('STARTING_DATA_SHA="$(git rev-parse HEAD)"', workflow)
                self.assertIn('test "$(git rev-parse "origin/$PRIVATE_DATA_BRANCH")" = "$STARTING_DATA_SHA"', workflow)
                self.assertLess(workflow.index('= "$STARTING_DATA_SHA"'), workflow.index('git push origin'))

    def test_audit_requires_private_verified_persistence_protocol(self):
        workflow = (WORKFLOWS / 'neon_reconciliation.yml').read_text()
        self.assertIn('test -s "private_source/Neon Weekly Audit/neon_persistence.py"', workflow)
        self.assertIn('--runtime-repository "${GITHUB_WORKSPACE}/private_data"', workflow)
        self.assertNotIn('git push', workflow)
        self.assertNotIn('git rebase', workflow)
        self.assertIn('Verified runtime-data commit', workflow)

    def test_alert_acknowledgement_requires_verified_incident_persistence(self):
        workflow = (WORKFLOWS / 'crypto_runner.yml').read_text()
        ack = workflow.split('31.5 Acknowledge and persist delivered provider event', 1)[1]
        ack = ack.split('SECTION 32', 1)[0]
        self.assertIn("steps.verify_core.outcome == 'success'", ack)
        self.assertIn("steps.persist_failed_incident.outcome == 'success'", ack)
        self.assertIn("steps.send_provider_alert.outputs.delivery_status == 'accepted'", ack)
        self.assertIn('persist-incident', ack)
        self.assertIn('--expected-state-file private_logger/provider_incident_state.json', ack)
        self.assertIn('--csv-state-file private_logger/csv_state.json', ack)
        self.assertIn('--acknowledge-event-file "$PROVIDER_EVENT_FILE"', ack)
        self.assertNotIn('git push', ack)
        self.assertNotIn('git rebase', workflow)

    def test_recorded_price_failure_uses_provider_alerts_and_other_failures_still_alert(self):
        workflow = (WORKFLOWS / 'crypto_runner.yml').read_text()
        step = workflow.split('name: "30.1 Determine whether human attention is required"', 1)[1]
        step = step.split('      # ===', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = dict(os.environ, RUNNER_TEMP=directory, JOB_STATUS='failure',
                       LOGGER_OUTCOME='failure', INCIDENT_CHECKPOINT_OUTCOME='success')
            alert = root / 'vpn-alert-type.txt'
            def classify(**changes):
                result = subprocess.run(['bash', '-c', script], env={**env, **changes},
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            classify()
            self.assertFalse(alert.exists())
            classify(INCIDENT_CHECKPOINT_OUTCOME='failure')
            self.assertEqual(alert.read_text().strip(), 'PRODUCTION_WORKFLOW_FAILED')
            classify(LOGGER_OUTCOME='success')
            self.assertEqual(alert.read_text().strip(), 'PRODUCTION_WORKFLOW_FAILED')
            (root / 'vpn-auth-recovery-failed').touch()
            classify()
            self.assertEqual(alert.read_text().strip(), 'VPN_AUTH_RECOVERY_FAILED')

    def test_recovery_notification_passes_workflow_validation_without_sending_email(self):
        workflow = (WORKFLOWS / 'crypto_runner.yml').read_text()
        step = workflow.split('name: "31.3 Send deduplicated price-source event alert"', 1)[1]
        step = step.split('      - name:', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notifier = root / 'private_logger/Crypto Logger-Private Repo/vpn_auth_recovery/alert_email.py'
            notifier.parent.mkdir(parents=True)
            notifier.write_text('print("offline notifier reached")\n')
            event = root / 'event.json'
            payload = {'event_type': 'PRICE_SOURCE_RECOVERED', 'severity': 'RECOVERY',
                       'event_id': 'a' * 32, 'fingerprint': 'b' * 64}
            env = dict(os.environ, PROVIDER_EVENT_FILE=str(event), GITHUB_OUTPUT=str(root / 'output'))
            event.write_text(json.dumps(payload))
            result = subprocess.run(['bash', '-c', script], cwd=root, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('offline notifier reached', result.stdout)
            event.write_text(json.dumps({**payload, 'event_type': 'PRICE_SOURCE_INCIDENT'}))
            result = subprocess.run(['bash', '-c', script], cwd=root, env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('offline notifier reached', result.stdout)

    def test_optional_email_failure_timeout_and_success_preserve_data_and_delivery_truth(self):
        workflow = (WORKFLOWS / 'crypto_runner.yml').read_text()
        for name, argument in (
            ('31.1 Send production failure or VPN recovery alert', 'ALERT_TYPE'),
            ('31.3 Send deduplicated price-source event alert', 'EVENT_TYPE'),
        ):
            step = workflow.split(f'name: "{name}"', 1)[1].split('      - name:', 1)[0]
            script = textwrap.dedent(step.split('        run: |\n', 1)[1])
            self.assertIn('continue-on-error: true', step)
            self.assertIn('timeout-minutes: 1', step)
            self.assertIn(f'timeout --kill-after=5s 45s python "$NOTIFIER" --alert-type "${argument}"', script)
            with self.subTest(step=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                notifier = root / 'private_logger/Crypto Logger-Private Repo/vpn_auth_recovery/alert_email.py'
                notifier.parent.mkdir(parents=True)
                csv = root / 'private_logger/price_log.csv'
                csv.write_text('verified committed batch stays intact\n')
                original = csv.read_bytes()
                event = root / 'event.json'
                event.write_text(json.dumps({
                    'event_type': 'PRICE_SOURCE_INCIDENT', 'severity': 'WARNING',
                    'event_id': 'a' * 32, 'fingerprint': 'b' * 64,
                }))
                alert = root / 'vpn-alert-type.txt'
                alert.write_text('PRODUCTION_WORKFLOW_FAILED\n')
                output = root / 'output'
                env = dict(os.environ, RUNNER_TEMP=directory, PROVIDER_EVENT_FILE=str(event),
                           GITHUB_OUTPUT=str(output), ALERT_MAKE_WEBHOOK_URL='offline',
                           ALERT_MAKE_API_KEY='offline')

                def run(**changes):
                    output.write_text('')
                    result = subprocess.run(['bash', '-c', script], cwd=root,
                                            env={**env, **changes}, capture_output=True,
                                            text=True, timeout=5)
                    self.assertEqual(csv.read_bytes(), original)
                    values = dict(line.split('=', 1) for line in output.read_text().splitlines())
                    return result, values

                notifier.write_text('print("ALERT_EMAIL_ERROR: Make/Outlook delivery failed with HTTP 500")\nraise SystemExit(1)\n')
                result, values = run()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('::warning::', result.stdout)
                self.assertEqual(values['delivery_status'], 'failed')
                self.assertEqual(values['required'], 'true')

                # Simulate the external deadline result without waiting or sending an email.
                commands = root / 'bin'
                commands.mkdir()
                deadline = commands / 'timeout'
                deadline.write_text('#!/bin/sh\n[ "$1" = --kill-after=5s ] && [ "$2" = 45s ] || exit 99\nexit 124\n')
                deadline.chmod(0o755)
                result, values = run(PATH=str(commands) + os.pathsep + env['PATH'])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(values['delivery_status'], 'failed')

                notifier.write_text('print("offline accepted")\n')
                result, values = run()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(values['delivery_status'], 'accepted')
                self.assertNotIn('::warning::', result.stdout)

                event.unlink()
                alert.unlink()
                result, values = run()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(values['required'], 'false')
                self.assertEqual(values['delivery_status'], 'not_required')
                self.assertNotIn('offline accepted', result.stdout)

    def test_optional_failures_cannot_relax_core_data_gates_or_hide_fallback(self):
        workflow = (WORKFLOWS / 'crypto_runner.yml').read_text()
        for name in ('24.1 Run price_logger.py on managed S2 network',
                     '26.1 Validate production CSV schema and new rows',
                     '28.2 Push only the unchanged runtime-data snapshot',
                     '29.1 Verify remote private runtime-data SHA',
                     'Run exact one-way Neon sync'):
            step = workflow.split(f'name: "{name}"' if name[0].isdigit() else f'name: {name}', 1)[1]
            step = step.split('      - name:', 1)[0]
            self.assertNotIn('continue-on-error: true', step.split('        run:', 1)[0], name)
        for name in ('32.1 Create structured production summary',
                     '33.1 Collect non-secret production diagnostics',
                     'Publish sanitized Neon handoff summary'):
            step = workflow.split(f'name: "{name}"' if name[0].isdigit() else f'name: {name}', 1)[1]
            step = step.split('      - name:', 1)[0]
            self.assertIn('continue-on-error: true', step)
            self.assertIn('timeout-minutes: 1', step)
        for sender in ('send_make_alert', 'send_provider_alert'):
            self.assertIn(f"steps.{sender}.outcome == 'failure' || steps.{sender}.outputs.delivery_status == 'failed' || steps.{sender}.outputs.delivery_status == 'pending'", workflow)
        sync_gate = workflow.split('  sync-neon:', 1)[1].split('    runs-on:', 1)[0]
        self.assertIn("needs.run-logger.outputs.core_commit_sha != ''", sync_gate)
        self.assertNotIn('send_provider_alert', sync_gate)
        self.assertNotIn("needs.run-logger.result == 'success'", sync_gate)
        fallback = workflow.split('  fallback-issues:', 1)[1]
        self.assertIn('continue-on-error: true', fallback.split('    steps:', 1)[0])
        self.assertIn("needs.run-logger.outputs.provider_alert_delivery_failed == 'true'", fallback)

    def test_notification_summary_reports_degraded_without_claiming_core_success(self):
        workflow = (WORKFLOWS / 'crypto_runner.yml').read_text()
        step = workflow.split('name: "31.6 Report optional notification health"', 1)[1]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1].split('      # ===', 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / 'summary'
            env = dict(os.environ, GITHUB_STEP_SUMMARY=str(summary),
                       WORKFLOW_EMAIL_STATUS='not_required', PROVIDER_EMAIL_STATUS='failed',
                       WORKFLOW_EMAIL_OUTCOME='success', PROVIDER_EMAIL_OUTCOME='success')
            result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('::warning::', result.stdout)
            self.assertIn('Provider event email: failed', summary.read_text())
            self.assertNotIn('CSV saved successfully', summary.read_text())
            result = subprocess.run(['bash', '-c', script],
                                    env={**env, 'PROVIDER_EMAIL_STATUS': 'accepted'},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('::warning::', result.stdout)

    def test_main_push_preserves_concurrent_reset_and_accepts_exact_retry(self):
        workflow = (WORKFLOWS / 'crypto_runner.yml').read_text()
        step = workflow.split('28.2 Push only the unchanged runtime-data snapshot', 1)[1]
        step = step.split('      # ===', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, local, other = root / 'remote.git', root / 'private_data', root / 'other'
            def git(path, *args):
                return subprocess.run(['git', '-C', str(path), *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git(root, 'init', '--bare', str(remote))
            git(root, 'clone', str(remote), str(local))
            git(local, 'config', 'user.name', 'Test')
            git(local, 'config', 'user.email', 'test@example.invalid')
            git(local, 'checkout', '-b', 'runtime-data')
            (local / 'price_log.csv').write_text('header\nold-row\n')
            git(local, 'add', '.')
            git(local, 'commit', '-m', 'Baseline')
            git(local, 'push', '-u', 'origin', 'runtime-data')
            git(root, 'clone', '--branch', 'runtime-data', str(remote), str(other))
            git(other, 'config', 'user.name', 'Test')
            git(other, 'config', 'user.email', 'test@example.invalid')
            (local / 'price_log.csv').write_text('header\nold-row\nnew-row\n')
            git(local, 'add', '.')
            git(local, 'commit', '-m', 'Collected batch')
            env = dict(os.environ, RUNNER_TEMP=str(root), PRIVATE_DATA_BRANCH='runtime-data',
                       GIT_TERMINAL_PROMPT='0')
            def push():
                return subprocess.run(['bash', '-c', script], cwd=root, env=env,
                                      capture_output=True, text=True)
            first = push()
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(push().returncode, 0)  # lost-response retry is safe
            git(other, 'pull', '--ff-only')
            (other / 'price_log.csv').write_text('header\n')
            git(other, 'add', '.')
            git(other, 'commit', '-m', 'Intentional reset')
            git(other, 'push')
            reset_sha = git(remote, 'rev-parse', 'runtime-data')
            rejected = push()
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('changed concurrently', rejected.stdout)
            self.assertEqual(git(remote, 'rev-parse', 'runtime-data'), reset_sha)
            self.assertEqual(git(remote, 'show', 'runtime-data:price_log.csv'), 'header')


if __name__ == '__main__':
    unittest.main()
