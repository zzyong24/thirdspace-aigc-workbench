"""Fault and integration tests: dependency changes, locks, budget and recovery."""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'queue'))
import automation as runner
from storage import atomic_text, within


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aigc automation 空格 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'projects/demo-rooftop', self.root / 'projects/demo-rooftop')
        shutil.copytree(ROOT / 'queue', self.root / 'queue', ignore=shutil.ignore_patterns('node_modules', '__pycache__'))
        shutil.copytree(ROOT / '.agents', self.root / '.agents')
        self.job = {'id': 'render-demo', 'project': 'projects/demo-rooftop', 'action': 'render', 'depends_on': []}
        self.write_jobs([self.job])

    def write_jobs(self, jobs):
        (self.root / 'queue/automation.yaml').write_text(yaml.safe_dump({'version': 1, 'jobs': jobs}), encoding='utf-8')

    def ready(self):
        path = self.root / 'projects/demo-rooftop/assets/asset-matrix.yaml'
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        for a in data['assets']:
            a['status'] = 'uploaded'
        path.write_text(yaml.safe_dump(data), encoding='utf-8')

    def paid(self):
        path = self.root / 'queue/index.yaml'
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        data['execution_policy'].update(allow_existing_runninghub_points_at_21_00=True, point_budget_per_run=100)
        path.write_text(yaml.safe_dump(data), encoding='utf-8')
        self.ready()
        return {**self.job, 'action': 'generate_runninghub', 'shots': [1]}

    def test_real_execution_idempotent_and_reexecutes_changed_input(self):
        jobs = runner.jobs_from(self.root)
        first = runner.execute(self.root, jobs)
        self.assertEqual(first[0]['state'], 'done')
        with patch.object(runner, 'render_markdown', side_effect=AssertionError('duplicate')):
            self.assertEqual(runner.execute(self.root, jobs)[0]['state'], 'done')
        path = self.root / 'projects/demo-rooftop/prompts/shots.yaml'
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        data['shots'][0]['prompt'] += ' 改动'
        path.write_text(yaml.safe_dump(data), encoding='utf-8')
        self.assertEqual(runner.plan(self.root, jobs, runner.read_state(self.root))[0]['state'], 'ready')
        self.assertEqual(runner.execute(self.root, jobs)[0]['state'], 'done')
        self.assertIn('改动', (path.parent / 'shot-prompts.md').read_text(encoding='utf-8'))

    def test_dependency_topological_order_and_real_failed_readiness(self):
        ready = {'id': 'ready-demo', 'project': self.job['project'], 'action': 'check_ready', 'depends_on': ['render-demo']}
        self.write_jobs([ready, self.job])
        jobs = runner.jobs_from(self.root)
        self.assertEqual([j['id'] for j in jobs], ['render-demo', 'ready-demo'])
        outcome = runner.execute(self.root, jobs)
        self.assertEqual([r['state'] for r in outcome], ['done', 'failed'])
        self.assertIn('uploaded', outcome[1]['reason'])
        self.ready()
        # Failure is never silently retried even when data changes.
        self.assertEqual(runner.plan(self.root, jobs, runner.read_state(self.root))[1]['state'], 'failed')
        runner.recover(self.root, jobs, 'ready-demo', True)
        self.assertEqual([r['state'] for r in runner.execute(self.root, jobs)], ['done', 'done'])

    def test_changed_dependency_blocks_selected_downstream(self):
        downstream = {**self.job, 'id': 'next', 'depends_on': ['render-demo']}
        self.write_jobs([self.job, downstream])
        jobs = runner.jobs_from(self.root)
        runner.execute(self.root, jobs, 'render-demo')
        path = self.root / self.job['project'] / 'project.yaml'
        path.write_text(path.read_text(encoding='utf-8') + '\nnotes: new\n', encoding='utf-8')
        self.assertEqual(runner.execute(self.root, jobs, 'next')[0]['state'], 'waiting_dependency')

    def test_invalid_jobs_are_rejected_before_effects(self):
        variants = [
            [self.job, self.job], [{**self.job, 'action': 'shell'}],
            [{**self.job, 'project': '../outside'}], [{**self.job, 'enabled': 'yes'}],
            [{**self.job, 'depends_on': ['missing']}], [{**self.job, 'depends_on': ['render-demo']}],
            [{**self.job, 'action': 'generate_runninghub', 'shots': [True]}],
            [{**self.job, 'action': 'generate_runninghub', 'shots': [1, 1]}],
        ]
        for jobs in variants:
            with self.subTest(jobs=jobs):
                self.write_jobs(jobs)
                with self.assertRaises(ValueError):
                    runner.jobs_from(self.root)
        self.assertFalse((self.root / '.private').exists())

    def test_lock_prevents_second_runner_and_is_released_on_error(self):
        lock = self.root / '.private/automation/runner.lock'
        with runner.RunLock(lock):
            with self.assertRaisesRegex(ValueError, 'lock exists'):
                runner.execute(self.root, runner.jobs_from(self.root))
            with self.assertRaises(ValueError):
                runner.recover_lock(self.root)
        self.assertFalse(lock.exists())
        with self.assertRaises(RuntimeError):
            with runner.RunLock(lock):
                raise RuntimeError('injected')
        self.assertFalse(lock.exists())

    def test_write_ahead_interrupt_and_explicit_recovery(self):
        jobs = runner.jobs_from(self.root)
        with patch.object(runner, 'render_markdown', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runner.execute(self.root, jobs)
        self.assertEqual(runner.read_state(self.root)['jobs'][self.job['id']]['state'], 'failed')
        with self.assertRaises(ValueError):
            runner.recover(self.root, jobs, self.job['id'], False)
        runner.recover(self.root, jobs, self.job['id'], True)
        self.assertEqual(len(runner.read_state(self.root)['recoveries']), 1)
        self.assertEqual(runner.execute(self.root, jobs)[0]['state'], 'done')

    def test_browser_timeout_never_retries_or_changes_binding(self):
        job = {**self.job, 'action': 'inspect_runninghub'}
        directory = self.root / '.private/automation/projects/demo-rooftop'
        directory.mkdir(parents=True)
        binding = directory / 'browser.json'
        binding.write_text('{"spaceId": 123, "page": "p1"}', encoding='utf-8')
        with patch.object(runner, 'browser_inspect', side_effect=subprocess.TimeoutExpired('ego-browser', 1)):
            self.assertEqual(runner.execute(self.root, [job])[0]['state'], 'uncertain')
        with patch.object(runner, 'browser_inspect', side_effect=AssertionError('duplicate')):
            self.assertEqual(runner.execute(self.root, [job])[0]['state'], 'uncertain')
        runner.recover(self.root, [job], job['id'], True)
        self.assertEqual(json.loads(binding.read_text())['spaceId'], 123)

    def test_point_window_timezone_boundaries_and_budget(self):
        job = self.paid()
        # UTC 13:00 = Shanghai 21:00. End is exclusive.
        for hour, minute, allowed in ((12, 59, False), (13, 0, True), (13, 59, True), (14, 0, False)):
            now = datetime(2026, 10, 5, hour, minute, tzinfo=timezone.utc)
            with self.subTest(now=now):
                if allowed:
                    runner.point_gate(self.root, job, 50, now)
                else:
                    with self.assertRaisesRegex(ValueError, 'outside'):
                        runner.point_gate(self.root, job, 50, now)
        now = datetime(2026, 10, 5, 13, tzinfo=timezone.utc)
        for budget in (0, -1, True, 101):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                runner.point_gate(self.root, job, budget, now)
        path = self.root / 'queue/index.yaml'
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        data['execution_policy']['allow_existing_runninghub_points_at_21_00'] = 'true'
        path.write_text(yaml.safe_dump(data), encoding='utf-8')
        with self.assertRaises(ValueError):
            runner.point_gate(self.root, job, 50, now)

    def test_paid_jobs_cannot_run_in_bulk(self):
        job = self.paid()
        with patch.object(runner, 'generate', side_effect=AssertionError('unapproved')):
            self.assertEqual(runner.execute(self.root, [job])[0]['state'], 'waiting_authorization')
        self.assertEqual(runner.read_state(self.root)['jobs'], {})

    def test_agent_result_requires_all_shots_playable_evidence_and_audit(self):
        job = self.paid()
        directory = self.root / '.private/automation/projects/demo-rooftop'
        directory.mkdir(parents=True)
        (directory / 'shot.png').write_bytes(b'screenshot fixture')
        result = {'job_id': job['id'], 'status': 'generated', 'spent_points': 30, 'shots': [{'id': 1, 'node_id': 'original-node', 'playable': True, 'evidence': 'shot.png'}]}
        with self.assertRaisesRegex(ValueError, 'audit'):
            runner.validate_result(self.root, job, directory, result, 50)
        path = self.root / job['project'] / 'shot_audit.yaml'
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        data['records'][0]['state'] = 'generated'
        path.write_text(yaml.safe_dump(data), encoding='utf-8')
        runner.validate_result(self.root, job, directory, result, 50)
        for change in ({'job_id': 'wrong'}, {'spent_points': float('nan')}, {'spent_points': 100}, {'shots': []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.validate_result(self.root, job, directory, {**result, **change}, 50)
        for change in ({'playable': False}, {'evidence': '../outside.png'}, {'node_id': ''}, {'evidence': 'missing.png'}):
            altered = {**result, 'shots': [{**result['shots'][0], **change}]}
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.validate_result(self.root, job, directory, altered, 50)

    def test_doctor_missing_optional_runtime_is_actionable(self):
        with patch.object(runner.shutil, 'which', return_value=None):
            checks = runner.doctor(self.root, True)
        self.assertFalse(next(c for c in checks if c['name'] == 'ego-browser')['ok'])
        self.assertIn('lite.ego.app', next(c for c in checks if c['name'] == 'ego-browser')['detail'])

    def test_atomic_failure_keeps_previous_file_and_cleans_temporary(self):
        path = self.root / 'record.txt'
        path.write_text('old', encoding='utf-8')
        with patch('storage.os.replace', side_effect=OSError('injected disk error')):
            with self.assertRaises(OSError):
                atomic_text(path, 'new')
        self.assertEqual(path.read_text(encoding='utf-8'), 'old')
        self.assertEqual(list(self.root.glob('.record.txt*')), [])

    def test_paths_portable_and_absolute_drive_escape_rejected(self):
        for name in ('../out', 'C:/Users/private', 'C:relative', '\\server\\share', 'assets\\x.png', '/tmp/out'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                within(self.root, name)
        self.assertEqual(within(self.root, 'assets/my ref.svg'), self.root / 'assets/my ref.svg')

    def test_cli_dry_run_has_no_side_effect_and_unicode_path_executes(self):
        command = [sys.executable, str(self.root / 'queue/automation.py'), 'run']
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', cwd=self.root.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / '.private').exists())
        result = subprocess.run([*command, '--execute'], capture_output=True, text=True, encoding='utf-8', cwd=self.root.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(runner.read_state(self.root)['jobs'][self.job['id']]['state'], 'done')

    def test_ego_console_on_stderr_and_sanitized_environment_regression(self):
        job = {**self.job, 'action': 'inspect_runninghub'}
        directory = self.root / '.private/probe'
        directory.mkdir(parents=True)
        observed = {'spaceId': 17, 'url': 'https://www.runninghub.cn/', 'snapshot': 'visible live page'}
        result = subprocess.CompletedProcess([], 0, stdout='', stderr=json.dumps(observed) + '\n')
        with patch.object(runner.shutil, 'which', return_value='/fake/ego-browser'), patch.object(runner.subprocess, 'run', return_value=result) as run:
            report = runner.browser_inspect(self.root, job, directory, 10)
        self.assertEqual(report['spaceId'], 17)
        self.assertIn('const AIGC_BROWSER_REQUEST = ', run.call_args.kwargs['input'])
        self.assertNotIn('env', run.call_args.kwargs)
        self.assertEqual(json.loads((directory / 'observation.json').read_text(encoding='utf-8')), observed)

    def test_corrupt_state_and_cross_project_canvas_rejected(self):
        path = self.root / '.private/automation/state.json'
        path.parent.mkdir(parents=True)
        path.write_text('broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            runner.read_state(self.root)
        metadata = self.root / self.job['project'] / 'project.yaml'
        data = yaml.safe_load(metadata.read_text(encoding='utf-8'))
        for address in ('javascript:alert(1)', 'https://evil.example/secret', 'https://user:pass@runninghub.cn/projects/abc'):
            data['canvas_url'] = address
            metadata.write_text(yaml.safe_dump(data), encoding='utf-8')
            with self.subTest(address=address), self.assertRaises(ValueError):
                runner.canvas_url(self.root, {**self.job, 'action': 'generate_runninghub'})
        data['canvas_url'] = 'https://rhtv.runninghub.cn/projects/canvas/me'
        metadata.write_text(yaml.safe_dump(data), encoding='utf-8')
        self.assertEqual(runner.canvas_url(self.root, {**self.job, 'action': 'inspect_runninghub'}), data['canvas_url'])

    def test_cli_nonzero_failure_and_no_paid_watch(self):
        ready = {**self.job, 'action': 'check_ready'}
        self.write_jobs([ready])
        command = [sys.executable, str(self.root / 'queue/automation.py'), 'run', '--execute']
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stderr)
        result = subprocess.run([sys.executable, str(self.root / 'queue/automation.py'), 'watch', '--execute', '--point-budget', '50'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 2)
        self.assertIn('watch supports', result.stderr)

    def test_overnight_points_window_is_configurable_and_end_exclusive(self):
        job = self.paid()
        path = self.root / 'queue/index.yaml'
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        data['credit_queue_check_end'] = '10:00'
        path.write_text(yaml.safe_dump(data), encoding='utf-8')
        for now in (datetime(2026, 10, 5, 16, tzinfo=timezone.utc), datetime(2026, 10, 6, 1, 59, tzinfo=timezone.utc)):
            runner.point_gate(self.root, job, 50, now)
        with self.assertRaisesRegex(ValueError, 'outside'):
            runner.point_gate(self.root, job, 50, datetime(2026, 10, 6, 2, tzinfo=timezone.utc))

    def test_agent_failure_and_timeout_preserve_private_log_and_terminate(self):
        directory = self.root / '.private/probe'
        directory.mkdir(parents=True)
        schema, output = directory / 'schema.json', directory / 'out.json'
        schema.write_text('{}', encoding='utf-8')
        process = unittest.mock.Mock()
        process.returncode = 1
        with patch.object(runner.shutil, 'which', return_value='codex'), patch.object(runner.subprocess, 'Popen', return_value=process) as popen:
            with self.assertRaisesRegex(ValueError, 'structured result'):
                runner.invoke_agent(self.root, 'probe', schema, output, directory, 5, agent_model='user-model')
        args = popen.call_args.args[0]
        self.assertIn('read-only', args)
        self.assertIn('user-model', args)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)
        process.communicate.side_effect = subprocess.TimeoutExpired('codex', 1)
        process.pid = 999
        with patch.object(runner.shutil, 'which', return_value='codex'), patch.object(runner.subprocess, 'Popen', return_value=process), patch.object(runner.os, 'killpg', create=True) as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.invoke_agent(self.root, 'probe', schema, output, directory, 1)
        self.assertTrue((directory / 'agent-output.log').is_file())
        if os.name == 'nt':
            process.terminate.assert_called_once()
        else:
            kill.assert_called_once()
