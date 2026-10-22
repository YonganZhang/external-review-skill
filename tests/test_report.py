import importlib.util
import pathlib
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('report', pathlib.Path(__file__).parents[1] / 'scripts/llm-report.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class ReportTests(unittest.TestCase):
    def test_strict_contract(self):
        base = 'JOB_ID: j\nPROVIDER: gemini\nCOMPLETION_STATUS: COMPLETE\nERROR_CLASS: NONE\n' + ''.join('\n## '+s+'\nActual evidence.\n' for s in r.SECTIONS)
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp)/'result.md'
            for text, expected in [(base,True),(base+'PROVIDER: codex\n',False),(base+'ERROR_CLASS: AUTH\n',False),(base+'COMPLETION_STATUS: FAILED\n',False),(base.replace('## Evidence\nActual evidence.','## Evidence\n'),False),(base.replace('JOB_ID: j','JOB_ID: wrong'),False)]:
                with self.subTest(text=text):
                    p.write_text(text)
                    self.assertEqual(r.validate(p,'j','gemini'),expected)

if __name__ == '__main__': unittest.main()
