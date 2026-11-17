"""Manual check: run the question set through map_intent with the real model.

Makes paid API calls. Must not run in CI. Prints PASS or FAIL per question.
"""

import json
import sys
from pathlib import Path

from student_workflow.ai_assistant import map_intent

ROOT = Path(__file__).resolve().parents[1]
RISKY = {'task_confirm_sevis_active'}


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


def main() -> int:
    tasks = load_tasks()
    questions = json.loads((ROOT / 'data/ai_test_questions.json').read_text(encoding='utf-8'))
    failures = 0
    for item in questions:
        result = map_intent(item['q'], tasks)
        got = outcome_of(result)
        ok = got == item['expect'] and (
            item['expect'] != 'matched' or result.task_id == item.get('task')
        )
        failures += 0 if ok else 1
        print('PASS' if ok else 'FAIL', '|', item['q'][:50], '| expected', item['expect'],
              '| got', got, result.task_id or '')
    print(f'{len(questions) - failures}/{len(questions)} passed')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
