"""Retrieval quality on the golden set (D-014): hit@k and MRR at the record level.

A question is a *hit@k* if any of its expected records appears among the first k distinct
records retrieved. Expected ids ending in `*` match by prefix (multi-part summaries).
Out-of-scope questions have no expected records and are excluded from the metrics.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from dgbot.retrieval.retriever import HybridRetriever


class GoldenItem(BaseModel):
    id: str
    question: str
    lang: Literal["en", "ar"]
    category: Literal["darglobal", "wasalt", "out_of_scope"]
    expected: list[str]


def load_golden(path: Path) -> list[GoldenItem]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [GoldenItem.model_validate_json(line) for line in lines if line.strip()]


def _matches(record_id: str, expected: str) -> bool:
    return record_id.startswith(expected[:-1]) if expected.endswith("*") else record_id == expected


def unknown_expected(items: Iterable[GoldenItem], record_ids: set[str]) -> list[str]:
    """Expected ids that match nothing in the index — a typo in the exam, not a miss."""
    return [
        f"{item.id}: {exp}"
        for item in items
        for exp in item.expected
        if not any(_matches(rid, exp) for rid in record_ids)
    ]


@dataclass
class ItemResult:
    item: GoldenItem
    rank: int | None  # 1-based rank of the first relevant record, None if not in top `depth`
    retrieved: list[str]


@dataclass
class Metrics:
    n: int = 0
    hit_at: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0


@dataclass
class EvalReport:
    overall: Metrics
    by_group: dict[str, Metrics]
    results: list[ItemResult]

    def misses(self, k: int = 5) -> list[ItemResult]:
        return [r for r in self.results if r.item.expected and (r.rank is None or r.rank > k)]


def evaluate(
    retriever: HybridRetriever,
    items: Sequence[GoldenItem],
    *,
    depth: int = 10,
    ks: Sequence[int] = (1, 3, 5),
) -> EvalReport:
    results: list[ItemResult] = []
    for item in items:
        hits = retriever.search(item.question, k=depth * 2)
        records: list[str] = []
        for hit in hits:  # distinct records, in rank order
            if hit.chunk.record_id not in records:
                records.append(hit.chunk.record_id)
        records = records[:depth]
        rank = next(
            (i for i, rid in enumerate(records, 1) if any(_matches(rid, e) for e in item.expected)),
            None,
        )
        results.append(ItemResult(item, rank, records))

    scored = [r for r in results if r.item.expected]
    groups: dict[str, list[ItemResult]] = defaultdict(list)
    for r in scored:
        groups[r.item.category].append(r)
        groups[f"lang:{r.item.lang}"].append(r)
    return EvalReport(
        _metrics(scored, ks), {g: _metrics(rs, ks) for g, rs in sorted(groups.items())}, results
    )


def _metrics(results: Sequence[ItemResult], ks: Sequence[int]) -> Metrics:
    n = len(results)
    if not n:
        return Metrics()
    return Metrics(
        n=n,
        hit_at={k: sum(1 for r in results if r.rank and r.rank <= k) / n for k in ks},
        mrr=sum(1 / r.rank for r in results if r.rank) / n,
    )


def format_report(report: EvalReport, title: str) -> str:
    def row(name: str, m: Metrics) -> str:
        hits = "  ".join(f"hit@{k} {v:.2f}" for k, v in m.hit_at.items())
        return f"  {name:<14} n={m.n:<3} {hits}  MRR {m.mrr:.2f}"

    lines = [f"== {title}", row("overall", report.overall)]
    lines += [row(g, m) for g, m in report.by_group.items()]
    misses = report.misses()
    lines.append(f"  misses@5: {len(misses)}")
    for r in misses:
        got = ", ".join(rid.split(":", 2)[-1][:40] for rid in r.retrieved[:3])
        lines.append(f"    - [{r.item.id}] rank={r.rank} | got: {got}")
    return "\n".join(lines)


def to_json(report: EvalReport) -> str:
    return json.dumps(
        {
            "overall": report.overall.__dict__,
            "by_group": {g: m.__dict__ for g, m in report.by_group.items()},
            "items": [
                {"id": r.item.id, "rank": r.rank, "retrieved": r.retrieved[:5]}
                for r in report.results
            ],
        },
        indent=2,
        ensure_ascii=False,
    )
