"""Regression checks for job-local helper availability and snapshot persistence."""
import unittest
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

    def test_maintenance_and_audit_refuse_to_rebase_stale_data(self):
        for name in ('csv_maintenance.yml', 'neon_reconciliation.yml'):
            with self.subTest(workflow=name):
                workflow = (WORKFLOWS / name).read_text()
                self.assertNotRegex(workflow, r'git rebase\b')
                self.assertIn('STARTING_DATA_SHA="$(git rev-parse HEAD)"', workflow)
                self.assertIn('test "$(git rev-parse "origin/$PRIVATE_DATA_BRANCH")" = "$STARTING_DATA_SHA"', workflow)
                self.assertLess(workflow.index('= "$STARTING_DATA_SHA"'), workflow.index('git push origin'))


if __name__ == '__main__':
    unittest.main()
