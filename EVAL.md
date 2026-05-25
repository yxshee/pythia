# Oracle Evaluation Status

Pythia should not be submitted or judged as a proven predictive oracle yet.
This repository currently proves the product rail: live market selection,
LLM-generated reasoning traces, Arc hash anchoring, DevUSDC/testnet unlocks,
server-side paywall verification, and replay rejection.

It does **not** yet prove historical accuracy, calibration, or profitable
selection across resolved long-tail markets.

## Current Evidence

| Evidence | Status | What it proves |
|---|---|---|
| Public feed batch `24-31` | Complete | Eight current preview traces are unique, Arc-anchored, and public-safe. |
| Private full bundle | Complete | The paid payload matches public IDs `24-31` and passes source/risk/HOLD checks. |
| Trace coherence validator | Complete | HOLD traces cannot ship with actionable BUY/copy-trade language or nonzero size. |
| Live unlock smoke | Complete | Trace `24` returns full payload after unlock and rejects nonce replay. |
| Resolved-market backtest | Not complete | No statistically meaningful historical oracle accuracy claim is made. |
| External user traction | Not complete | No external paid-user or feedback-count claim is made. |

## Red-Team Finding Already Fixed

Trace `24` previously had the dangerous failure mode Aadi called out:
the final action was `HOLD`, while stale paid reasoning text still said a
BUY YES was justifiable. That is now fixed in three layers:

- The private trace payload was rewritten so trace `24` concludes with
  `Final action: HOLD`, zero size, and no outbound trade link.
- `validate_submission --mode private-deploy` rejects HOLD entries if
  actionable recommendation language appears anywhere in the private entry.
- The promoted Vercel Blob and live `/api/traces/24/full` response were
  revalidated after redeploy.

## Minimum Backtest Before Any Accuracy Claim

Before using language like "effective oracle", "validated oracle", or
"profitable predictor", add a resolved-market study with:

| Requirement | Minimum |
|---|---|
| Markets | At least 20 resolved long-tail markets, with sports separated from politics/crypto. |
| Snapshot | Market price at the time the agent would have scored the market. |
| Agent output | Fair probability, final decision, confidence, and paper size. |
| Outcome | Resolved YES/NO and source of resolution. |
| Metrics | Brier score, calibration bucket, hit rate by decision type, and paper PnL. |
| Failure review | At least 3 correct-sounding wrong traces and the policy changes they caused. |

The machine gate for that study is:

```bash
cd agent
uv run python -m pythia.scripts.validate_oracle_eval ../eval/oracle-redteam.json
```

That command intentionally fails if the dataset is missing, has fewer than
20 resolved markets, lacks paper PnL / resolution sources, or contains fewer
than 3 correct-sounding wrong examples with policy changes.

## Correct-Sounding Wrong Trace Template

Use this table when the resolved-market study is added:

| Market | Agent said | Actual outcome | Why the reasoning sounded right | Why it was wrong | Policy change |
|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD |

## Oracle Red-Team Roadmap

We do not claim historical predictive accuracy yet. This release proves the
Arc-native paid reasoning-trace primitive. EVAL.md defines and begins the
red-team process: resolved long-tail markets, calibration, false positives,
and correct-sounding wrong traces.

The schema for resolved-market entries is captured at
[`eval/oracle-redteam.sample.json`](eval/oracle-redteam.sample.json). Real
entries land in `eval/oracle-redteam.json` as markets resolve, with sizing
pulled from the private full trace at scoring time.

### Failure taxonomy

Every wrong trace gets one of these labels:

- `source_missing` — the source bundle never pulled the data that would have
  changed the call.
- `source_stale` — the source was pulled but the data was already invalidated
  by an event the agent did not see.
- `overfit_to_market_price` — the agent collapsed to the implied probability
  instead of holding its independent prior.
- `ignored_liquidity` — the call was actionable in theory but unfillable at
  the market's actual depth.
- `long_horizon_uncertainty` — the resolution window was too far out for any
  prior to be informative; the call should have been HOLD.
- `correlation_blindness` — the agent treated correlated events as
  independent and double-counted evidence.
- `reasoning_sounded_good_but_false` — the trace read coherently but was
  contradicted by a source the agent did weight, indicating a synthesis bug
  rather than a missing-data bug.

### Planned metrics

Computed once the resolved-market dataset crosses the minimums in the
previous section:

- Accuracy on actionable calls (BUY_YES / BUY_NO only; HOLD excluded).
- Brier score across all calls including HOLD-as-0.5-confidence.
- Average calibration error per confidence bucket.
- False-positive rate (actionable calls where the outcome contradicted the
  decision).
- False-negative rate ("HOLD regret" — HOLD calls where a confident
  actionable call would have been correct).
- Paper PnL in DevUSDC across all actionable calls at the published size.

## Submission Wording Boundary

Allowed wording:

- "Prototype paid reasoning-trace marketplace."
- "Arc-anchored current-market reasoning traces."
- "Paper sizing and risk-gated recommendations."
- "Historical oracle evaluation is planned and explicitly not claimed."

Disallowed until the backtest exists:

- "Proven oracle."
- "Validated predictor."
- "Profitable historical track record."
- "Calibrated across long-tail markets."
