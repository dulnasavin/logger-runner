"""Exercise the actual GitHub-script fallback using an in-memory GitHub stub."""
import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/crypto_runner.yml'


class AlertFallbackTests(unittest.TestCase):
    def execute(self, provider=True, existing=False, **environment):
        name = '31.4 Create or update trusted Issue if provider delivery fails' if provider else '31.2 Create or update trusted Issue if workflow alert delivery fails'
        step = WORKFLOW.read_text().split('name: "' + name + '"', 1)[1].split('      - name:', 1)[0]
        script = textwrap.dedent(step.split('          script: |\n', 1)[1])
        harness = '''
const records = [];
const context = {repo:{owner:"example",repo:"logger"},runId:42};
const core = {warning:()=>{}};
const github = {
  rest:{issues:{getLabel:async()=>{},listForRepo:()=>{},
    create:async data=>{records.push(data);return {data:{number:1}};},
    createComment:async data=>{records.push(data);}}},
  paginate:async()=>EXISTING
};
(async()=>{SCRIPT})().then(()=>console.log(JSON.stringify(records))).catch(e=>{console.error(e);process.exit(1);});
'''
        # Match the marker at runtime without coupling the test to its hash.
        existing_fixture = '[{number:1,user:{login:"github-actions[bot]"},labels:["crypto-alert-fallback"],body:{includes:()=>true}}]' if existing else '[]'
        harness = harness.replace('EXISTING', existing_fixture).replace('SCRIPT', script)
        env = {**os.environ, 'ALERT_TYPE':'PRICE_SOURCE_INCIDENT', 'ALERT_SEVERITY':'WARNING',
               'ALERT_EVENT_ID':'a'*32, 'ALERT_FINGERPRINT':'b'*64,
               'LOGGER_RESULT':'success', 'CORE_VERIFICATION':'success', 'SYNC_RESULT':'success',
               'DELIVERY_ERROR':'MAKE_EMAIL_AUTH_INVALID_GRANT', **environment}
        result = subprocess.run(['node', '-e', harness], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)[0]

    def test_oauth_delivery_failure_preserves_successful_data_results(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                body = self.execute(existing=existing)['body']
                self.assertIn('CSV commit verification:** success', body)
                self.assertIn('Neon sync job:** success', body)
                self.assertIn('reauthorize Email send connection', body)
                self.assertIn('5967130/logs', body)

    def test_generic_http_does_not_claim_invalid_grant_was_observed(self):
        body = self.execute(DELIVERY_ERROR='MAKE_HTTP_ERROR')['body']
        self.assertIn('HTTP 500 alone does not prove', body)
        self.assertNotIn('Make reported invalid_grant', body)

    def test_neon_failure_is_not_mislabeled_email_failure(self):
        issue = self.execute(provider=False, SYNC_RESULT='failure', EMAIL_FAILED='false',
                             WORKFLOW_EMAIL_STATUS='accepted', DELIVERY_ERROR='')
        self.assertIn('NEON_SYNC_FAILED', issue['title'])
        self.assertNotIn('alert delivery failed', issue['title'])
        self.assertIn('explicit success acknowledgment', issue['body'])
        self.assertIn('Neon sync job:** failure', issue['body'])

    def test_untrusted_error_text_is_not_copied_to_public_issue(self):
        body = self.execute(DELIVERY_ERROR='private credential should never appear')['body']
        self.assertNotIn('private credential', body)
        self.assertIn('Delivery was not confirmed', body)

    def test_validation_failure_or_cancellation_is_reported_before_skipped_jobs(self):
        for status in ('failure', 'cancelled'):
            with self.subTest(status=status):
                issue = self.execute(provider=False, VALIDATION_RESULT=status,
                                     LOGGER_RESULT='skipped', SYNC_RESULT='skipped', CORE_VERIFICATION='',
                                     EMAIL_FAILED='false', WORKFLOW_EMAIL_STATUS='', DELIVERY_ERROR='')
                self.assertIn('PRODUCTION_VALIDATION_FAILED', issue['title'])
                self.assertIn('logger and email steps were not reached', issue['body'])
                self.assertNotIn('OAuth grant failed', issue['body'])
                self.assertIn('Neon sync job:** skipped', issue['body'])

    def test_checkpoint_failure_is_distinct_from_email_failure(self):
        issue = self.execute(provider=False, VALIDATION_RESULT='success', PROVIDER_ACK_FAILED='true',
                             EMAIL_FAILED='false', WORKFLOW_EMAIL_STATUS='not_required', DELIVERY_ERROR='')
        self.assertIn('PROVIDER_DELIVERY_CHECKPOINT_FAILED', issue['title'])
        self.assertIn('Email was accepted, but the delivery record was not saved', issue['body'])
        self.assertNotIn('alert delivery failed', issue['title'])

    def test_fallback_conditions_cover_failures_and_cancellations(self):
        workflow = WORKFLOW.read_text()
        fallback = workflow.split('  fallback-issues:', 1)[1]
        self.assertIn('- validate-invocation', fallback.split('    steps:', 1)[0])
        condition = fallback.split('        if: >-\n', 1)[1].split('        continue-on-error:', 1)[0]
        self.assertIn('always() &&', condition)
        for job in ('validate-invocation', 'run-logger', 'sync-neon'):
            for status in ('failure', 'cancelled'):
                self.assertIn(f"needs.{job}.result == '{status}'", condition)
        self.assertIn("needs.run-logger.outputs.provider_ack_failed == 'true'", condition)

    def test_issue_failure_marks_reporting_failed_but_success_or_skip_do_not(self):
        workflow = WORKFLOW.read_text()
        step = workflow.split('name: "31.7 Verify fallback reporting health"', 1)[1]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        self.assertNotIn('continue-on-error:', step)
        for workflow_result, provider_result in (('success', 'success'), ('skipped', 'skipped'),
                                                 ('failure', 'success'), ('success', 'failure'),
                                                 ('failure', 'failure'), ('cancelled', 'skipped'), ('', 'success')):
            with self.subTest(workflow=workflow_result, provider=provider_result), tempfile.TemporaryDirectory() as directory:
                summary = Path(directory) / 'summary'
                result = subprocess.run(['bash', '-c', script], text=True, capture_output=True,
                    env={**os.environ, 'GITHUB_STEP_SUMMARY': str(summary),
                         'WORKFLOW_FALLBACK_OUTCOME': workflow_result, 'PROVIDER_FALLBACK_OUTCOME': provider_result})
                expected_failure = any(value not in ('success', 'skipped') for value in (workflow_result, provider_result))
                self.assertEqual(result.returncode, int(expected_failure), result.stderr)
                self.assertEqual('::error::Alert fallback failed' in result.stdout, expected_failure)
                self.assertEqual('ACTION REQUIRED' in summary.read_text(), expected_failure)


if __name__ == '__main__':
    unittest.main()
