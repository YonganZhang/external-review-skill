"""Public CLI accounting checks using synthetic official dsh JSONL shapes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/deepseek-usage.py'


def stream(usage=None):
    return [
        {'type': 'session', 'sessionId': 'synthetic'},
        {'type': 'status', 'phase': 'turn_start', 'turn': 1},
        {'type': 'status', 'phase': 'step_start', 'turn': 1, 'step': 1},
        {'type': 'text', 'text': 'review'},
        dict(type='status', phase='step_end', turn=1, step=1, **({'usage': usage} if usage is not None else {})),
        {'type': 'status', 'phase': 'turn_end', 'turn': 1, 'reason': {'kind': 'completed'}},
        {'type': 'final', 'text': 'review'},
    ]


USAGE = dict(inputTokens=100, outputTokens=50, totalTokens=1150, cacheReadTokens=1000, cacheWriteTokens=0, reasoningTokens=30)


class UsageCLI(unittest.TestCase):
    def invoke(self, events, model='deepseek-flash', output=False, raw=None):
        with tempfile.TemporaryDirectory() as temp:
            events_path = Path(temp) / 'events.jsonl'
            events_path.write_text(raw if raw is not None else ''.join(json.dumps(e) + '\n' for e in events), encoding='utf-8')
            command = [sys.executable, str(SCRIPT), '--events', str(events_path), '--model', model]
            if output:
                command += ['--out', str(Path(temp) / 'usage.json')]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            payload = (Path(temp) / 'usage.json').read_text() if output and result.returncode == 0 else result.stdout
            return result, json.loads(payload) if payload else None

    def test_success_cache_and_reasoning_are_disjoint(self):
        result, data = self.invoke(stream(USAGE), output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertTrue(data['usage_complete'])
        self.assertEqual(data['tokens'], USAGE)
        self.assertEqual(data['usage_scope'], 'parent_only')
        self.assertEqual(data['estimated_cost_cny_range'], {'currency': 'CNY', 'idle': .00032, 'peak': .00064})

    def test_second_model_and_multiple_steps(self):
        events = stream(USAGE)
        events[5:5] = [dict(type='status', phase='step_start', turn=1, step=2), dict(type='status', phase='step_end', turn=1, step=2, usage=USAGE)]
        _, data = self.invoke(events, 'deepseek-v4-pro')
        self.assertTrue(data['usage_complete'])
        self.assertEqual(data['step_count'], 2)
        self.assertEqual(data['tokens']['outputTokens'], 100)
        self.assertEqual(data['estimated_cost_cny_range']['idle'], .00255)

    def test_duplicate_never_double_counts(self):
        events = stream(USAGE)
        events.insert(5, events[4].copy())
        _, data = self.invoke(events)
        self.assertFalse(data['usage_complete'])
        self.assertIn('duplicate_step_end', data['flags'])
        self.assertEqual(data['tokens']['inputTokens'], 100)
        self.assertIsNone(data['estimated_cost_cny_range'])

    def test_incomplete_valid_streams(self):
        cases = [(stream(), 'missing_usage'), (stream(USAGE)[:4], 'unfinished_steps')]
        events = stream(USAGE)
        events[3]['truncated'] = True
        cases.append((events, 'truncated_event'))
        events = stream(USAGE)
        events.insert(5, {'type': 'error', 'message': 'provider failed'})
        cases.append((events, 'run_error'))
        events = stream(USAGE)
        events[5]['reason'] = {'kind': 'error', 'error': {'message': 'failed', 'code': 'UNKNOWN'}}
        cases.append((events, 'run_error'))
        events = stream(dict(USAGE, inputTokens=True))
        cases.append((events, 'invalid_usage'))
        events = stream(dict(USAGE, totalTokens=1))
        cases.append((events, 'inconsistent_total'))
        events = stream(USAGE)
        del events[2]
        cases.append((events, 'missing_step_start'))
        for events, flag in cases:
            with self.subTest(flag=flag):
                result, data = self.invoke(events)
                self.assertEqual(result.returncode, 0)
                self.assertFalse(data['usage_complete'])
                self.assertIn(flag, data['flags'])
                self.assertIsNone(data['estimated_cost_cny_range'])

    def test_cache_unknown_writes_unknown_and_model_unknown(self):
        cases = [(dict(inputTokens=3, outputTokens=1), 'deepseek-flash', 'cache_usage_unavailable'),
                 (dict(USAGE, cacheWriteTokens=1, totalTokens=1151), 'deepseek-flash', 'cache_write_price_unavailable'),
                 (USAGE, 'unknown-model', 'unknown_model')]
        for usage, model, flag in cases:
            with self.subTest(flag=flag):
                _, data = self.invoke(stream(usage), model)
                self.assertTrue(data['usage_complete'])
                self.assertIsNone(data['estimated_cost_cny_range'])
                self.assertIn(flag, data['flags'])

    def test_malformed_files_fail_and_stdout_empty(self):
        for raw in ('{"type":', '[]\n', '{"type": NaN}\n'):
            result, data = self.invoke([], raw=raw)
            self.assertEqual(result.returncode, 1)
            self.assertIsNone(data)
            self.assertIn('line 1', result.stderr)

    def test_missing_file_and_help(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--events', '/no/such/fixture', '--model', 'unknown'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        result = subprocess.run([sys.executable, str(SCRIPT), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('Example:', result.stdout)


if __name__ == '__main__':
    unittest.main()
