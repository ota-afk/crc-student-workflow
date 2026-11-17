"""Manual check: run the question set through map_intent with the real model.

Makes paid API calls. Must not run in CI. Prints PASS or FAIL per question,
then the token use of the model calls. Optional: set INPUT_PRICE_PER_M and
OUTPUT_PRICE_PER_M (dollars per million tokens, from OpenAI's pricing page)
to also print a cost per 1,000 questions.
"""

import json
import os
import sys
from pathlib import Path

from openai import OpenAI

from student_workflow.ai_assistant import map_intent

ROOT = Path(__file__).resolve().parents[1]
RISKY = {'task_confirm_sevis_active'}


class CountingClient:
    """Wraps the OpenAI client and adds up the token usage of each call."""

    def __init__(self, client):
        self._client = client
        self.responses = self
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def parse(self, **kwargs):
        response = self._client.responses.parse(**kwargs)
        self.calls += 1
        usage = getattr(response, 'usage', None)
        if usage is not None:
            self.input_tokens += usage.input_tokens
            self.output_tokens += usage.output_tokens
        return response


def load_tasks() -> list[dict]:
    rules = json.loads((ROOT / 'data/rules/rules.json').read_text(encoding='utf-8'))
    return [
        {'id': t['id'], 'title': t['title'], 'high_risk': t['id'] in RISKY}
        for t in rules['tasks']
    ]


def outcome_of(result) -> str:
    message = result.message or ''
    if result.outcome == 'no_match' and 'English' in message:
        return 'language'
    if result.outcome == 'no_match' and 'personal details' in message:
        return 'rephrase'
    return result.outcome


def print_usage(counter: CountingClient) -> None:
    if counter.calls == 0:
        print('No model calls were made.')
        return
    avg_in = counter.input_tokens / counter.calls
    avg_out = counter.output_tokens / counter.calls
    print(f'Model calls: {counter.calls}')
    print(f'Tokens: {counter.input_tokens} in, {counter.output_tokens} out')
    print(f'Average per call: {avg_in:.0f} in, {avg_out:.0f} out')
    price_in = os.getenv('INPUT_PRICE_PER_M')
    price_out = os.getenv('OUTPUT_PRICE_PER_M')
    if price_in and price_out:
        per_call = avg_in * float(price_in) / 1e6 + avg_out * float(price_out) / 1e6
        print(f'Cost per 1,000 model calls: ${per_call * 1000:.4f}')


def main() -> int:
    key = os.getenv('OPENAI_API_KEY')
    if not key or not os.getenv('OPENAI_MODEL'):
        print('FAIL: Set OPENAI_API_KEY and OPENAI_MODEL in .env.')
        return 1
    tasks = load_tasks()
    questions = json.loads((ROOT / 'data/ai_test_questions.json').read_text(encoding='utf-8'))
    failures = 0
    with OpenAI(
        api_key=key, base_url='https://api.openai.com/v1', timeout=30, max_retries=0
    ) as real_client:
        counter = CountingClient(real_client)
        for item in questions:
            result = map_intent(item['q'], tasks, client=counter)
            got = outcome_of(result)
            ok = got == item['expect'] and (
                item['expect'] != 'matched' or result.task_id == item.get('task')
            )
            failures += 0 if ok else 1
            print(
                'PASS' if ok else 'FAIL', '|', item['q'][:50],
                '| expected', item['expect'], '| got', got, result.task_id or '',
            )
    print(f'{len(questions) - failures}/{len(questions)} passed')
    print_usage(counter)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
