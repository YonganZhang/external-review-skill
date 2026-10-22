#!/usr/bin/env python3
"""Summarize parent-agent dsh JSONL usage; never a billing reconciliation."""
import argparse
import json
import sys
from pathlib import Path

FIELDS = ('inputTokens', 'outputTokens', 'totalTokens', 'cacheReadTokens', 'cacheWriteTokens', 'reasoningTokens')
RATES = {'deepseek-flash': (1, .02, 4), 'deepseek-v4-pro': (4.5, .15, 13.5)}


def summarize(events, model):
    flags = set()
    started, ended, samples = set(), set(), []
    final_count = 0
    for event in events:
        if event.get('truncated'):
            flags.add('truncated_event')
        if event.get('type') == 'error':
            flags.add('run_error')
        if event.get('type') == 'status' and event.get('phase') == 'turn_end':
            reason = event.get('reason')
            if isinstance(reason, dict) and reason.get('kind') in ('error', 'aborted', 'interrupted'):
                flags.add('run_' + reason['kind'])
        if event.get('type') == 'final':
            final_count += 1
        if event.get('type') != 'status' or event.get('phase') not in ('step_start', 'step_end'):
            continue
        key = (event.get('turn'), event.get('step'))
        if any(type(value) is not int or value < 0 for value in key):
            flags.add('invalid_step_identity')
            continue
        if event['phase'] == 'step_start':
            if key in started or key in ended:
                flags.add('duplicate_step_start')
            started.add(key)
            continue
        if key in ended:
            flags.add('duplicate_step_end')
            continue  # Never count the same step twice.
        ended.add(key)
        if key not in started:
            flags.add('missing_step_start')
        usage = event.get('usage')
        if not isinstance(usage, dict) or not all(name in usage for name in FIELDS[:2]):
            flags.add('missing_usage')
            continue
        if any(type(usage[name]) is not int or usage[name] < 0 for name in FIELDS if name in usage):
            flags.add('invalid_usage')
            continue
        if usage.get('reasoningTokens', 0) > usage['outputTokens']:
            flags.add('inconsistent_reasoning')
        if 'totalTokens' in usage and usage['totalTokens'] < usage['inputTokens'] + usage['outputTokens']:
            flags.add('inconsistent_total')
        if 'totalTokens' in usage and all(name in usage for name in ('cacheReadTokens', 'cacheWriteTokens')):
            if usage['totalTokens'] != sum(usage[name] for name in ('inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens')):
                flags.add('inconsistent_total')
        samples.append(usage)
    if started - ended:
        flags.add('unfinished_steps')
    if not started or not ended:
        flags.add('no_steps')
    if final_count != 1:
        flags.add('missing_final' if not final_count else 'duplicate_final')
    totals = {name: sum(s[name] for s in samples) if samples and all(name in s for s in samples) else None for name in FIELDS}
    complete = not flags and len(samples) == len(ended)
    cost = None
    if model not in RATES:
        flags.add('unknown_model')
    elif complete:
        if totals['cacheReadTokens'] is None or totals['cacheWriteTokens'] is None:
            flags.add('cache_usage_unavailable')
        elif totals['cacheWriteTokens']:
            flags.add('cache_write_price_unavailable')
        else:
            miss, read, output = RATES[model]
            low = (totals['inputTokens'] * miss + totals['cacheReadTokens'] * read + totals['outputTokens'] * output) / 1_000_000
            cost = {'currency': 'CNY', 'idle': round(low, 12), 'peak': round(low * 2, 12)}
    return {
        'schema_version': 1, 'model': model, 'usage_scope': 'parent_only',
        'usage_complete': complete, 'step_count': len(ended),
        'started_step_count': len(started), 'usage_step_count': len(samples),
        'tokens': totals, 'input_tokens_semantics': 'uncached_input_excluding_cache_read_and_write',
        'estimated_cost_cny_range': cost,
        'pricing': {'as_of': '2026-10-22', 'source_url': 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
                    'unit': 'CNY_per_1M_tokens', 'idle_rates': dict(zip(('uncached_input', 'cache_read', 'output'), RATES[model])) if model in RATES else None,
                    'peak_multiplier': 2, 'basis': 'idle_to_peak_range_without_time_or_holiday_inference'},
        'flags': sorted(flags),
        'limitations': [
            'Parent headless stream excludes delegated child, provider title, and background usage.',
            'Reported tokens may be partial when usage_complete is false.',
            'Reasoning tokens are included in output tokens and are not charged again.',
            'Estimate is not total billed cost; discounts and account billing are not reconciled.',
            'Absent cache fields remain unknown; positive cache writes have no assumed price.',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog='Example: deepseek-usage.py --events events.jsonl --model deepseek-flash --out usage.json. Exit: 0 valid stream summary (possibly incomplete), 1 file/JSON error, 2 invalid arguments.')
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--model', required=True, help='Exact model route; unknown routes have no cost estimate.')
    parser.add_argument('--out', type=Path, help='Default: stdout')
    args = parser.parse_args(argv)
    try:
        events = []
        with args.events.open(encoding='utf-8') as source:
            for number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('non-finite JSON number')))
                except ValueError as exc:
                    raise ValueError(f'line {number}: invalid JSON: {exc}') from exc
                if not isinstance(event, dict):
                    raise ValueError(f'line {number}: expected JSON object')
                events.append(event)
        result = json.dumps(summarize(events, args.model), ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.out:
            if args.out.resolve() == args.events.resolve():
                raise ValueError('--out must differ from --events')
            args.out.write_text(result, encoding='utf-8')
        else:
            sys.stdout.write(result)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'deepseek-usage: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
