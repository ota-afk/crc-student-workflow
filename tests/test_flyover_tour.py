"""The first-session spotlight tour (plan feature 7).

The tour itself is JavaScript running in the browser, which AppTest can't execute, so these
tests check what can be checked here: the steps, that the scripts parse (with Node, when it's
installed), that every target exists in Flyover, and when Flyover sends the tour. Where the
spotlight and arrow land on screen still needs a look in a real browser.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from test_flyover_app import app_with

from student_workflow import flyover
from student_workflow.flyover_tour import TOUR_STEPS, tour_code, tour_script

FLYOVER = (Path(__file__).resolve().parents[1] / 'src/student_workflow/flyover.py').read_text()


def test_every_step_has_a_selector_title_text_and_shape():
    assert len(TOUR_STEPS) == 7
    for selector, title, text, shape in TOUR_STEPS:
        assert selector.startswith('.st-key-') and title and len(text) > 20
        assert shape in ('circle', 'rounded')


def test_every_target_is_a_keyed_flyover_element():
    for selector, *_ in TOUR_STEPS:
        key = re.match(r'\.st-key-(\w+)', selector).group(1)
        assert f"key='{key}'" in FLYOVER, f'{key} is not a key in flyover.py'


def test_the_tour_starts_with_the_profile_and_ends_on_settings():
    assert TOUR_STEPS[0][0] == '.st-key-flyover_profile'
    assert TOUR_STEPS[-1][0] == '.st-key-flyover_settings'


@pytest.mark.skipif(shutil.which('node') is None, reason='Node is not installed')
@pytest.mark.parametrize('replay', [False, True])
def test_the_tour_scripts_parse(tmp_path, replay):
    page = tmp_path / 'tour.js'
    page.write_text(tour_code(replay, reduce_motion=False))
    frame = tmp_path / 'frame.js'
    frame.write_text(re.search(r'<script>(.*)</script>', tour_script(replay, False),
                               re.DOTALL).group(1))
    for script in (page, frame):
        # check=False: we read the return code ourselves to show Node's error in the failure.
        result = subprocess.run(['node', '--check', str(script)], check=False,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_the_tour_is_a_labelled_modal_that_can_be_skipped():
    code = tour_code(False, False)
    for needed in ("'aria-modal', 'true'", 'Skip tour', "data-act=\"back\"", "setAttribute('inert'",
                   "event.key === 'Escape'", 'sessionStorage'):
        assert needed in code, needed


def test_replay_and_reduce_motion_reach_the_script():
    assert 'var replay = true' in tour_code(True, False)
    assert '__STILL__' not in tour_code(False, True) and 'true ||' in tour_code(False, True)


def _sent(monkeypatch):
    calls = []
    real = flyover.tour_script
    monkeypatch.setattr(flyover, 'tour_script',
                        lambda replay, still: calls.append((replay, still)) or real(replay, still))
    return calls


def test_flyover_sends_the_tour_once_per_session(monkeypatch):
    calls = _sent(monkeypatch)
    app = app_with(monkeypatch)
    assert calls == [(False, False)]
    app.run()
    assert calls == [(False, False)]  # not again on a redraw


def test_replay_in_settings_sends_it_again_on_page_one(monkeypatch):
    calls = _sent(monkeypatch)
    app = app_with(monkeypatch)
    app.button(key='flyover_next').click().run()  # page 2 first: Replay must come back home
    app.button(key='flyover_settings').click().run()
    app.button(key='flyover_tour_replay_btn').click().run()
    assert not app.exception
    assert app.session_state['flyover_page'] == 'home'
    assert calls[-1] == (True, False)


def test_the_tour_is_not_sent_on_page_two(monkeypatch):
    calls = _sent(monkeypatch)
    app = app_with(monkeypatch)
    app.session_state['flyover_page'] = 'readiness'
    app.session_state['flyover_tour_sent'] = False
    calls.clear()
    app.run()
    assert calls == []
