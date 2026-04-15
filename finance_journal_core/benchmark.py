from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean
from typing import Any, Callable

from .analytics import split_tags
from .app import FinanceJournalApp
from .memory import score_memory_row
from .storage import json_loads


@dataclass
class BenchmarkCase:
    case_id: str
    description: str
    query: dict[str, Any]
    relevant_memory_ids: list[str]


def _fts_query_terms(text: str) -> list[str]:
    terms: list[str] = []
    for part in split_tags(text):
        for token in str(part).replace('"', " ").split():
            cleaned = token.strip()
            if cleaned:
                terms.append(cleaned)
    return list(dict.fromkeys(terms))


def _row_text(row: dict[str, Any]) -> str:
    return " ".join(
        [
            str(row.get("title") or ""),
            str(row.get("text_body") or ""),
            " ".join(split_tags(json_loads(row.get("tags_json"), []))),
            str(row.get("strategy_line") or ""),
            str(row.get("market_stage") or ""),
        ]
    ).lower()


def _ranked_ids(rows: list[dict[str, Any]], limit: int) -> list[str]:
    return [str(row.get("memory_id") or "") for row in rows[:limit] if row.get("memory_id")]


def _evaluate_ranking(ranked_ids: list[str], relevant_ids: list[str], ks: tuple[int, ...] = (1, 3, 5)) -> dict[str, float]:
    relevant = set(relevant_ids)
    metrics: dict[str, float] = {}
    first_rank = 0
    dcg = 0.0
    idcg = 0.0
    for rank, memory_id in enumerate(ranked_ids, start=1):
        if memory_id in relevant:
            if not first_rank:
                first_rank = rank
            dcg += 1.0 / (1.0 if rank == 1 else math.log2(rank + 1))
    for ideal_rank in range(1, min(len(relevant), len(ranked_ids)) + 1):
        idcg += 1.0 / (1.0 if ideal_rank == 1 else math.log2(ideal_rank + 1))
    metrics["mrr"] = round(1.0 / first_rank, 4) if first_rank else 0.0
    metrics["ndcg"] = round(dcg / idcg, 4) if idcg else 0.0
    for k in ks:
        top_k = ranked_ids[:k]
        matched = [memory_id for memory_id in top_k if memory_id in relevant]
        metrics[f"hit@{k}"] = 1.0 if matched else 0.0
        metrics[f"recall@{k}"] = round(len(matched) / len(relevant), 4) if relevant else 0.0
    return metrics


