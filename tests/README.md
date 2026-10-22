# Synthetic regression tests

From the package root, run `python3 -m unittest discover -s tests -p 'test_*.py' -v` and `bash tests/test-llm-tmux-run.sh`.

Python tests cover provider selection, shared round input, partial failure, report validation, job identity and packet baselines/redaction/path handling. The shell suite starts isolated tmux sessions with stub provider CLIs and a temporary HOME; no production session is targeted and no model API is called. The suite requires a working tmux binary and GNU timeout.
