"""
SafeFuzzyPrompt: with every choice hidden by the filter (e.g. after typing a
space), up/down/tab must not crash and enter must not exit with an empty answer.
InquirerPy 0.3.4's FuzzyPrompt raises ZeroDivisionError / IndexError there.
"""
from __future__ import annotations

import pytest

pytest.importorskip("InquirerPy")

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from fxt.term.prompts import SafeFuzzyPrompt


class _Event:
    class app:
        result = "not exited"
        @classmethod
        def exit(cls, result=None):
            cls.result = result


@pytest.fixture
def prompt():
    with create_pipe_input() as inp, create_app_session(input=inp, output=DummyOutput()):
        p = SafeFuzzyPrompt(message="m", choices=["2013", "2014"], multiselect=True)
        yield p


def test_keys_ignored_with_no_visible_choices(prompt):
    prompt.content_control._filtered_choices = []      # what a no-match filter leaves
    for handler in (prompt._handle_up, prompt._handle_down, prompt._handle_toggle_choice):
        handler(None)                                    # must not raise
    _Event.app.result = "not exited"
    prompt._handle_enter(_Event)
    assert _Event.app.result == "not exited"


def test_enter_keeps_selected_choices_hidden_by_filter(prompt):
    prompt._handle_toggle_choice(None)                   # tab on "2013"
    prompt.content_control._filtered_choices = []
    _Event.app.result = "not exited"
    prompt._handle_enter(_Event)
    assert _Event.app.result == ["2013"]
