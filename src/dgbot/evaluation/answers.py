"""Answer-level checks on the golden set (Phase 4). Uses one LLM request per question —
run deliberately (`--answers --limit N`), never in CI (CLAUDE.md rule 6).

Automatic checks per answer:
- grounded: cites ≥1 source, and ≥1 cited source is an expected record
- language: answer language == question language
- no_dg_price: DarGlobal answers state no *unit price* (D-037); company figures such as
  revenue, development value, contract value or visa/investment thresholds are fine
- declines: out-of-scope questions get no citations
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from dgbot.chat.prompts import detect_language
from dgbot.chat.service import ChatService, ErrorEvent
from dgbot.domain.chat import ChatAnswer
from dgbot.evaluation.retrieval import GoldenItem, _matches

_MONEY = r"(?:AED|USD|US\$|SAR|GBP|EUR|OMR|QAR|\$|£|€|درهم|ريال)"
# Unit-price phrasing: "starting from AED 1.2M", "priced at", "prices start", "يبدأ من".
_UNIT_PRICE = re.compile(
    rf"(?:start(?:s|ing)?(?:\s+(?:from|at))?|priced\s+(?:at|from)|prices?\s+(?:start|from|of)|"
    rf"costs?|from)\s+{_MONEY}\s?\d|(?:يبدأ|تبدأ|بسعر|الأسعار\s+تبدأ|سعر\s+(?:الوحدة|الشقة|الفيلا))",
    re.I,
)
# Amounts next to these words are company/regulatory figures, not unit prices.
_NOT_UNIT_PRICE = re.compile(
    r"revenue|sales|development value|gdv|contract|invest|minimum|threshold|at least|profit|"
    r"إيرادات|قيمة|عقد|استثمار|الحد الأدنى",
    re.I,
)


def unit_price_mentions(text: str) -> list[str]:
    """Phrases that state a unit price, ignoring company/regulatory amounts nearby."""
    hits = []
    for match in _UNIT_PRICE.finditer(text):
        window = text[max(0, match.start() - 60) : match.end()]
        if not _NOT_UNIT_PRICE.search(window):
            hits.append(match.group(0))
    return hits


@dataclass
class AnswerResult:
    item: GoldenItem
    answer: str | None
    error: str | None = None
    model: str | None = None
    checks: dict[str, bool] | None = None


async def evaluate_answers(service: ChatService, items: Sequence[GoldenItem]) -> list[AnswerResult]:
    results: list[AnswerResult] = []
    for item in items:
        result = await service.answer(item.question)
        if isinstance(result, ErrorEvent):
            results.append(AnswerResult(item, None, error=result.code))
            if result.code == "quota":
                break  # no point continuing
            continue
        results.append(
            AnswerResult(item, result.answer, model=result.model, checks=_checks(item, result))
        )
    return results


def _checks(item: GoldenItem, answer: ChatAnswer) -> dict[str, bool]:
    cited = [s for s in answer.sources if s.cited]
    checks = {"language": detect_language(answer.answer) == item.lang}
    if item.category == "out_of_scope":
        checks["declines"] = not cited
        return checks
    checks["grounded"] = any(any(_matches(s.record_id, e) for e in item.expected) for s in cited)
    if item.category == "darglobal":
        checks["no_dg_price"] = not unit_price_mentions(answer.answer)
    return checks


def summarize(results: Sequence[AnswerResult]) -> str:
    totals: dict[str, list[bool]] = {}
    for r in results:
        for name, ok in (r.checks or {}).items():
            totals.setdefault(name, []).append(ok)
    errors = sum(1 for r in results if r.error)
    lines = [f"== answers: {len(results)} questions, {errors} errors"]
    lines += [f"  {name:<12} {sum(v)}/{len(v)}" for name, v in sorted(totals.items())]
    for r in results:
        failed = [k for k, ok in (r.checks or {}).items() if not ok]
        if failed or r.error:
            lines.append(
                f"  - [{r.item.id}] {r.error or ', '.join(failed)} | {(r.answer or '')[:120]!r}"
            )
    return "\n".join(lines)
