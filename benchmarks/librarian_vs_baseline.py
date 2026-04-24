"""
Benchmark: LibrarianAgent vs. naive keyword-match baseline.

Runs a fixed panel of representative tasks (with hand-labelled ground
truth) against two selection strategies:

  * ``baseline`` — load every bundle whose name, description, or body
    shares a keyword with the task description (naive OR-match). No
    model calls. This is what you'd do with ``grep``.
  * ``librarian`` — ``run_librarian_session`` with the default three-
    librarian council (Haiku / Flash / small OSS). Uses ``MockAgent``
    fallbacks when provider API keys are absent so the benchmark is
    runnable offline; set ``MAESTRO_BENCH_LIVE=1`` (plus provider keys)
    to run against real models.

Metrics reported:
  * selection size (proxy for token delta)
  * precision / recall / F1 vs. hand-labelled ground truth
  * wall-clock latency per task

Output is a human-readable table to stdout plus a JSON summary to
``benchmarks/results/librarian_vs_baseline.json``.

Usage:
  python -m benchmarks.librarian_vs_baseline
  MAESTRO_BENCH_LIVE=1 python -m benchmarks.librarian_vs_baseline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from maestro.bundles.catalog import Catalog
from maestro.bundles.manifest import regenerate, DEFAULT_MANIFEST_DIR
from maestro.specialists.librarian import (
    default_librarian_council,
    run_librarian_session,
)


# --- Ground-truth task panel -------------------------------------------
#
# Each entry names tasks by the skills the benchmark author expects a
# competent librarian to return. Labels reference skills by *name* (from
# front matter), not bundle_id — ids change if SKILL.md content changes.

GROUND_TRUTH: list[dict] = [
    {
        "task": "Write a Python script that builds a formatted .docx with brand-guideline colours and fonts.",
        "expected": ["docx", "brand-guidelines"],
    },
    {
        "task": "Generate a powerpoint deck from markdown input using python-pptx.",
        "expected": ["pptx"],
    },
    {
        "task": "Create an Excel workbook with formulas and charts for a quarterly report.",
        "expected": ["xlsx"],
    },
    {
        "task": "Extract text and tables from a PDF file into structured JSON.",
        "expected": ["pdf"],
    },
    {
        "task": "Build a small MCP server in TypeScript that exposes a file-listing tool.",
        "expected": ["mcp-builder"],
    },
    {
        "task": "Test a React web app end-to-end with Playwright in CI.",
        "expected": ["webapp-testing"],
    },
    {
        "task": "Design a visual poster for an internal launch announcement.",
        "expected": ["canvas-design"],
    },
    {
        "task": "Write a Claude API integration in Python with prompt caching and streaming.",
        "expected": ["claude-api"],
    },
    {
        "task": "Create a brand-aligned PDF flyer with custom typography.",
        "expected": ["canvas-design", "brand-guidelines"],
    },
    {
        "task": "Build an interactive HTML/TypeScript artifact with React for a frontend prototype.",
        "expected": ["web-artifacts-builder", "frontend-design"],
    },
]


# --- Metrics ------------------------------------------------------------

@dataclass
class TaskResult:
    task: str
    strategy: str
    selected_names: list
    expected_names: list
    selection_size: int
    precision: float
    recall: float
    f1: float
    latency_ms: float


def _prf(selected: list, expected: list) -> tuple[float, float, float]:
    s = set(selected)
    e = set(expected)
    if not s and not e:
        return 1.0, 1.0, 1.0
    tp = len(s & e)
    precision = tp / len(s) if s else 0.0
    recall = tp / len(e) if e else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return round(precision, 4), round(recall, 4), round(f1, 4)


# --- Strategies ---------------------------------------------------------

_KEYWORD_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "to", "in", "on", "of",
    "from", "by", "that", "this", "these", "those", "at", "is", "are",
    "be", "been", "being", "was", "were", "it", "its", "as", "into",
    "using", "use", "write", "create", "build", "make",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")


def _tokenise(text: str) -> set[str]:
    return {
        w.lower() for w in _WORD_RE.findall(text or "")
        if w.lower() not in _KEYWORD_STOPWORDS
    }


def baseline_select(task: str, catalog: Catalog, min_hits: int = 1) -> list[str]:
    """Naive keyword OR-match: include every bundle whose text shares at
    least ``min_hits`` keyword tokens with the task description."""
    task_words = _tokenise(task)
    if not task_words:
        return [m.name for m in catalog]

    selected: list[str] = []
    for m in catalog:
        corpus = " ".join([
            m.name,
            m.raw_description or "",
            m.abstract or "",
            " ".join(t for tags in (m.capabilities or {}).values() for t in tags),
        ])
        hits = task_words & _tokenise(corpus)
        if len(hits) >= min_hits:
            selected.append(m.name)
    return selected


async def librarian_select(task: str, catalog: Catalog) -> tuple[list[str], Optional[str]]:
    council = default_librarian_council(catalog, use_mocks_if_no_keys=True)
    result = await run_librarian_session(
        task=task,
        council=council,
        catalog=catalog,
        session_count=0,
    )
    id_to_name = {m.bundle_id: m.name for m in catalog}
    return [id_to_name[b] for b in result.consensus_bundle_ids if b in id_to_name], result.dissenter


# Python < 3.10 compatibility for ``Optional`` in annotation above
from typing import Optional  # noqa: E402  (intentionally after class body)


# --- Runner -------------------------------------------------------------

async def run(args: argparse.Namespace) -> dict:
    # Ensure manifest cache is fresh before loading the catalog
    if args.regenerate:
        regenerate()
    catalog = Catalog.from_disk()
    if len(catalog) == 0:
        # No cache yet — build in-memory from the skills root
        catalog = Catalog.from_skills_root()
    print(f"Catalog: {len(catalog)} bundles  snapshot={catalog.snapshot_hash()[:12]}")
    print(f"Tasks:   {len(GROUND_TRUTH)}")
    print()

    results: list[TaskResult] = []

    for entry in GROUND_TRUTH:
        task = entry["task"]
        expected = entry["expected"]

        # --- baseline ---
        t0 = time.perf_counter()
        baseline_names = baseline_select(task, catalog)
        baseline_latency = (time.perf_counter() - t0) * 1000.0
        p, r, f1 = _prf(baseline_names, expected)
        results.append(TaskResult(
            task=task, strategy="baseline",
            selected_names=baseline_names, expected_names=expected,
            selection_size=len(baseline_names),
            precision=p, recall=r, f1=f1, latency_ms=round(baseline_latency, 3),
        ))

        # --- librarian ---
        t0 = time.perf_counter()
        lib_names, _dissenter = await librarian_select(task, catalog)
        lib_latency = (time.perf_counter() - t0) * 1000.0
        p, r, f1 = _prf(lib_names, expected)
        results.append(TaskResult(
            task=task, strategy="librarian",
            selected_names=lib_names, expected_names=expected,
            selection_size=len(lib_names),
            precision=p, recall=r, f1=f1, latency_ms=round(lib_latency, 3),
        ))

    # --- Print table ---
    _print_table(results)

    # --- Aggregate ---
    summary = _aggregate(results)
    _print_summary(summary)

    # --- Persist ---
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "librarian_vs_baseline.json"
    out.write_text(json.dumps({
        "catalog_size": len(catalog),
        "catalog_snapshot": catalog.snapshot_hash(),
        "results": [asdict(r) for r in results],
        "summary": summary,
    }, indent=2))
    print(f"\nWrote {out}")

    return summary


def _print_table(results: list[TaskResult]) -> None:
    header = (
        f"{'#':>3}  {'strategy':<10}  {'|sel|':>5}  "
        f"{'P':>5}  {'R':>5}  {'F1':>5}  {'ms':>8}  task"
    )
    print(header)
    print("-" * len(header))
    for i in range(0, len(results), 2):
        for r in results[i : i + 2]:
            task_snippet = r.task[:72] + ("…" if len(r.task) > 72 else "")
            print(
                f"{(i // 2) + 1:>3}  {r.strategy:<10}  {r.selection_size:>5}  "
                f"{r.precision:>5.2f}  {r.recall:>5.2f}  {r.f1:>5.2f}  "
                f"{r.latency_ms:>8.1f}  {task_snippet}"
            )


def _aggregate(results: list[TaskResult]) -> dict:
    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    by_strategy: dict[str, list[TaskResult]] = {}
    for r in results:
        by_strategy.setdefault(r.strategy, []).append(r)

    summary: dict[str, dict] = {}
    for strat, rs in by_strategy.items():
        summary[strat] = {
            "tasks": len(rs),
            "mean_selection_size": mean([r.selection_size for r in rs]),
            "mean_precision": mean([r.precision for r in rs]),
            "mean_recall": mean([r.recall for r in rs]),
            "mean_f1": mean([r.f1 for r in rs]),
            "mean_latency_ms": mean([r.latency_ms for r in rs]),
        }

    # Token-delta proxy: ratio of mean selection sizes.
    baseline_size = summary.get("baseline", {}).get("mean_selection_size", 0.0)
    librarian_size = summary.get("librarian", {}).get("mean_selection_size", 0.0)
    if baseline_size > 0:
        summary["token_delta_ratio"] = round(librarian_size / baseline_size, 4)
    else:
        summary["token_delta_ratio"] = None

    return summary


def _print_summary(summary: dict) -> None:
    print()
    print("Summary:")
    for strat in ("baseline", "librarian"):
        if strat not in summary:
            continue
        s = summary[strat]
        print(
            f"  {strat:<10}  "
            f"|sel|={s['mean_selection_size']:>5.2f}  "
            f"P={s['mean_precision']:>5.2f}  "
            f"R={s['mean_recall']:>5.2f}  "
            f"F1={s['mean_f1']:>5.2f}  "
            f"lat={s['mean_latency_ms']:>7.1f} ms"
        )
    ratio = summary.get("token_delta_ratio")
    if ratio is not None:
        print(f"  token-delta ratio (librarian/baseline): {ratio:.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--regenerate", action="store_true",
        help="Regenerate manifest cache before running.",
    )
    args = ap.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
