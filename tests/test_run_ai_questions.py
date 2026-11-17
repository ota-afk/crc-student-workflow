"""The manual evaluator must use ENG's risk flags, not a list of task IDs."""

import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('run_ai_questions', ROOT / 'scripts/run_ai_questions.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_task_risk_is_derived_from_every_cited_rule(tmp_path, monkeypatch):
    data = json.loads((ROOT / 'data/rules/rules.json').read_text())
    # A newly risky rule must affect a formerly safe task without editing this script.
    for rule in data['rules']:
        if rule['rule_id'] == 'rule_i94_retrieval_guidance':
            rule['high_risk'] = True
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(data))
    monkeypatch.setenv('RULES_PATH', str(path))
    tasks = {task['id']: task for task in runner.load_tasks()}
    assert tasks['task_i94_retrieval']['high_risk'] is True
    assert tasks['task_confirm_sevis_active']['high_risk'] is True
    assert tasks['task_dmv_id']['high_risk'] is False


def test_missing_rule_risk_does_not_silently_become_safe(tmp_path, monkeypatch):
    data = json.loads((ROOT / 'data/rules/rules.json').read_text())
    del data['rules'][0]['high_risk']
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(data))
    monkeypatch.setenv('RULES_PATH', str(path))
    with pytest.raises(ValidationError):
        runner.load_tasks()
