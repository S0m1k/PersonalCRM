"""
Прогон набора примеров (assistant_cases.json) через настоящую модель — сравнение моделей и промптов.

    cd backend
    LLM_BASE_URL=http://192.168.0.50:11434/v1 LLM_MODEL=qwen3.5:4b python -m evals.run_eval [--json report.json]

База — in-memory (mongomock), настоящую MongoDB не трогает. Очередь не нужна: вызываются
те же run_capture / run_ask, что и в воркере.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from mongomock_motor import AsyncMongoMockClient

from app.ai import tools
from app.ai.ask import run_ask
from app.ai.analytics import ANALYTICS_TOOLS, validate_params
from app.ai.capture import run_capture
from app.ai.chat import plan_calls, _plan
from app.ai.llm import LLMProvider, build_provider
from app.models.contact import ContactCreate
from app.repositories import contacts as contacts_repo

CASES = Path(__file__).with_name("assistant_cases.json")


def load_cases() -> list[dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))


async def seed(db: Any, contacts: list[dict]) -> dict[str, str]:
    """Создать контакты случая; {полное имя: id}."""
    ids: dict[str, str] = {}
    for spec in contacts:
        data = {k: v for k, v in spec.items() if k not in ("questions", "answered")}
        contact = await contacts_repo.create_contact(db, ContactCreate(**data))
        for text in spec.get("questions", []):
            await tools.add_question(db, contact.id, text)
        for question, answer in spec.get("answered", []):
            await tools.answer_question(db, contact.id, answer, question_text=question)
        ids[tools.full_name(contact)] = contact.id
    return ids


def _has(values: list[str], needle: str) -> bool:
    return any(needle.lower() in v.lower() for v in values)


def score_capture(expect: dict, result: dict, ids: dict[str, str]) -> list[tuple[str, bool]]:
    actions = result["actions"]
    fields = {a["key"]: a["new"] for a in actions if a["type"] == "update_field" and not a.get("error")}
    answers = [a for a in actions if a["type"] == "answer_question"]
    checks: list[tuple[str, bool]] = []
    if "contact" in expect:
        want = ids.get(expect["contact"]) if expect["contact"] else None
        checks.append((f"контакт {expect['contact']}", result["contact_id"] == want))
    if "new_contact" in expect:
        name = (result.get("new_contact") or {}).get("first_name", "")
        checks.append((f"новый контакт {expect['new_contact']}", expect["new_contact"].lower() in name.lower()))
    for key, value in expect.get("fields", {}).items():
        checks.append((f"поле {key}={value}", value.lower() in str(fields.get(key, "")).lower()))
    for key in expect.get("forbid_fields", []):
        checks.append((f"без поля {key}", key not in fields))
    if "max_fields" in expect:
        checks.append((f"полей ≤ {expect['max_fields']}", len(fields) <= expect["max_fields"]))
    for needle in expect.get("answers", []):
        checks.append((f"закрытый вопрос «{needle}»", _has([a["answer"] for a in answers], needle)))
    for needle in expect.get("answers_existing", []):
        existing = [a["answer"] for a in answers if a["question_id"]]
        checks.append((f"ответ на открытый вопрос «{needle}»", _has(existing, needle)))
    for needle in expect.get("new_questions", []):
        texts = [a["text"] for a in actions if a["type"] == "add_question"]
        checks.append((f"новый вопрос «{needle}»", _has(texts, needle)))
    if "min_notes" in expect:
        notes = [a for a in actions if a["type"] == "add_note"]
        checks.append((f"заметок ≥ {expect['min_notes']}", len(notes) >= expect["min_notes"]))
    return checks


def score_ask(expect: dict, result: dict, ids: dict[str, str]) -> list[tuple[str, bool]]:
    checks = [(f"в ответе «{n}»", n.lower() in result["answer"].lower()) for n in expect.get("answer_contains", [])]
    got = {c["id"] for c in result["contacts"]}
    checks += [(f"ссылка на {name}", ids.get(name) in got) for name in expect.get("contacts", [])]
    return checks


async def plan_result(llm: LLMProvider, question: str) -> dict:
    """Выбор инструментов аналитики: вызовы после проверки (как в чате) — имя и параметры."""
    calls = []
    for name, params in plan_calls(await _plan(llm, question, "")):
        calls.append({"tool": name, "params": validate_params(ANALYTICS_TOOLS[name], params)})
    return {"question": question, "calls": calls}


def score_tools(expect: dict, result: dict) -> list[tuple[str, bool]]:
    chosen = [c["tool"] for c in result["calls"]]
    checks = [(f"инструменты {expect['tools']}", chosen == expect["tools"])]
    for tool, want in expect.get("params", {}).items():
        got = next((c["params"] for c in result["calls"] if c["tool"] == tool), {})
        checks += [(f"{tool}.{k}={v}", got.get(k) == v) for k, v in want.items()]
    return checks


async def run_case(llm: LLMProvider, case: dict) -> dict:
    db = AsyncMongoMockClient()[f"eval_{case['name']}"]
    ids = await seed(db, case.get("contacts", []))
    started = time.perf_counter()
    try:
        if case["kind"] == "capture":
            result = await run_capture(db, llm, {"text": case["text"]})
            checks = score_capture(case["expect"], result, ids)
        elif case["kind"] == "tools":
            result = await plan_result(llm, case["question"])
            checks = score_tools(case["expect"], result)
        else:
            result = await run_ask(db, llm, {"question": case["question"]})
            checks = score_ask(case["expect"], result, ids)
        error = None
    except Exception as exc:  # noqa: BLE001 — ошибка модели = проваленный случай
        result, checks, error = None, [("без ошибки", False)], f"{type(exc).__name__}: {exc}"
    return {
        "name": case["name"],
        "kind": case["kind"],
        "seconds": round(time.perf_counter() - started, 2),
        "passed": all(ok for _, ok in checks),
        "checks": [{"check": c, "ok": ok} for c, ok in checks],
        "error": error,
        "result": result,
    }


async def run_all(llm: LLMProvider, cases: list[dict]) -> list[dict]:
    return [await run_case(llm, case) for case in cases]


def _print_report(model: str, reports: list[dict]) -> None:
    total_checks = sum(len(r["checks"]) for r in reports)
    ok_checks = sum(c["ok"] for r in reports for c in r["checks"])
    for r in reports:
        mark = "OK  " if r["passed"] else "FAIL"
        failed = [c["check"] for c in r["checks"] if not c["ok"]]
        detail = f" — не прошло: {', '.join(failed)}" if failed else ""
        print(f"{mark} {r['name']:<28} {r['seconds']:>6.1f} с{detail}{' — ' + r['error'] if r['error'] else ''}")
    times = sorted(r["seconds"] for r in reports)
    print(
        f"\nМодель {model}: случаев {sum(r['passed'] for r in reports)}/{len(reports)}, "
        f"проверок {ok_checks}/{total_checks}; время медиана {times[len(times) // 2]:.1f} с, макс {times[-1]:.1f} с"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--json", type=Path, help="записать полный отчёт в файл")
    parser.add_argument("--only", help="прогнать один случай по имени")
    args = parser.parse_args()
    cases = [c for c in load_cases() if not args.only or c["name"] == args.only]
    llm = build_provider()
    reports = asyncio.run(run_all(llm, cases))
    _print_report(llm.name, reports)
    if args.json:
        args.json.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(0 if all(r["passed"] for r in reports) else 1)


if __name__ == "__main__":
    main()
