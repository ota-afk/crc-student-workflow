from student_workflow.config import mock_path
from student_workflow.contract import Workflow


def load():
    return Workflow.model_validate_json(mock_path().read_text(encoding='utf-8'))


def test_mock_validates():
    assert load().workflow


def test_mock_is_consistent():
    wf = load()
    ids = {t.id for t in wf.workflow}
    completed = {t.id for t in wf.workflow if t.status == 'Completed'}
    assert set(wf.student_profile.completed_tasks) == completed
    for task in wf.workflow:
        assert set(task.prerequisites) <= ids
        assert set(task.missing_prerequisites) == set(task.prerequisites) - completed
        if task.status != 'Blocked':
            assert not task.missing_prerequisites
        else:
            assert task.missing_prerequisites or task.blockers
