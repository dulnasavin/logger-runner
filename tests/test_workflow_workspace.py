"""Regression checks for job-local helper availability and snapshot persistence."""
import unittest
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[1] / '.github' / 'workflows'


class WorkflowWorkspaceTests(unittest.TestCase):
    def test_maintenance_job_checks_out_helpers_before_private_workspaces(self):
        workflow = (WORKFLOWS / 'csv_maintenance.yml').read_text()
        job = workflow.split('  maintain-runtime-data:', 1)[1]
        checkout = job.index('uses: actions/checkout@')
        private_checkout = job.index('name: Checkout pinned CSV integrity source')
        self.assertLess(checkout, private_checkout)
        public_checkout = job[checkout:private_checkout]
        self.assertIn('ref: ${{ github.sha }}', public_checkout)
        self.assertIn('persist-credentials: false', public_checkout)
        self.assertNotIn('repository:', public_checkout)
        self.assertNotIn('path:', public_checkout)

    def test_staging_runs_all_public_tests_at_the_triggering_commit(self):
        workflow = (WORKFLOWS / 'provider_resilience_gate.yml').read_text()
        checkout = workflow.split('02 Checkout public staging read-only', 1)[1]
        checkout = checkout.split('03 Validate', 1)[0]
        self.assertIn('ref: ${{ github.sha }}', checkout)
        self.assertIn("python -m unittest discover -s tests -p 'test_*.py' -v", workflow)

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

    def test_alert_acknowledgement_requires_verified_core_persistence(self):
        workflow = (WORKFLOWS / 'crypto_runner.yml').read_text()
        ack = workflow.split('31.5 Acknowledge and persist delivered provider event', 1)[1]
        ack = ack.split('SECTION 32', 1)[0]
        self.assertIn("steps.verify_core.outcome == 'success'", ack)
        self.assertIn('test "$(git rev-parse HEAD)" = "$VERIFIED_CORE_SHA"', ack)
        self.assertIn('test "$(git rev-parse "origin/$PRIVATE_DATA_BRANCH")" = "$VERIFIED_CORE_SHA"', ack)
        self.assertNotIn('git rebase', workflow)

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
