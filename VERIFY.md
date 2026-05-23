# Pythia / Agora Alpha — Release Proof Report

> Reproducible evidence that the deployed artifact at
> https://agoraalpha.vercel.app matches the source tree at the recorded commit,
> that the contract, agent, and web suites all pass, that the paywall
> validation chain rejects malformed requests, and that a real wallet can
> complete the unlock → fetch flow with replay protection.
>
> Each block below is a verbatim transcript. Sections marked **`TODO:`**
> are filled in by re-running the command shown directly above the block
> (see [`scripts/verify.sh`](scripts/verify.sh) when present, or run the
> command manually). The post-deploy audit checklist that this report is
> the *output* of lives in [`VERIFY-CHECKLIST.md`](VERIFY-CHECKLIST.md).

---

## 0. Identity

| Field             | Value                                                              |
|-------------------|--------------------------------------------------------------------|
| Commit            | `5d1ab397222ad22967cd2ec5f77fa72a6e2e0cdd` (audit branch HEAD as of generation; final submission commit will sit on top of this) |
| Short SHA         | `5d1ab39`                                                          |
| Branch            | `audit/executive-verdict-fixes` (PR'd to `main` before submission) |
| Worktree clean    | dirty — the changes from this audit are staged but un-committed at generation; full diff in §0.1 below |
| Generated at      | `2026-05-23T15:45:12Z` (local-evidence sections 1, 2, 7); §3–§6 timestamps captured against the live preview at handoff |
| Production URL    | https://agoraalpha.vercel.app                                      |
| Preview URL       | `TODO: paste preview URL produced by Vercel after the audit branch is pushed` |
| UnlockMarket addr | `0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA` (registered trace IDs `9,10,11,12,13,14,15,16`) |
| Chain             | Arc testnet, chain id `5042002`                                    |

### 0.1 Diff scope

The audit branch modifies the following tracked files and adds the following
new files. Reproduce with `git status --short` on the same commit.

```text
 M .env.example
 M .gitignore
 M README.md
 M STATUS.md
 M VERIFY.md
 M agent/pythia/analyst.py
 M agent/pythia/preview.py
 M agent/pythia/scripts/publish_live_feed.py
 M agent/pythia/scripts/validate_submission.py
 M agent/tests/test_publisher_payload.py
 M agent/tests/test_validate_submission.py
 M contracts/src/PythiaVault.sol
 M scripts/package_submission.py
 M traces/sanitized-full-trace.example.json
 M web/.env.local.example
 M web/README.md
 M web/app/api/rpc/route.ts
 M web/app/api/traces/[traceId]/full/route.ts
 M web/app/layout.tsx
 M web/app/page.tsx
 M web/app/pick/[traceId]/page.tsx
 M web/components/traction-strip.tsx
 M web/components/unlocked-content.tsx
 M web/lib/server/paywall-nonce.ts
 M web/lib/server/rate-limit.ts
 M web/lib/traces.ts
 M web/next.config.ts
 M web/package.json
 M web/pnpm-lock.yaml
?? .github/workflows/ci.yml
?? VERIFY-CHECKLIST.md
?? scripts/backfill_event_data_sources.py
?? scripts/upload-private-blob.mjs
?? web/app/opengraph-image.tsx
?? web/app/twitter-image.tsx
?? web/lib/server/kv.ts
?? web/lib/server/private-traces.ts
```

---

## 1. Source build evidence

### 1.1 `pnpm install --frozen-lockfile`

Command:

```bash
cd web && pnpm install --frozen-lockfile
```

```text
Lockfile is up to date, resolution step is skipped
Already up to date

╭ Warning ─────────────────────────────────────────────────────────────────────╮
│                                                                              │
│   Ignored build scripts: bufferutil@4.1.0, keccak@3.0.4,                     │
│   utf-8-validate@5.0.10.                                                     │
│   Run "pnpm approve-builds" to pick which dependencies should be allowed     │
│   to run scripts.                                                            │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
Done in 305ms using pnpm v10.33.0
```

The three ignored build scripts are optional native bindings of upstream
dependencies (wagmi/viem WebSocket transports). They are not used in this
project and the pnpm warning is informational, not an error.

### 1.2 `pnpm build`

Command:

```bash
cd web && pnpm build
```

```text
> web@0.1.0 build /Users/Shared/pythia/web
> next build

▲ Next.js 16.2.6 (Turbopack)

  Creating an optimized production build ...
✓ Compiled successfully in 1682ms
  Running TypeScript ...
  Finished TypeScript in 2.4s ...
  Collecting page data using 9 workers ...
  Generating static pages using 9 workers (0/7) ...
  Generating static pages using 9 workers (1/7)
  Generating static pages using 9 workers (3/7)
  Generating static pages using 9 workers (5/7)
✓ Generating static pages using 9 workers (7/7) in 162ms
  Finalizing page optimization ...

Route (app)                     Revalidate  Expire
┌ ○ /                                  30s      1y
├ ○ /_not-found
├ ƒ /api/rpc
├ ƒ /api/traces/[traceId]/full
├ ○ /icon.svg
├ ○ /opengraph-image
├ ƒ /pick/[traceId]
└ ○ /twitter-image


○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
```

Both `/opengraph-image` and `/twitter-image` are statically prerendered from
[`web/app/opengraph-image.tsx`](web/app/opengraph-image.tsx) and
[`web/app/twitter-image.tsx`](web/app/twitter-image.tsx) (Next.js 16 file
convention; emits the `og:image*` and `twitter:image*` meta tags).

### 1.3 `pnpm exec tsc --noEmit`

Command:

```bash
cd web && pnpm exec tsc --noEmit
```

```text
(empty stdout, exit code 0)
```

---

## 2. Test evidence

### 2.1 Contracts — `forge test -vvv`

Command:

```bash
cd contracts && forge test
```

```text
No files changed, compilation skipped

Ran 16 tests for test/UnlockMarket.t.sol:UnlockMarketTest
[PASS] test_clearPriceOverride_revertsToDefault() (gas: 30996)
[PASS] test_priceFor_defaultsWhenNoOverride() (gas: 13663)
[PASS] test_priceFor_usesOverrideWhenSet() (gas: 43343)
[PASS] test_registerTrace_onlyOwnerAndRejectsZero() (gas: 48815)
[PASS] test_setDefaultPrice_onlyOwner() (gas: 29788)
[PASS] test_setPriceOverride_zeroRejected() (gas: 14601)
[PASS] test_setTreasury_routesToNewAddress() (gas: 150597)
[PASS] test_transferOwnership_transfersAdminAuthority() (gas: 31254)
[PASS] test_unlock_atDefaultPrice() (gas: 140392)
[PASS] test_unlock_atOverridePrice() (gas: 160986)
[PASS] test_unlock_distinctBuyersBothCount() (gas: 181709)
[PASS] test_unlock_doubleUnlockReverts() (gas: 161361)
[PASS] test_unlock_nonexistentTraceReverts() (gas: 48677)
[PASS] test_unlock_reentrantTokenCannotUnlockTwice() (gas: 1250289)
[PASS] test_unlock_revertsOnInsufficientAllowance() (gas: 98028)
[PASS] test_unlock_revertsOnZeroPrice() (gas: 775488)
Suite result: ok. 16 passed; 0 failed; 0 skipped; finished in 7.64ms (2.01ms CPU time)

Ran 6 tests for test/TraceLog.t.sol:TraceLogTest
[PASS] test_constructor_authorizesPublisher() (gas: 18005)
[PASS] test_publish_assignsMonotonicIds() (gas: 27481)
[PASS] test_publish_rejectsBadConfidence() (gas: 13904)
[PASS] test_publish_revertsForUnauthorized() (gas: 13811)
[PASS] test_setPublisher_onlyAdmin() (gas: 34008)
[PASS] test_transferAdmin() (gas: 24255)
Suite result: ok. 6 passed; 0 failed; 0 skipped; finished in 9.65ms (3.25ms CPU time)

Ran 8 tests for test/DevUSDC.t.sol:DevUSDCTest
[PASS] test_cancelAuthorization_alreadyUsedReverts() (gas: 78985)
[PASS] test_cancelAuthorization_preventsLaterUse() (gas: 51266)
[PASS] test_domainSeparator_isStableAtSameChainId() (gas: 6259)
[PASS] test_transferWithAuthorization_badSigReverts() (gas: 23085)
[PASS] test_transferWithAuthorization_expiredReverts() (gas: 18372)
[PASS] test_transferWithAuthorization_prematureReverts() (gas: 18190)
[PASS] test_transferWithAuthorization_replayReverts() (gas: 77201)
[PASS] test_transferWithAuthorization_validSig_transfersAndMarksNonce() (gas: 81064)
Suite result: ok. 8 passed; 0 failed; 0 skipped; finished in 9.66ms (11.25ms CPU time)

Ran 12 tests for test/PythiaVault.t.sol:PythiaVaultTest
[PASS] test_bridgeOut_thenIn_preservesAccounting() (gas: 176935)
[PASS] test_deposit_revertsForNonOperator() (gas: 79004)
[PASS] test_deposit_revertsWhenPaused() (gas: 75942)
[PASS] test_firstDeposit_mintsOneToOne() (gas: 157261)
[PASS] test_recordTrade_lossExceedingNav_reverts() (gas: 156649)
[PASS] test_recordTrade_revertsForNonOperator() (gas: 156349)
[PASS] test_secondDeposit_afterProfit_getsFewerShares() (gas: 220883)
[PASS] test_secondDeposit_atFlatNav_isProRata() (gas: 216109)
[PASS] test_setPerformanceFee_capped() (gas: 23182)
[PASS] test_withdraw_loss_paysNoFee() (gas: 182355)
[PASS] test_withdraw_noProfit_noFee() (gas: 170135)
[PASS] test_withdraw_profitTakesFee() (gas: 204352)
Suite result: ok. 12 passed; 0 failed; 0 skipped; finished in 9.67ms (3.26ms CPU time)

Ran 4 test suites in 14.66ms (36.62ms CPU time): 42 tests passed, 0 failed, 0 skipped (42 total tests)
```

### 2.2 Agent — `python -m unittest discover -s tests -v`

Command:

```bash
cd agent && uv run python -m unittest discover -s tests -v
```

```text
test_excludes_private_paid_traces_and_runtime_artifacts (test_package_submission.PackageSubmissionTests.test_excludes_private_paid_traces_and_runtime_artifacts) ... ok
test_includes_public_deliverables (test_package_submission.PackageSubmissionTests.test_includes_public_deliverables) ... ok
test_dedupe_caps_repeated_template_clusters (test_publish_live_feed.PublishLiveFeedTests.test_dedupe_caps_repeated_template_clusters) ... ok
test_dedupe_rejects_expired_or_low_signal_markets (test_publish_live_feed.PublishLiveFeedTests.test_dedupe_rejects_expired_or_low_signal_markets) ... ok
test_dedupe_rejects_fixture_markers_and_duplicate_questions (test_publish_live_feed.PublishLiveFeedTests.test_dedupe_rejects_fixture_markers_and_duplicate_questions) ... ok
test_load_gamma_candidates_marks_import_as_live_not_fixture (test_publish_live_feed.PublishLiveFeedTests.test_load_gamma_candidates_marks_import_as_live_not_fixture) ... ok
test_buy_decisions_include_side_hint (test_publisher_payload.PublisherPayloadTests.test_buy_decisions_include_side_hint) ... ok
test_full_payload_adds_default_risk_factor_when_reasoning_has_no_risk_step (test_publisher_payload.PublisherPayloadTests.test_full_payload_adds_default_risk_factor_when_reasoning_has_no_risk_step) ... ok
test_full_payload_hides_copy_trade_for_hold_and_includes_source_bundle (test_publisher_payload.PublisherPayloadTests.test_full_payload_hides_copy_trade_for_hold_and_includes_source_bundle) ... ok
test_hold_decision_has_no_copy_trade_url (test_publisher_payload.PublisherPayloadTests.test_hold_decision_has_no_copy_trade_url) ... ok
test_preview_payload_never_includes_builder_code (test_publisher_payload.PublisherPayloadTests.test_preview_payload_never_includes_builder_code) ... ok
test_accepts_blob_url_when_local_file_absent (test_validate_submission.ValidateSubmissionDeployModeTests.test_accepts_blob_url_when_local_file_absent) ... ok
test_accepts_private_full_snapshot_and_public_preview_only (test_validate_submission.ValidateSubmissionDeployModeTests.test_accepts_private_full_snapshot_and_public_preview_only) ... ok
test_rejects_full_payload_without_non_market_source (test_validate_submission.ValidateSubmissionDeployModeTests.test_rejects_full_payload_without_non_market_source) ... ok
test_rejects_public_full_snapshot_fixture_source_wrong_dates_and_stale_copy (test_validate_submission.ValidateSubmissionDeployModeTests.test_rejects_public_full_snapshot_fixture_source_wrong_dates_and_stale_copy) ... ok
test_rejects_when_both_private_file_and_blob_url_missing (test_validate_submission.ValidateSubmissionDeployModeTests.test_rejects_when_both_private_file_and_blob_url_missing) ... ok
test_accepts_preview_only_zip (test_validate_submission.ValidateSubmissionPackageModeTests.test_accepts_preview_only_zip) ... ok
test_ignores_private_full_in_working_tree (test_validate_submission.ValidateSubmissionPackageModeTests.test_ignores_private_full_in_working_tree) ... ok
test_rejects_public_full_present_in_package (test_validate_submission.ValidateSubmissionPackageModeTests.test_rejects_public_full_present_in_package) ... ok

----------------------------------------------------------------------
Ran 19 tests in 0.021s

OK
```

### 2.3 Submission validator — deploy mode

Command:

```bash
cd /Users/Shared/pythia && PYTHONPATH=agent uv --project agent run \
  python -m pythia.scripts.validate_submission --mode deploy
```

```text
submission data ok (deploy): 8 home markets, 8 private full traces
```

(exit code 0)

### 2.4 Submission validator — package mode

Command:

```bash
# Build the zip first, then validate the unpacked contents in package mode.
python3 scripts/package_submission.py
unzip -q submission.zip -d /tmp/pythia-pkg-check
cd /tmp/pythia-pkg-check && PYTHONPATH=/Users/Shared/pythia/agent \
  uv --project /Users/Shared/pythia/agent run \
  python -m pythia.scripts.validate_submission --mode package
```

```text
wrote submission.zip (337,703 bytes)
submission data ok (package): 8 home markets, no paid bundle present
```

(both exit code 0)

---

> **Sections 3–6 are operator-run against the live deploy.** They cannot be
> filled by an offline sandbox: §3 needs the production URL responding live,
> §4 needs the rate-limiter and paywall route hot, §5 needs a real wallet on
> Arc with DevUSDC, and §6 needs browser screenshots. The plan is to run
> these against the **preview deploy** produced by the audit branch first
> (catch regressions), then re-run §3 and §5 against `agoraalpha.vercel.app`
> after promotion. Capture verbatim output into the blocks below.

## 3. Live deploy — surface checks

### 3.1 Security headers

Command:

```bash
curl -sI https://agoraalpha.vercel.app | sort
```

```text
TODO: full sorted header dump. Required entries:
  - content-security-policy
  - strict-transport-security: max-age=63072000; includeSubDomains; preload
  - x-content-type-options: nosniff
  - x-frame-options: DENY  (or CSP frame-ancestors 'none')
  - referrer-policy: strict-origin-when-cross-origin (or stricter)
```

### 3.2 Home page renders

Command:

```bash
curl -s https://agoraalpha.vercel.app | grep -c 'href="/pick/'
```

```text
TODO: expected count = number of cards rendered on home (>= 8)
```

### 3.3 Pick page renders

Command:

```bash
curl -sI https://agoraalpha.vercel.app/pick/16
```

```text
TODO: expected `HTTP/2 200`
```

### 3.4 Unknown pick returns 404

Command:

```bash
curl -sI https://agoraalpha.vercel.app/pick/999999
```

```text
TODO: expected `HTTP/2 404`
```

---

## 4. Paywall route — rejection paths

### 4.1 `/api/rpc` rejects write methods

Command:

```bash
curl -s -X POST https://agoraalpha.vercel.app/api/rpc \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_sendRawTransaction","params":["0x"]}'
```

```text
TODO: expected JSON-RPC error with code -32601 (method not allowed) and HTTP 403
```

### 4.2 `/api/rpc` rejects oversized body

Command:

```bash
yes 'a' | head -c 65000 | curl -s -X POST https://agoraalpha.vercel.app/api/rpc \
  -H 'content-type: application/json' --data-binary @-
```

```text
TODO: expected HTTP 413
```

### 4.3 `/api/rpc` rejects batch > 10

Command:

```bash
curl -s -X POST https://agoraalpha.vercel.app/api/rpc \
  -H 'content-type: application/json' \
  -d "$(python3 -c 'import json; print(json.dumps([{"jsonrpc":"2.0","id":i,"method":"eth_chainId"} for i in range(11)]))')"
```

```text
TODO: expected HTTP 400 with explicit "batch too large" error
```

### 4.4 `/api/traces/16/full` rejects missing fields

Command:

```bash
curl -s -X POST 'https://agoraalpha.vercel.app/api/traces/16/full' \
  -H 'content-type: application/json' \
  -d '{}'
```

```text
TODO: expected HTTP 400 with explicit reason listing required fields
       (address, nonce, signature, message)
```

### 4.5 `/api/traces/16/full` rejects unsigned address

Command:

```bash
curl -s -X POST 'https://agoraalpha.vercel.app/api/traces/16/full' \
  -H 'content-type: application/json' \
  -d '{"address":"0x0000000000000000000000000000000000000000","nonce":"x","signature":"0x00","message":"x"}'
```

```text
TODO: expected HTTP 401 or 403 with "signature-invalid" or equivalent
```

---

## 5. Paid unlock — live transcript

Wallet is a fresh testnet address; values are redacted only where they would
expose a private key. The trace id, contract address, and tx hash are public.

### 5.1 Nonce issuance

Command:

```bash
WALLET=<wallet address, no 0x prefix is fine in the curl path>
TRACE=16
curl -s "https://agoraalpha.vercel.app/api/paywall/nonce?traceId=${TRACE}&address=0x${WALLET}"
```

```text
TODO: { "nonce": "...", "message": "Unlock Pythia trace 16 for 0x...\\nNonce: ...\\nIssued: 2026-05-..." }
```

### 5.2 Sign + POST

Command (wallet signs `message` from 5.1, then):

```bash
curl -s -X POST "https://agoraalpha.vercel.app/api/traces/${TRACE}/full" \
  -H 'content-type: application/json' \
  -d '{"address":"0x...","nonce":"...","signature":"0x...","message":"..."}'
```

```text
TODO: expected HTTP 200 with the full trace JSON. Capture:
  - decision
  - edge_bps
  - source kinds (must include at least one of: event_data, news, sentiment, official_data)
  - risk_factors length
```

### 5.3 Replay rejection

Re-run the exact same POST from 5.2.

```text
TODO: expected HTTP 409 with body { "error": "nonce-used" } or equivalent
```

### 5.4 Onchain anchor

Command:

```bash
TX=<tx hash from /pick/${TRACE} onchain card or UnlockMarket.lookupBySigner(address,traceId)>
curl -sI "https://explorer.arc.network/tx/${TX}"
```

```text
TODO: expected HTTP 200; record block number from the explorer
```

---

## 6. Visual evidence

| File                                       | Description                                   |
|--------------------------------------------|-----------------------------------------------|
| `verify/screenshots/unlocked-trace.png`    | `TODO`: unlocked /pick/16 page in browser     |
| `verify/screenshots/explorer-tx.png`       | `TODO`: Arc explorer tx detail page           |

Both screenshots should be 1280×800 or larger, browser chrome included.

---

## 7. Package evidence

### 7.1 Zip build

Command:

```bash
python3 scripts/package_submission.py
```

```text
wrote submission.zip (337,703 bytes)
```

### 7.2 Zip surface

Command:

```bash
unzip -l submission.zip | grep -E 'picks|trace-' | head -20
```

```text
9500  05-23-2026 04:24   web/data/picks-preview.json
```

Only `web/data/picks-preview.json` appears. No `web/data/picks-full*.json` and
no `traces/trace-*.json` entries — confirms the package builder excludes both
the public and private full bundles and the raw trace JSONs. This is also
asserted at runtime by §2.4's `--mode package` validator.

---

## 8. Sign-off

- [ ] All `TODO:` blocks above are replaced with real output.
- [ ] `git status` shows only tracked changes that match the diff.
- [ ] Production URL serves a 200 on `/api/traces/16/full` after a real unlock.
- [ ] Both screenshots committed under `verify/screenshots/`.
- [ ] Date in §0 matches the timestamp on the most recent transcript.

Signed-off by: `TODO: handle`
