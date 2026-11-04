"""
Набор примеров для оценки модели: файл читается, проверки считают правильно.
Сама модель здесь — сценарий DoD (FakeLLM); настоящий прогон — python -m evals.run_eval.
"""

from __future__ import annotations

from evals.run_eval import load_cases, run_case

from .ai_fakes import FakeLLM, petya_responder


def test_cases_are_well_formed():
    cases = load_cases()

    assert len({c["name"] for c in cases}) == len(cases)
    for case in cases:
        assert case["kind"] in ("capture", "ask", "tools")
        assert case.get("text") or case.get("question")
        assert case["expect"]


async def test_dod_case_passes_with_expected_output():
    case = next(c for c in load_cases() if c["name"] == "dod-petya")

    report = await run_case(FakeLLM(petya_responder), case)

    assert report["passed"], report["checks"]


async def test_wrong_output_fails_the_case():
    case = next(c for c in load_cases() if c["name"] == "dod-petya")

    def lazy(schema_name, system, user):
        data = petya_responder(schema_name, system, user)
        return {**data, "fields": [], "notes": []} if schema_name == "capture" else data

    report = await run_case(FakeLLM(lazy), case)

    assert not report["passed"]
    assert {c["check"] for c in report["checks"] if not c["ok"]} == {"поле city=Дубай", "заметок ≥ 1"}
