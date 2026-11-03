"""
Оценка выбора инструментов аналитики: случаи kind=tools считаются по плану модели.
"""

from __future__ import annotations

from evals.run_eval import load_cases, run_case

from .ai_fakes import FakeLLM

BLANK = {"field": "", "chart": "", "period": "", "from": "", "to": "", "contact_id": "", "days": 0, "limit": 0}


def _case(name: str) -> dict:
    return next(c for c in load_cases() if c["name"] == name)


def _plans(*calls):
    return FakeLLM(lambda *a: {"calls": [{**BLANK, **c} for c in calls]})


def test_there_are_enough_tool_cases():
    assert len([c for c in load_cases() if c["kind"] == "tools"]) >= 5


async def test_right_tool_and_params_pass():
    llm = _plans({"tool": "count_contacts_by", "field": "city"})

    assert (await run_case(llm, _case("tools-by-city")))["passed"]


async def test_wrong_tool_or_param_fails():
    llm = _plans({"tool": "count_contacts_by", "field": "city"})
    assert not (await run_case(llm, _case("tools-stale")))["passed"]

    wrong_field = _plans({"tool": "count_contacts_by", "field": "company"})
    assert not (await run_case(wrong_field, _case("tools-by-city")))["passed"]


async def test_no_tool_expected_for_question_about_person():
    assert (await run_case(_plans(), _case("tools-none-for-person")))["passed"]
    assert not (await run_case(_plans({"tool": "stale_contacts"}), _case("tools-none-for-person")))["passed"]


async def test_invalid_params_make_the_case_fail_not_crash():
    report = await run_case(_plans({"tool": "stale_contacts", "days": 99999}), _case("tools-stale"))

    assert not report["passed"] and report["error"]