def seed_demo_benchmark_corpus(app: FinanceJournalApp) -> dict[str, Any]:
    created: dict[str, dict[str, Any]] = {}
    demo_rows = [
        {
            "label": "cpo_alpha",
            "ts_code": "603083",
            "name": "Alpha Optics",
            "buy_date": "20260410",
            "buy_price": 43.20,
            "sell_date": "20260415",
            "sell_price": 46.80,
            "thesis": "absorption after panic washout in optical supply chain repair",
            "logic_type_tags": ["leader", "pullback"],
            "pattern_tags": ["ma_pullback"],
            "market_stage_tag": "range",
            "environment_tags": ["repair_flow", "cpo"],
            "emotion_notes": "slightly anxious during the flush",
            "mistake_tags": ["early_entry"],
            "lessons_learned": "wait for reclaim confirmation before scaling",
            "decision_context": {"strategy_context": {"strategy_line": "cpo_repair_pullback"}},
        },
        {
            "label": "cpo_beta",
            "ts_code": "688256",
            "name": "Photon Link",
            "buy_date": "20260411",
            "buy_price": 58.40,
            "sell_date": "20260416",
            "sell_price": 61.20,
            "thesis": "weak-open shakeout followed by supply return in optical hardware",
            "logic_type_tags": ["leader", "pullback"],
            "pattern_tags": ["base_reclaim"],
            "market_stage_tag": "range",
            "environment_tags": ["repair_flow", "cpo"],
            "emotion_notes": "calmer because the setup was already rehearsed",
            "mistake_tags": ["late_add"],
            "lessons_learned": "do not add before the second reclaim",
            "decision_context": {"strategy_context": {"strategy_line": "cpo_repair_pullback"}},
        },
        {
            "label": "dividend_alpha",
            "ts_code": "600519",
            "name": "Dividend Core",
            "buy_date": "20260410",
            "buy_price": 1350.0,
            "sell_date": "20260417",
            "sell_price": 1384.0,
            "thesis": "defensive base reclaim with dividend support and low-vol rotation",
            "logic_type_tags": ["defensive", "pullback"],
            "pattern_tags": ["base_reclaim"],
            "market_stage_tag": "range",
            "environment_tags": ["dividend", "defense"],
            "emotion_notes": "comfortable because the position size stayed small",
            "mistake_tags": [],
            "lessons_learned": "fits the slower rotation regime",
            "decision_context": {"strategy_context": {"strategy_line": "dividend_repair"}},
        },
        {
            "label": "dividend_beta",
            "ts_code": "601318",
            "name": "Shield Insurance",
            "buy_date": "20260412",
            "buy_price": 51.20,
            "sell_date": "20260418",
            "sell_price": 53.00,
            "thesis": "income-style rotation with defense and low-beta support",
            "logic_type_tags": ["defensive", "pullback"],
            "pattern_tags": ["base_reclaim"],
            "market_stage_tag": "range",
            "environment_tags": ["dividend", "defense"],
            "emotion_notes": "patient entry because the setup was not crowded",
            "mistake_tags": [],
            "lessons_learned": "keep it as a calm portfolio anchor",
            "decision_context": {"strategy_context": {"strategy_line": "dividend_repair"}},
        },
        {
            "label": "breakout_alpha",
            "ts_code": "002131",
            "name": "Crowded Runner",
            "buy_date": "20260409",
            "buy_price": 12.20,
            "sell_date": "20260410",
            "sell_price": 11.50,
            "thesis": "late chase into a crowded breakout after a climax gap",
            "logic_type_tags": ["breakout", "chase"],
            "pattern_tags": ["gap_breakout"],
            "market_stage_tag": "euphoric",
            "environment_tags": ["crowded", "momentum"],
            "emotion_notes": "impulsive follow-through after a fast open",
            "mistake_tags": ["impulse", "fomo"],
            "lessons_learned": "crowded gaps need a faster failure stop",
            "decision_context": {"strategy_context": {"strategy_line": "crowded_breakout"}},
        },
        {
            "label": "breakout_beta",
            "ts_code": "600986",
            "name": "Heat Board",
            "buy_date": "20260409",
            "buy_price": 8.80,
            "sell_date": "20260411",
            "sell_price": 8.10,
            "thesis": "exhaustion pop followed by failed continuation in a crowded tape",
            "logic_type_tags": ["breakout", "chase"],
            "pattern_tags": ["failed_breakout"],
            "market_stage_tag": "euphoric",
            "environment_tags": ["crowded", "momentum"],
            "emotion_notes": "felt rushed by the opening spike",
            "mistake_tags": ["impulse", "late_exit"],
            "lessons_learned": "when the tape is euphoric, protect the exit first",
            "decision_context": {"strategy_context": {"strategy_line": "crowded_breakout"}},
        },
        {
            "label": "ai_alpha",
            "ts_code": "300308",
            "name": "Compute Spring",
            "buy_date": "20260413",
            "buy_price": 27.10,
            "sell_date": "20260418",
            "sell_price": 29.60,
            "thesis": "oversold compute name reclaiming after a shallow undercut",
            "logic_type_tags": ["reversal", "oversold"],
            "pattern_tags": ["undercut_reclaim"],
            "market_stage_tag": "transition",
            "environment_tags": ["ai", "mean_reversion"],
            "emotion_notes": "entry stayed disciplined because risk was predefined",
            "mistake_tags": [],
            "lessons_learned": "the best entry came after the failed flush",
            "decision_context": {"strategy_context": {"strategy_line": "ai_mean_reversion"}},
        },
        {
            "label": "ai_beta",
            "ts_code": "002415",
            "name": "Inference Loop",
            "buy_date": "20260414",
            "buy_price": 18.40,
            "sell_date": "20260418",
            "sell_price": 19.10,
            "thesis": "mean-reversion bounce after an undercut in AI hardware",
            "logic_type_tags": ["reversal", "oversold"],
            "pattern_tags": ["undercut_reclaim"],
            "market_stage_tag": "transition",
            "environment_tags": ["ai", "mean_reversion"],
            "emotion_notes": "more comfortable because the position was smaller",
            "mistake_tags": ["small_size"],
            "lessons_learned": "size up only after the second higher low",
            "decision_context": {"strategy_context": {"strategy_line": "ai_mean_reversion"}},
        },
    ]

    for row in demo_rows:
        trade = app.log_trade(
            ts_code=row["ts_code"],
            name=row["name"],
            buy_date=row["buy_date"],
            buy_price=row["buy_price"],
            thesis=row["thesis"],
            sell_date=row["sell_date"],
            sell_price=row["sell_price"],
            logic_type_tags=row["logic_type_tags"],
            pattern_tags=row["pattern_tags"],
            market_stage_tag=row["market_stage_tag"],
            environment_tags=row["environment_tags"],
            emotion_notes=row["emotion_notes"],
            mistake_tags=row["mistake_tags"],
            lessons_learned=row["lessons_learned"],
            decision_context=row["decision_context"],
        )
        created[row["label"]] = trade

    app.rebuild_memory()
    app.skillize_memory(trade_date="20260418", lookback_days=365, min_samples=1)
    return {
        "labels": {
            label: {
                "trade_id": trade.get("trade_id"),
                "memory_id": (trade.get("memory_cell") or {}).get("memory_id"),
                "ts_code": trade.get("ts_code"),
                "strategy_line": json_loads(trade.get("decision_context_json"), {}).get("strategy_context", {}).get("strategy_line", ""),
            }
            for label, trade in created.items()
        }
    }


