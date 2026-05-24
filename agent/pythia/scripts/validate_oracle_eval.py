"""Validate and summarize a resolved-market oracle red-team dataset.

This script is intentionally separate from ``validate_submission``. The current
hackathon package does not claim historical oracle accuracy, so the public
package should not fail just because this dataset is absent. When a real
resolved-market study exists, this gate defines the minimum evidence required
before docs may claim calibration, accuracy, or a profitable track record.

Usage:

    uv run python -m pythia.scripts.validate_oracle_eval eval/oracle-redteam.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DECISIONS = frozenset({"BUY_YES", "BUY_NO", "HOLD"})
REQUIRED_FIELDS = (
    "market",
    "vertical",
    "scored_at",
    "market_probability_yes",
    "agent_probability_yes",
    "decision",
    "outcome_yes",
    "resolved_at",
    "resolution_source_url",
    "reasoning_summary",
    "paper_pnl_usdc",
)
WRONG_EXAMPLE_FIELDS = (
    "reasoning_sounded_right",
    "why_wrong",
    "policy_change",
)


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_probability(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and 0 <= float(value) <= 1


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_iso_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_http_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def _actionable_wrong(record: dict[str, Any]) -> bool:
    decision = record.get("decision")
    outcome_yes = record.get("outcome_yes")
    if not isinstance(outcome_yes, bool):
        return False
    return (decision == "BUY_YES" and not outcome_yes) or (decision == "BUY_NO" and outcome_yes)


def validate_eval_dataset(
    records: object,
    *,
    min_markets: int = 20,
    min_wrong_examples: int = 3,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(records, list):
        return ["oracle eval dataset must be a JSON array"]
    if len(records) < min_markets:
        failures.append(f"oracle eval needs at least {min_markets} resolved markets; found {len(records)}")

    wrong_examples = 0
    verticals: set[str] = set()
    for index, raw in enumerate(records):
        label = f"record {index}"
        if not isinstance(raw, dict):
            failures.append(f"{label}: must be an object")
            continue
        record = raw
        missing = [field for field in REQUIRED_FIELDS if field not in record]
        if missing:
            failures.append(f"{label}: missing fields {missing}")
            continue

        for field in ("market", "vertical", "reasoning_summary"):
            if not _is_nonempty_string(record.get(field)):
                failures.append(f"{label}: {field} must be a non-empty string")
        if _is_nonempty_string(record.get("vertical")):
            verticals.add(str(record["vertical"]).strip().lower())
        for field in ("scored_at", "resolved_at"):
            if not _is_iso_datetime(record.get(field)):
                failures.append(f"{label}: {field} must be ISO-8601")
        for field in ("market_probability_yes", "agent_probability_yes"):
            if not _is_probability(record.get(field)):
                failures.append(f"{label}: {field} must be a probability in [0, 1]")
        if record.get("decision") not in DECISIONS:
            failures.append(f"{label}: decision must be one of {sorted(DECISIONS)}")
        if not isinstance(record.get("outcome_yes"), bool):
            failures.append(f"{label}: outcome_yes must be boolean")
        if not _is_http_url(record.get("resolution_source_url")):
            failures.append(f"{label}: resolution_source_url must be http(s)")
        if not _is_number(record.get("paper_pnl_usdc")):
            failures.append(f"{label}: paper_pnl_usdc must be numeric")

        if _actionable_wrong(record):
            if all(_is_nonempty_string(record.get(field)) for field in WRONG_EXAMPLE_FIELDS):
                wrong_examples += 1
            else:
                failures.append(
                    f"{label}: wrong actionable call needs reasoning_sounded_right, why_wrong, and policy_change"
                )

    if len(verticals) < 2 and len(records) >= min_markets:
        failures.append("oracle eval should include at least two verticals so broad claims are not single-domain")
    if wrong_examples < min_wrong_examples:
        failures.append(
            f"oracle eval needs at least {min_wrong_examples} correct-sounding wrong examples; "
            f"found {wrong_examples}"
        )
    return failures


def summarize_eval(records: list[dict[str, Any]]) -> dict[str, Any]:
    brier_values: list[float] = []
    actionable_hits = 0
    actionable_total = 0
    paper_pnl = 0.0
    buckets: dict[str, dict[str, int]] = {}

    for record in records:
        prob = float(record["agent_probability_yes"])
        outcome = 1.0 if record["outcome_yes"] else 0.0
        brier_values.append((prob - outcome) ** 2)
        paper_pnl += float(record["paper_pnl_usdc"])

        bucket_floor = int(prob * 5) * 20
        if bucket_floor == 100:
            bucket_floor = 80
        bucket = f"{bucket_floor}-{bucket_floor + 20}"
        buckets.setdefault(bucket, {"count": 0, "yes": 0})
        buckets[bucket]["count"] += 1
        buckets[bucket]["yes"] += int(bool(record["outcome_yes"]))

        decision = record["decision"]
        if decision in {"BUY_YES", "BUY_NO"}:
            actionable_total += 1
            if (decision == "BUY_YES" and record["outcome_yes"]) or (
                decision == "BUY_NO" and not record["outcome_yes"]
            ):
                actionable_hits += 1

    return {
        "markets": len(records),
        "brier_score": round(sum(brier_values) / len(brier_values), 6) if brier_values else None,
        "actionable_hit_rate": round(actionable_hits / actionable_total, 6) if actionable_total else None,
        "actionable_calls": actionable_total,
        "paper_pnl_usdc": round(paper_pnl, 6),
        "calibration_buckets": buckets,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default="eval/oracle-redteam.json",
        help="Resolved-market eval JSON file to validate.",
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"FAIL: oracle eval dataset missing: {path}", file=sys.stderr)
        print("This is expected unless EVAL.md has been completed; do not claim oracle accuracy.", file=sys.stderr)
        return 1
    try:
        records = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"FAIL: oracle eval dataset is not valid JSON: {exc}", file=sys.stderr)
        return 1

    failures = validate_eval_dataset(records)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(json.dumps(summarize_eval(records), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

