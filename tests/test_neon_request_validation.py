"""Execute the workflow's request gate without database access or secrets."""
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/neon_reconciliation.yml'
PLAN_ID = 'nrp-v1-' + 'a1' * 32


class NeonRequestValidationTests(unittest.TestCase):
    def validate(self, plan_id, **changes):
        workflow = WORKFLOW.read_text()
        step = workflow.split('      - name: "01 Validate protected request"', 1)[1].split('      - name:', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'outputs'
            environment = {**os.environ, 'GITHUB_REF': 'refs/heads/main',
                           'OPERATION': 'apply-approved-plan', 'APPROVED_PLAN_ID': plan_id,
                           'CONFIRMATION': 'APPLY_NEON_RECONCILIATION', 'CHANGE_REASON': 'Repair missing rows',
                           'GITHUB_OUTPUT': str(output), **changes}
            result = subprocess.run(['bash', '-c', script], env=environment, text=True, capture_output=True)
            return result, output.read_text() if output.exists() else ''

    def test_valid_id_is_preserved_and_trimmed_id_is_passed_to_apply(self):
        for value in (PLAN_ID, ' ' + PLAN_ID, PLAN_ID + ' ', '\t\r\n' + PLAN_ID + '\r\n\t',
                      '\u00a0' + PLAN_ID + '\u00a0', '\u2003' + PLAN_ID + '\u2003'):
            with self.subTest(value=repr(value)):
                result, output = self.validate(value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, f'approved_plan_id={PLAN_ID}\n')
                self.assertEqual('Ignored surrounding whitespace' in result.stdout, value != PLAN_ID)
        apply_step = WORKFLOW.read_text().split('      - name: "08 Reconcile and verify Git persistence before completion"', 1)[1].split('      - name:', 1)[0]
        self.assertIn('APPROVED_PLAN_ID: ${{ steps.request.outputs.approved_plan_id }}', apply_step)
        self.assertNotIn('inputs.approved_plan_id', apply_step)
        self.assertIn('--approved-plan-id "$APPROVED_PLAN_ID"', apply_step)

    def test_internal_whitespace_and_invalid_ids_are_rejected(self):
        for value in ('', ' \t\n', PLAN_ID[:20] + ' ' + PLAN_ID[20:], PLAN_ID[:20] + '\n' + PLAN_ID[20:],
                      PLAN_ID[:-1], PLAN_ID + 'b', PLAN_ID.upper(), PLAN_ID + '\nother_output=true',
                      'nrp-v1-' + 'g' * 64, '\u200b' + PLAN_ID):
            with self.subTest(value=repr(value)):
                result, output = self.validate(value)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, '')

    def test_trimming_does_not_relax_confirmation_or_protected_branch(self):
        for changes in ({'CONFIRMATION': ''}, {'CONFIRMATION': 'APPLY_NEON_RECONCILIATION '},
                        {'GITHUB_REF': 'refs/heads/staging'}, {'CHANGE_REASON': ''}):
            with self.subTest(changes=changes):
                result, output = self.validate(' ' + PLAN_ID + ' ', **changes)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, '')

    def test_other_modes_do_not_export_or_accept_an_approved_plan(self):
        for operation in ('check-and-apply', 'scheduled-apply'):
            fields = {'OPERATION': operation}
            if operation == 'scheduled-apply':
                fields.update(CONFIRMATION='', CHANGE_REASON='')
            with self.subTest(operation=operation):
                result, output = self.validate(' \t\n', **fields)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, '')
                result, output = self.validate(PLAN_ID, **fields)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, '')
        result, output = self.validate('anything\nother_output=true', OPERATION='preview')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, '')


if __name__ == '__main__':
    unittest.main()