def build_demo_benchmark_cases(manifest: dict[str, Any]) -> list[BenchmarkCase]:
    labels = manifest["labels"]
    return [
        BenchmarkCase(
            case_id="text_cpo_repair",
            description="Text-only query with partial lexical overlap; graph expansion should recover the second CPO memory.",
            query={"text": "washout,reclaim,optical,repair"},
            relevant_memory_ids=[labels["cpo_alpha"]["memory_id"], labels["cpo_beta"]["memory_id"]],
        ),
        BenchmarkCase(
            case_id="strategy_cpo_range",
            description="Structured query by strategy line, stage, and tags.",
            query={
                "strategy_line": "cpo_repair_pullback",
                "market_stage": "range",
                "tags": "leader,pullback,repair_flow",
            },
            relevant_memory_ids=[labels["cpo_alpha"]["memory_id"], labels["cpo_beta"]["memory_id"]],
        ),
        BenchmarkCase(
            case_id="dividend_defense",
            description="Mixed defensive dividend query.",
            query={
                "text": "defensive,dividend,base,reclaim",
                "market_stage": "range",
                "tags": "defense,dividend",
            },
            relevant_memory_ids=[labels["dividend_alpha"]["memory_id"], labels["dividend_beta"]["memory_id"]],
        ),
        BenchmarkCase(
            case_id="crowded_breakout_risk",
            description="Risk-focused momentum query should recall both crowded breakout failures.",
            query={
                "text": "crowded,breakout,impulse,climax",
                "market_stage": "euphoric",
            },
            relevant_memory_ids=[labels["breakout_alpha"]["memory_id"], labels["breakout_beta"]["memory_id"]],
        ),
        BenchmarkCase(
            case_id="ai_mean_reversion",
            description="AI mean-reversion retrieval using strategy and environment cues.",
            query={
                "strategy_line": "ai_mean_reversion",
                "market_stage": "transition",
                "tags": "ai,mean_reversion,oversold",
            },
            relevant_memory_ids=[labels["ai_alpha"]["memory_id"], labels["ai_beta"]["memory_id"]],
        ),
    ]


