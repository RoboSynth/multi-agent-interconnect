from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.external_rotation import run_once


class ExternalRotationTests(unittest.TestCase):
    def make_plan(self, directory, jobs):
        root = Path(directory)
        plan = root / 'plan.json'
        plan.write_text(json.dumps({'jobs': jobs, 'state_file': str(root / 'state.json'),
            'evidence_directory': str(root / 'evidence'), 'caller_script': str(root / 'caller.py'),
            'stop_at': '2080-01-01T00:00:00+00:00'}), encoding='utf-8')
        return plan

    @staticmethod
    def success():
        return SimpleNamespace(returncode=0, stdout=json.dumps({'status': 'completed',
            'task_id': 'real-result-task', 'product_count': 1,
            'products': [{'dataItems': [{'type': 'text', 'text': 'Useful result'}]}]}))

    def test_ticks_advance_queue_and_do_not_repeat_finished_jobs(self):
        jobs = [{'id': 'a', 'aic': 'service-a', 'name': 'A', 'request': 'First task'},
                {'id': 'b', 'aic': 'service-b', 'name': 'B', 'request': 'Second task'}]
        with tempfile.TemporaryDirectory() as directory:
            plan = self.make_plan(directory, jobs)
            with patch('ops.external_rotation.subprocess.run', return_value=self.success()) as child:
                first = run_once(plan)
                second = run_once(plan)
                final = run_once(plan)
            self.assertEqual((first['job_id'], second['job_id']), ('a', 'b'))
            self.assertEqual(child.call_count, 2)
            self.assertEqual(final['completed'], 2)
            self.assertEqual(final['status'], 'finished')
            self.assertEqual((Path(directory) / 'evidence/a/response.txt').read_text(), 'Useful result\n')

    def test_failed_service_is_skipped_while_other_service_runs(self):
        jobs = [{'id': 'a1', 'aic': 'service-a', 'name': 'A', 'request': 'First task'},
                {'id': 'a2', 'aic': 'service-a', 'name': 'A', 'request': 'Another task'},
                {'id': 'b1', 'aic': 'service-b', 'name': 'B', 'request': 'Different service'}]
        failed = SimpleNamespace(returncode=0, stdout=json.dumps({'status': 'timeout', 'product_count': 0}))
        with tempfile.TemporaryDirectory() as directory:
            plan = self.make_plan(directory, jobs)
            with patch('ops.external_rotation.subprocess.run', side_effect=[failed, self.success()]) as child:
                first = run_once(plan)
                second = run_once(plan)
            state = json.loads((Path(directory) / 'state.json').read_text())
            self.assertEqual(first['status'], 'timeout')
            self.assertEqual(second['job_id'], 'b1')
            self.assertEqual(child.call_count, 2)
            self.assertEqual(state['jobs']['a2']['status'], 'skipped_service_unavailable')

    def test_empty_completion_is_not_reported_as_a_useful_result(self):
        jobs = [{'id': 'empty', 'aic': 'service-a', 'name': 'A', 'request': 'Task'}]
        empty = SimpleNamespace(returncode=0, stdout=json.dumps({'status': 'completed', 'product_count': 0}))
        with tempfile.TemporaryDirectory() as directory:
            plan = self.make_plan(directory, jobs)
            with patch('ops.external_rotation.subprocess.run', return_value=empty):
                result = run_once(plan)
            status = run_once(plan, status_only=True)
            self.assertEqual(result['status'], 'completed_without_product')
            self.assertEqual(status['completed'], 0)

    def test_queue_completion_disables_its_own_timer(self):
        jobs = [{'id': 'last', 'aic': 'service-a', 'name': 'A', 'request': 'Last task'}]
        with tempfile.TemporaryDirectory() as directory:
            plan = self.make_plan(directory, jobs)
            data = json.loads(plan.read_text())
            data['timer_unit'] = 'incident-external-rotation.timer'
            plan.write_text(json.dumps(data), encoding='utf-8')
            with patch('ops.external_rotation.subprocess.run', side_effect=[self.success(), SimpleNamespace(returncode=0)]) as child:
                run_once(plan)
            self.assertEqual(child.call_args.args[0],
                             ['systemctl', 'disable', '--now', 'incident-external-rotation.timer'])


if __name__ == '__main__':
    unittest.main()
