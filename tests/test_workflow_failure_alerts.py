"""Offline coverage for the default-branch workflow failure monitor."""
import importlib.util
import json
import os
import subprocess
import textwrap
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/workflow_failure_alerts.yml'
spec = importlib.util.spec_from_file_location('send_workflow_failure', ROOT / 'scripts/send_workflow_failure.py')
sender = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender)


class WorkflowFailureAlertsTests(unittest.TestCase):
    def execute(self, *, conclusion='failure', name='CSV Audit', repository='example/logger', jobs_error=False, issues_error=False, existing=False):
        step = WORKFLOW.read_text().split('      - name: Record the failed workflow independently of email', 1)[1].split('      - name:', 1)[0]
        script = textwrap.dedent(step.split('          script: |\n', 1)[1])
        fixture = {'conclusion':conclusion, 'name':name, 'repository':{'full_name':repository},
                   'id':42, 'run_attempt':2, 'run_number':123}
        harness = '''
const outputs={}, created=[];
const context={repo:{owner:'example',repo:'logger'},payload:{workflow_run:FIXTURE}};
const core={setOutput:(k,v)=>outputs[k]=v,warning:()=>{},notice:()=>{}};
const github={rest:{actions:{listJobsForWorkflowRunAttempt:()=>{}},issues:{listForRepo:()=>{},
  create:async data=>{if(ISSUES_ERROR) throw Error('issues unavailable');created.push(data);return {data:{number:9}};}}},
  paginate:async (method,args)=>{
    if(method===github.rest.actions.listJobsForWorkflowRunAttempt){
      if(JOBS_ERROR) throw Error('jobs unavailable');
      if(args.attempt_number!==2) throw Error('wrong attempt');
      return [{name:'Verify CSV',conclusion:'failure',steps:[{name:'Checkout',conclusion:'success'},
              {name:'Check generation',conclusion:'failure'}]}];
    }
    if(ISSUES_ERROR) throw Error('issues unavailable');
    return EXISTING ? [{number:9,user:{login:'github-actions[bot]'},body:'<!-- crypto-workflow-failure:42:2 -->'}] : [];
  }};
(async()=>{SCRIPT})().then(()=>console.log(JSON.stringify({outputs,created,error:false})))
.catch(()=>console.log(JSON.stringify({outputs,created,error:true})));
'''
        harness = harness.replace('FIXTURE', json.dumps(fixture)).replace('ISSUES_ERROR', str(issues_error).lower()).replace('JOBS_ERROR', str(jobs_error).lower()).replace('EXISTING', str(existing).lower()).replace('SCRIPT', script)
        result = subprocess.run(['node', '-e', harness], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_audit_failure_reports_original_run_and_first_failed_step(self):
        result = self.execute()
        self.assertFalse(result['error'])
        self.assertEqual(result['outputs']['required'], 'true')
        body = result['outputs']['body']
        self.assertIn('Verify CSV: failure; first stopped step: Check generation', body)
        self.assertIn('/actions/runs/42', body)
        self.assertIn('attempt 2', body)
        self.assertIn('does not establish that Main', body)
        self.assertEqual(len(result['created']), 1)

    def test_failure_conclusions_are_covered(self):
        for conclusion in ('failure', 'cancelled', 'timed_out', 'action_required', 'startup_failure'):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(self.execute(conclusion=conclusion)['outputs']['required'], 'true')

    def test_healthy_unknown_and_foreign_events_do_not_send(self):
        for changes in ({'conclusion':'success'}, {'conclusion':'skipped'}, {'conclusion':'neutral'},
                        {'name':'Workflow Failure Alerts'}, {'name':'Crypto Logger | Main'},
                        {'repository':'attacker/other'}):
            with self.subTest(changes=changes):
                result = self.execute(**changes)
                self.assertEqual(result['outputs']['required'], 'false')
                self.assertEqual(result['created'], [])

    def test_job_details_outage_does_not_hide_workflow_failure(self):
        result = self.execute(jobs_error=True)
        self.assertFalse(result['error'])
        self.assertIn('Job details unavailable', result['outputs']['body'])
        self.assertEqual(len(result['created']), 1)

    def test_issue_outage_still_prepares_independent_email(self):
        result = self.execute(issues_error=True)
        self.assertTrue(result['error'])
        self.assertEqual(result['outputs']['required'], 'true')
        self.assertIn('CSV Audit', result['outputs']['subject'])
        self.assertIn('/actions/runs/42', result['outputs']['body'])

    def test_monitor_rerun_reuses_trusted_incident_issue(self):
        result = self.execute(existing=True)
        self.assertFalse(result['error'])
        self.assertEqual(result['created'], [])
        self.assertEqual(result['outputs']['issue_number'], '9')

    def test_sender_uses_original_identity_and_preserves_content(self):
        env = {'FAILED_RUN_ID':'42', 'FAILED_RUN_ATTEMPT':'2', 'FAILED_RUN_NUMBER':'123',
               'FAILED_WORKFLOW_NAME':'Neon Audit | Weekly', 'FAILURE_SUBJECT':'audit failed',
               'FAILURE_BODY':'Open the failed step', 'GITHUB_RUN_ID':'999'}
        send = Mock()
        sender.send_failure(send, env)
        self.assertEqual(env['GITHUB_RUN_ID'], '42')
        self.assertEqual(env['GITHUB_RUN_ATTEMPT'], '2')
        self.assertEqual(env['GITHUB_WORKFLOW'], 'Neon Audit | Weekly')
        send.assert_called_once_with(subject='audit failed', body='Open the failed step',
                                     alert_type='WORKFLOW_EXECUTION_FAILED', severity='CRITICAL')

    def test_sender_rejects_missing_or_invalid_identity_without_sending(self):
        for run_id in ('', '0', '-1', '42\nprivate'):
            send = Mock()
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                sender.send_failure(send, {'FAILED_RUN_ID':run_id})
            send.assert_not_called()

    def test_monitor_executes_only_protected_code(self):
        workflow = WORKFLOW.read_text()
        self.assertIn('ref: ${{ github.sha }}', workflow)
        self.assertIn('ref: ${{ steps.release.outputs.private_code_sha }}', workflow)
        self.assertNotIn('workflow_run.head_sha', workflow)
        self.assertNotIn('download-artifact', workflow)
        self.assertNotIn('actions/cache', workflow)
        self.assertNotIn('workflow_dispatch:', workflow)
        for name in ('CSV Audit', 'CSV Maintenance', 'Neon Audit | Weekly', 'Neon Maintenance',
                     'Neon Schema | Controlled Migration', 'Crypto Logger | Staging', 'Workflow Security', 'CodeQL Advanced'):
            self.assertIn(f'      - "{name}"', workflow)

    def test_both_reporting_channels_failing_is_visible(self):
        step = WORKFLOW.read_text().split('      - name: Report notification delivery separately from the failed workflow', 1)[1].split('      - name:', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            for issue, email in (('success','success'), ('success','failure'), ('failure','success'),
                                 ('failure','failure'), ('failure','skipped')):
                with self.subTest(issue=issue,email=email):
                    env={**os.environ, 'GITHUB_STEP_SUMMARY':str(Path(directory)/'summary'),
                         'ISSUE_OUTCOME':issue,'EMAIL_OUTCOME':email,'ISSUE_NUMBER':'','ORIGINAL_RUN_ID':'42',
                         'NOTIFICATION_REQUIRED':'true'}
                    result = subprocess.run(['bash','-c',script],env=env,text=True,capture_output=True)
                    self.assertEqual(result.returncode, int(issue!='success' and email!='success'), result.stderr)
            # An early exception before the incident outputs exist must not look healthy.
            result = subprocess.run(['bash','-c',script],env={**env, 'NOTIFICATION_REQUIRED':'',
                'ISSUE_OUTCOME':'failure','EMAIL_OUTCOME':'skipped'},text=True,capture_output=True)
            self.assertEqual(result.returncode, 1, result.stderr)


if __name__ == '__main__':
    unittest.main()