def retrieve_fts_only(app: FinanceJournalApp, case: BenchmarkCase, limit: int) -> list[dict[str, Any]]:
    query_text = str(case.query.get("text") or "").strip()
    if not query_text:
        return []
    terms = _fts_query_terms(query_text)
    if not terms:
        return []
    query = " ".join(f'"{term}"' for term in terms)
    rows = app.db.fetchall(
        """
        SELECT c.*
        FROM memory_cells_fts f
        JOIN memory_cells c ON c.memory_id = f.memory_id
        WHERE memory_cells_fts MATCH ?
        ORDER BY c.updated_at DESC
        LIMIT ?
        """,
        (query, max(limit * 5, 12)),
    )
    scored: list[dict[str, Any]] = []
    for row in rows:
        text_blob = _row_text(row)
        score = 0.0
        for term in terms:
            if term.lower() in text_blob:
                score += 1.0
        if score <= 0:
            continue
        row_copy = dict(row)
        row_copy["score"] = round(score, 4)
        scored.append(row_copy)
    scored.sort(key=lambda item: (item.get("score") or 0.0, item.get("updated_at") or ""), reverse=True)
    return scored[:limit]


def retrieve_structured_only(app: FinanceJournalApp, case: BenchmarkCase, limit: int) -> list[dict[str, Any]]:
    query = case.query
    token_code = str(query.get("ts_code") or "").strip()
    strategy_line = str(query.get("strategy_line") or "").strip()
    market_stage = str(query.get("market_stage") or "").strip()
    requested_tags = set(split_tags(query.get("tags") or []))
    rows = app.db.fetchall("SELECT * FROM memory_cells ORDER BY updated_at DESC LIMIT 200")
    scored: list[dict[str, Any]] = []
    for row in rows:
        score = 0.0
        row_tags = set(split_tags(json_loads(row.get("tags_json"), [])))
        if token_code and row.get("ts_code") == token_code:
            score += 4.0
        if strategy_line and row.get("strategy_line") == strategy_line:
            score += 3.0
        if market_stage and row.get("market_stage") == market_stage:
            score += 2.0
        score += float(len(requested_tags & row_tags)) * 1.5
        if score <= 0:
            continue
        row_copy = dict(row)
        row_copy["score"] = round(score, 4)
        scored.append(row_copy)
    scored.sort(key=lambda item: (item.get("score") or 0.0, item.get("updated_at") or ""), reverse=True)
    return scored[:limit]


def retrieve_hybrid_cell_only(app: FinanceJournalApp, case: BenchmarkCase, limit: int) -> list[dict[str, Any]]:
    query = case.query
    text = str(query.get("text") or "")
    token_code = str(query.get("ts_code") or "")
    strategy_line = str(query.get("strategy_line") or "")
    market_stage = str(query.get("market_stage") or "")
    requested_tags = split_tags(query.get("tags") or [])
    rows = app.db.fetchall("SELECT * FROM memory_cells ORDER BY updated_at DESC LIMIT 200")
    scored: list[dict[str, Any]] = []
    for row in rows:
        score = score_memory_row(
            row,
            text=text,
            ts_code=token_code,
            strategy_line=strategy_line,
            market_stage=market_stage,
            tags=requested_tags,
        )
        if score <= 0 and (text or token_code or strategy_line or market_stage or requested_tags):
            continue
        row_copy = dict(row)
        row_copy["score"] = score
        scored.append(row_copy)
    scored.sort(key=lambda item: (item.get("score") or 0.0, item.get("updated_at") or ""), reverse=True)
    return scored[:limit]


def retrieve_graph_hybrid(app: FinanceJournalApp, case: BenchmarkCase, limit: int) -> list[dict[str, Any]]:
    query = case.query
    result = app.query_memory(
        text=str(query.get("text") or ""),
        ts_code=str(query.get("ts_code") or "") or None,
        strategy_line=str(query.get("strategy_line") or "") or None,
        market_stage=str(query.get("market_stage") or "") or None,
        tags=query.get("tags") or "",
        trade_date=query.get("trade_date") or None,
        limit=limit,
    )
    return list(result.get("matched_cells", []))


def _summarize_method(case_reports: list[dict[str, Any]], method_name: str) -> dict[str, Any]:
    metrics_by_name = ["mrr", "ndcg", "hit@1", "hit@3", "hit@5", "recall@1", "recall@3", "recall@5"]
    aggregate = {
        metric: round(mean(item["metrics"][metric] for item in case_reports), 4)
        for metric in metrics_by_name
    }
    return {
        "method": method_name,
        "case_count": len(case_reports),
        "aggregate_metrics": aggregate,
        "cases": case_reports,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Memory Retrieval Benchmark",
        "",
        f"- Benchmark name: `{report['benchmark_name']}`",
        f"- Trade date anchor: `{report['trade_date']}`",
        f"- Case count: `{report['case_count']}`",
        "",
        "## Aggregate Metrics",
        "",
        "| Method | MRR | nDCG | Hit@1 | Hit@3 | Recall@3 | Recall@5 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["methods"]:
        agg = item["aggregate_metrics"]
        lines.append(
            f"| {item['method']} | {agg['mrr']:.4f} | {agg['ndcg']:.4f} | {agg['hit@1']:.4f} | {agg['hit@3']:.4f} | {agg['recall@3']:.4f} | {agg['recall@5']:.4f} |"
        )
    lines.extend(["", "## Per-Case Highlights", ""])
    for case in report["cases"]:
        lines.append(f"### {case['case_id']}")
        lines.append(f"- Description: {case['description']}")
        lines.append(f"- Relevant memory ids: `{', '.join(case['relevant_memory_ids'])}`")
        for method_name, details in case["methods"].items():
            top_ids = ", ".join(details["ranked_ids"][:3]) or "-"
            lines.append(
                f"- `{method_name}` -> top ids: `{top_ids}` | MRR={details['metrics']['mrr']:.4f} | Recall@3={details['metrics']['recall@3']:.4f}"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "- `fts_only`: lexical retrieval over memory cell text only.",
            "- `structured_only`: exact symbol / stage / strategy / tag matching without free-text semantics.",
            "- `hybrid_cell_only`: lexical plus structured scoring on individual memory cells.",
            "- `graph_hybrid`: current Finance Journal retriever with scene and hyperedge expansion inspired by EverOS / HyperMem style relation-aware recall.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def run_memory_retrieval_benchmark(
    app: FinanceJournalApp,
    *,
    trade_date: str = "20260418",
    limit: int = 5,
    seed_demo: bool = True,
    write_artifact: bool = True,
) -> dict[str, Any]:
    if not seed_demo:
        raise ValueError("run_memory_retrieval_benchmark currently requires seed_demo=True")
    manifest = seed_demo_benchmark_corpus(app)
    cases = build_demo_benchmark_cases(manifest)
    methods: dict[str, Callable[[FinanceJournalApp, BenchmarkCase, int], list[dict[str, Any]]]] = {
        "fts_only": retrieve_fts_only,
        "structured_only": retrieve_structured_only,
        "hybrid_cell_only": retrieve_hybrid_cell_only,
        "graph_hybrid": retrieve_graph_hybrid,
    }

    case_reports_by_method: dict[str, list[dict[str, Any]]] = {name: [] for name in methods}
    case_reports: list[dict[str, Any]] = []
    for case in cases:
        method_payloads: dict[str, Any] = {}
        for method_name, method in methods.items():
            ranked_rows = method(app, case, limit)
            ranked_ids = _ranked_ids(ranked_rows, limit)
            metrics = _evaluate_ranking(ranked_ids, case.relevant_memory_ids)
            payload = {
                "ranked_ids": ranked_ids,
                "top_rows": [
                    {
                        "memory_id": row.get("memory_id"),
                        "title": row.get("title"),
                        "score": row.get("score"),
                        "strategy_line": row.get("strategy_line"),
                        "market_stage": row.get("market_stage"),
                    }
                    for row in ranked_rows[:limit]
                ],
                "metrics": metrics,
            }
            method_payloads[method_name] = payload
            case_reports_by_method[method_name].append(
                {
                    "case_id": case.case_id,
                    "metrics": metrics,
                }
            )
        case_reports.append(
            {
                "case_id": case.case_id,
                "description": case.description,
                "query": case.query,
                "relevant_memory_ids": case.relevant_memory_ids,
                "methods": method_payloads,
            }
        )

    method_summaries = [_summarize_method(case_reports_by_method[name], name) for name in methods]
    report = {
        "benchmark_name": "everos_memory_retrieval_v1",
        "trade_date": trade_date,
        "case_count": len(cases),
        "seed_demo": seed_demo,
        "manifest": manifest,
        "methods": method_summaries,
        "cases": case_reports,
    }
    if write_artifact:
        markdown = _render_markdown(report)
        report["artifact_paths"] = app._write_artifact(trade_date, "memory_retrieval_benchmark", report, markdown)
    return report
