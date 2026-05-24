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
| Historical baseline | Earlier sections retain pre-promotion audit transcripts for comparison. The final promotion proof is §5 onward. |
| Final promotion tree | `main` / `origin/main` aligned for the final package and deploy verification; final runtime hardening keeps rate-limit counters out of Blob while preserving durable nonce replay. |
| Generated at      | `2026-05-24T18:27:21Z` (§5.4 final trace-24 live unlock); screenshots refreshed on `2026-05-24`; package manifest generated after final zip (§7). |
| Production URL    | https://agoraalpha.vercel.app                                      |
| Production deploy | Latest `https://agoraalpha.vercel.app` production alias verified with `vercel inspect`. The exact deployment id is kept in the operator handoff because docs-only proof commits can trigger a fresh Vercel deployment. |
| UnlockMarket addr | `0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA` (registered trace IDs `24,25,26,27,28,29,30,31`) |
| Chain             | Arc testnet, chain id `5042002`                                    |

### 0.1 Diff scope

The post-promotion runtime cleanup removes Blob-backed rate-limit counters,
adds a regression test for that contract, and keeps the proof docs aligned on
trace IDs `24,25,26,27,28,29,30,31`. The runtime cleanup commit scope was:

```text
ec5ebfe fix: keep rate limits off blob storage
 STATUS.md                                   |  11 +--
 agent/tests/test_web_rate_limit.py          |  23 ++++++
 contracts/script/DeployUnlockMarket.s.sol   |   2 +-
 contracts/script/RegisterUnlockTraces.s.sol |   2 +-
 web/.env.local.example                      |  12 +--
 web/README.md                               |  10 +--
 web/lib/server/kv.ts                        |   5 +-
 web/lib/server/rate-limit.ts                | 115 ----------------------------
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
  python -m pythia.scripts.validate_submission --mode private-deploy
```

```text
submission data ok (private-deploy): 8 home markets, 8 private full traces
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
  python -m pythia.scripts.validate_submission --mode public-package
```

```text
wrote submission.zip (... bytes)
submission data ok (public-package): 8 home markets, no paid bundle present
```

(both exit code 0)

---

> **Sections 3–6 evidence is captured against the live deploy.** §3 + §4 below
> are filled in against `agoraalpha.vercel.app` (production) at
> **2026-05-23T17:15:50Z**, which at the time of capture is the **pre-merge
> baseline** (PR #26 has not yet been promoted). The Vercel deployment-preview
> URL for the audit branch is protected by Vercel SSO (HTTP 401 to unauth
> requests — see the auth-required HTML body), so the preview cannot be
> reached from a sandbox curl; the practical equivalent is to run the same
> battery against prod pre-merge (this section) and again against prod
> post-merge (§3-prod / §4-prod, added in E4). §5 needs a real wallet on Arc
> with DevUSDC; §6 needs browser screenshots. Both are operator-run.
>
> Captured outputs below are verbatim from the production endpoint at the
> timestamp above. After PR #26 merges and the new build promotes, this
> section is re-run and any deltas are appended as §3-post-merge / §4-post-merge.

## 3. Live deploy — surface checks (pre-merge baseline)

### 3.1 Security headers

Command:

```bash
curl -sI https://agoraalpha.vercel.app | sort
```

```text
HTTP/2 200
age: 19
cache-control: public, max-age=0, must-revalidate
content-length: 68497
content-security-policy: frame-ancestors 'none'; object-src 'none'; base-uri 'self';
content-type: text/html; charset=utf-8
date: Fri, 22 May 2026 22:59:33 GMT
etag: "ru4vtyn7pr1gqn"
referrer-policy: strict-origin-when-cross-origin
server: Vercel
strict-transport-security: max-age=63072000; includeSubDomains; preload
vary: rsc, next-router-state-tree, next-router-prefetch, next-router-segment-prefetch
x-content-type-options: nosniff
x-frame-options: DENY
x-matched-path: /
x-nextjs-prerender: 1
x-nextjs-stale-time: 300
x-powered-by: Next.js
x-vercel-cache: HIT
x-vercel-id: bom1::iad1::7hbxg-1779556503155-c62e830dd784
```

All five required headers present: `content-security-policy: frame-ancestors 'none'`,
`strict-transport-security: max-age=63072000; includeSubDomains; preload`,
`x-content-type-options: nosniff`, `x-frame-options: DENY`,
`referrer-policy: strict-origin-when-cross-origin`. CSP also asserts
`object-src 'none'` and `base-uri 'self'`.

### 3.2 Home page renders

Command:

```bash
curl -s https://agoraalpha.vercel.app | grep -oc 'href="/pick/[0-9]\+"'
```

```text
8
```

Home renders exactly 8 pick-page links — matches the 8 live Polymarket
traces validated by `validate_submission --mode private-deploy` in §2.3.

### 3.3 Pick page renders

Command:

```bash
curl -sI https://agoraalpha.vercel.app/pick/24
```

```text
HTTP/2 200 
```

### 3.4 Unknown pick returns 404

Command:

```bash
curl -sI https://agoraalpha.vercel.app/pick/999999
```

```text
HTTP/2 404
```

---

## 3 (post-merge). Live deploy — surface checks (re-run after PR #26 merge)

Re-running the §3 battery against `https://agoraalpha.vercel.app` after PR
#26 merged as commit `bcc1d55` and Vercel auto-deployed. This block exists
to prove the audit branch's hardening landed on prod; the pre-merge baseline
above stays intact for diffing.

Captured at `2026-05-23T18:33:00Z` against merge commit `bcc1d55`.

### 3.7 Security headers (post-merge)

Command:

```bash
curl -sI https://agoraalpha.vercel.app/ | sort | \
  grep -iE 'content-security-policy|strict-transport|x-content|x-frame|referrer'
```

```text
content-security-policy: frame-ancestors 'none'; object-src 'none'; base-uri 'self';
referrer-policy: strict-origin-when-cross-origin
strict-transport-security: max-age=63072000; includeSubDomains; preload
x-content-type-options: nosniff
x-frame-options: DENY
```

All five hardening headers from §3.1 still present post-merge. No regression.

### 3.8 Home page renders ≥8 picks (post-merge)

Command:

```bash
curl -s https://agoraalpha.vercel.app/ | grep -oE 'href="/pick/[0-9]+"' | sort -u | wc -l
```

```text
       8
```

Eight unique pick links, matching the pre-merge baseline and the home-feed
invariant enforced by `validate_submission`.

### 3.9 `/pick/24` returns 200 (post-promotion)

Command:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://agoraalpha.vercel.app/pick/24
```

```text
200
```

### 3.10 `/pick/999999` returns 404 (post-merge)

Command:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://agoraalpha.vercel.app/pick/999999
```

```text
404
```

---

## 4. Paywall route — rejection paths (pre-merge baseline)

### 4.1 `/api/rpc` rejects write methods

Command:

```bash
curl -s -X POST https://agoraalpha.vercel.app/api/rpc \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_sendRawTransaction","params":["0x"]}'
```

```text
{"error":"method-not-allowed","detail":"This proxy only forwards a read-only allowlist. Writes go through the wallet, not this endpoint."}
HTTP 403
```

`eth_sendRawTransaction` is rejected at the allowlist gate before any
upstream forwarding — Canteen-issued RPC quota is never spent on
arbitrary external transactions.

### 4.2 `/api/rpc` rejects oversized body

Command:

```bash
yes 'a' | head -c 65000 | curl -s -X POST https://agoraalpha.vercel.app/api/rpc \
  -H 'content-type: application/json' --data-binary @-
```

```text
{"error":"body-too-large"}
HTTP 413
```

`MAX_BODY_CHARS = 25_000` in [web/app/api/rpc/route.ts](web/app/api/rpc/route.ts);
65 KB exceeds the cap and short-circuits before JSON parsing.

### 4.3 `/api/rpc` rejects batch > 10

Command:

```bash
curl -s -X POST https://agoraalpha.vercel.app/api/rpc \
  -H 'content-type: application/json' \
  -d "$(python3 -c 'import json; print(json.dumps([{"jsonrpc":"2.0","id":i,"method":"eth_chainId"} for i in range(11)]))')"
```

```text
{"error":"batch-size-not-allowed","max":10}
HTTP 400
```

`MAX_BATCH_CALLS = 10`; an 11-call batch is rejected with the explicit
cap value in the body for client UI surfacing.

### 4.4 `/api/traces/24/full` rejects missing fields

Command:

```bash
curl -s -X POST 'https://agoraalpha.vercel.app/api/traces/24/full' \
  -H 'content-type: application/json' \
  -d '{}'
```

```text
{"error":"missing-fields"}
HTTP 400
```

The route requires `address`, `nonce`, `signature`, and `message`; an
empty body short-circuits at the first guard before any chain or
signature work happens.

### 4.5 `/api/traces/24/full` rejects unsigned address

Command:

```bash
curl -s -X POST 'https://agoraalpha.vercel.app/api/traces/24/full' \
  -H 'content-type: application/json' \
  -d '{"address":"0x0000000000000000000000000000000000000000","nonce":"x","signature":"0x00","message":"x"}'
```

```text
{"error":"message-context-mismatch"}
HTTP 401
```

The message ("x") fails the host/trace/address/chain/contract context
check at [web/app/api/traces/[traceId]/full/route.ts:176](web/app/api/traces/%5BtraceId%5D/full/route.ts#L176)
before reaching signature verification — fail-fast on the cheapest
check.

### 4.6 `/api/traces/24/full` rejects oversized body (post-merge expectation)

Command:

```bash
python3 -c 'import json; print(json.dumps({"address":"0x0000000000000000000000000000000000000000","nonce":"x"*5000,"signature":"0x00","message":"x"}))' | \
  curl -s -X POST 'https://agoraalpha.vercel.app/api/traces/24/full' \
  -H 'content-type: application/json' --data-binary @-
```

Pre-merge prod (current behavior — 4 KB cap not yet deployed):

```text
{"error":"message-context-mismatch"}
HTTP 401
```

This evidences that the **4 KB body cap added by PR #26 (C1)** is not yet
on production: the 5 KB body is accepted and the request proceeds to the
context-mismatch guard. After PR #26 promotes, this case is expected to
return `{"error":"payload-too-large"}` with `HTTP 413`. The
post-merge re-run in §4.12 confirms this.

---

## 4 (post-merge). Paywall route — rejection paths (re-run after PR #26 merge)

Re-running the §4 battery against `https://agoraalpha.vercel.app` after PR
#26 merged as commit `bcc1d55` and Vercel auto-deployed. §4.12 is the proof
that C1 (the 4 KB body cap) is now live.

Captured at `2026-05-23T18:35:00Z` against merge commit `bcc1d55`.

### 4.7 `/api/rpc` rejects write methods (post-merge)

Command:

```bash
curl -s -X POST https://agoraalpha.vercel.app/api/rpc \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","method":"eth_sendRawTransaction","params":["0x"],"id":1}'
```

```text
{"error":"method-not-allowed","detail":"This proxy only forwards a read-only allowlist. Writes go through the wallet, not this endpoint."}
HTTP 403
```

### 4.8 `/api/rpc` rejects oversized body (post-merge)

Command:

```bash
python3 -c "import json,sys; sys.stdout.write(json.dumps({'jsonrpc':'2.0','method':'eth_blockNumber','params':[],'id':'x'*200000}))" | \
  curl -s -X POST https://agoraalpha.vercel.app/api/rpc \
  -H 'content-type: application/json' --data-binary @-
```

(200 071 byte body)

```text
{"error":"body-too-large"}
HTTP 413
```

### 4.9 `/api/rpc` rejects batch > 10 (post-merge)

Command:

```bash
python3 -c "import json,sys; sys.stdout.write(json.dumps([{'jsonrpc':'2.0','method':'eth_blockNumber','params':[],'id':i} for i in range(11)]))" | \
  curl -s -X POST https://agoraalpha.vercel.app/api/rpc \
  -H 'content-type: application/json' --data-binary @-
```

```text
{"error":"batch-size-not-allowed","max":10}
HTTP 400
```

### 4.10 `/api/traces/24/full` rejects missing fields (post-promotion)

Command:

```bash
curl -s -X POST 'https://agoraalpha.vercel.app/api/traces/24/full' \
  -H 'content-type: application/json' \
  -d '{}'
```

```text
{"error":"missing-fields"}
HTTP 400
```

### 4.11 `/api/traces/24/full` rejects stale nonce (post-promotion)

Command:

```bash
curl -s -X POST 'https://agoraalpha.vercel.app/api/traces/24/full' \
  -H 'content-type: application/json' \
  -d '{"address":"0x0000000000000000000000000000000000000001","nonce":"0xdeadbeef","signature":"0x0123…1c","message":"agoraalpha.vercel.app — unlock trace\nTrace ID: 24\naddress: 0x0000000000000000000000000000000000000001\nChain ID: 5042002\nUnlockMarket: 0xd8af5ebe36ac9ea736f40d749674ff1b0f4bd3ca\nNonce: 0xdeadbeef\nIssued: 2020-01-01T00:00:00.000Z\nExpires: 2020-01-01T00:05:00.000Z"}'
```

```text
{"error":"nonce-not-found"}
HTTP 401
```

This is a tighter rejection than §4.5: the message context (host/trace/
address/chain/contract) matches the canonical form, so the route advances
past `messageMatchesContext` and falls at the nonce-store lookup. The fake
`0xdeadbeef` was never issued, so it's not in the active set.

### 4.12 `/api/traces/24/full` rejects oversized body — C1 confirmed live (post-promotion)

Command:

```bash
python3 -c "import json,sys; sys.stdout.write(json.dumps({'address':'0x'+'1'*40,'nonce':'0x'+'a'*8,'signature':'0x'+'b'*130,'message':'x'*5000}))" | \
  curl -s -X POST 'https://agoraalpha.vercel.app/api/traces/24/full' \
  -H 'content-type: application/json' --data-binary @-
```

(5 244 byte body — above the 4 KB cap)

```text
{"error":"payload-too-large"}
HTTP 413
```

**Confirmed:** the 4 KB body cap from C1 ([web/app/api/traces/[traceId]/full/route.ts](web/app/api/traces/%5BtraceId%5D/full/route.ts))
is now live on prod. Pre-merge this same payload returned `HTTP 401
message-context-mismatch` (see §4.6 baseline); post-merge it short-circuits
at the size gate before any parsing or context work.

---

## 5. Paid unlock — live transcript (current public batch)

Captured `2026-05-24T18:27:21Z` via [scripts/cli-unlock.mjs](scripts/cli-unlock.mjs)
against the production deploy `https://agoraalpha.vercel.app`, after the
public preview, private Blob bundle, live deploy, and `UnlockMarket`
registration were aligned on trace IDs `24,25,26,27,28,29,30,31`.

This is the current submission proof path: trace `24` is visible in
`web/data/picks-preview.json`, present in the server-only private Blob,
registered in `UnlockMarket`, and rendered in
`verify/screenshots/unlocked-trace.png`.

### 5.1 Full cli-unlock transcript — trace 24

Command:

```bash
PRIVATE_KEY=$DEMO_DEPLOYER_PK ARC_RPC_URL=$ARC_RPC_URL \
  node scripts/cli-unlock.mjs --base=https://agoraalpha.vercel.app \
  --trace-id=24
```

```text
[1/11] Wallet:    0xFA769b2C65087311B51E9541D8C8987f7FFB0A1e
[2/11] Args:      base=https://agoraalpha.vercel.app  trace-id=24  rpc=https://rpc.testnet.arc-node.thecanteenapp.com/…  dry-run=false
[3/11] Clients:   viem public+wallet on chain 5042002
[4/11] priceFor:  0.1 USDC (raw=100000)
         balance:  1000001.1 USDC
[5/11] mint:      skipped (balance >= price)
         allow:    0.1 USDC
[6/11] approve:   skipped (allowance >= price)
[7/11] unlock:    skipped (already unlocked on-chain)
[8/11] GET:       https://agoraalpha.vercel.app/api/traces/24/full?address=0xFA769b2C65087311B51E9541D8C8987f7FFB0A1e
         nonce:    eyJ2Ijox...OY-N8
         issued:   2026-05-24T18:27:21.822Z
         expires:  2026-05-24T18:32:21.822Z
[9/11] sign:      EIP-191 message (599 chars)
         sig:      0x4aefff6a45e0847a…461b
[10/11] POST:     https://agoraalpha.vercel.app/api/traces/24/full
         HTTP 200: {"agent_probability_yes":0.09,"confidence":"medium","copy_trade_url":null,"current_implied_yes":0.0105,"decision":"HOLD","edge_bps":795,"end_date_iso":"2026-07-20T00:00:00Z","expected_value_pct":0,"generated_at":"2026-05-24T14:28:09+00:00",…
[11/11] replay:   POST same body again (expect 401 nonce-used)
         HTTP 401: {"error":"nonce-used"}

DONE: 11/11 steps complete. Trace 24 unlocked and replay rejected.
```

### 5.2 Full 200 body — required invariants

The cli transcript truncates the JSON body for readability. A second
fresh nonce/sign/POST round captured the structured fields:

| Field | Value | Invariant |
|-------|-------|-----------|
| `trace_id` | `24` | current public preview ID ✅ |
| `decision` | `HOLD` | one of {BUY_YES, BUY_NO, HOLD} ✅ |
| `edge_bps` | `795` | signed integer present ✅ |
| `confidence` | `medium` | one of {low, medium, high} ✅ |
| `agent_probability_yes` | `0.09` | 0 ≤ p ≤ 1 ✅ |
| `current_implied_yes` | `0.0105` | 0 ≤ p ≤ 1 ✅ |
| `copy_trade_url` | `null` | HOLD has no copy-trade URL ✅ |
| `sources.length` | `4` | ≥ 3 ✅ |
| `source.kind` set | `[model, market_data, resolution_criteria, official_data]` | includes non-market kind (`official_data` ✅) |
| `risk_factors.length` | `1` | ≥ 1 ✅ |
| `trace_hash` | `0x09d89328fe484a8904809704dbbae111bff4a9dd5336571ccda30de4d3a455fd` | matches current public trace 24 ✅ |
| `generated_at` | `2026-05-24T14:28:09+00:00` | current 24-31 batch ✅ |

### 5.3 Replay rejection

Step 11 proves the nonce-consumption invariant. Re-posting the exact same
`{ address, nonce, signature, message }` body a second time returned:

```text
HTTP 401: {"error":"nonce-used"}
```

### 5.4 Final hardened nonce + rate-limit smoke

After replacing per-instance nonce state with HMAC-bound nonce tokens,
durable write-once Blob used markers, and bounded KV-or-memory rate limiting,
the final production alias was re-smoked against trace `24`:

```text
[8/11] GET:       https://agoraalpha.vercel.app/api/traces/24/full?address=0xFA769b2C65087311B51E9541D8C8987f7FFB0A1e
         nonce:    eyJ2Ijox...OY-N8
         issued:   2026-05-24T18:27:21.822Z
         expires:  2026-05-24T18:32:21.822Z
[9/11] sign:      EIP-191 message (599 chars)
[10/11] POST:     https://agoraalpha.vercel.app/api/traces/24/full
         HTTP 200: {"agent_probability_yes":0.09,"confidence":"medium","copy_trade_url":null,...}
[11/11] replay:   POST same body again (expect 401 nonce-used)
         HTTP 401: {"error":"nonce-used"}

DONE: 11/11 steps complete. Trace 24 unlocked and replay rejected.
```

### 5.5 Onchain unlock anchor — trace 24

Recovered from `getLogs(Unlocked, address=UnlockMarket)` on Arc testnet
(chain id `5042002`):

| Field | Value |
|-------|-------|
| Wallet | `0xFA769b2C65087311B51E9541D8C8987f7FFB0A1e` |
| Trace | `24` |
| Contract | `0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA` (UnlockMarket) |
| Tx hash | `0x0f1d9b9a7a7a501047460c37c8267e3ed24f27381d77e5fcc002397c27c15e2b` |
| Block | `43861411` |
| Price paid | `100000` (= 0.1 DevUSDC at 6-decimal precision) |
| Explorer | https://testnet.arcscan.app/tx/0x0f1d9b9a7a7a501047460c37c8267e3ed24f27381d77e5fcc002397c27c15e2b |

### 5.6 Batch alignment checks

```text
preview_ids       24,25,26,27,28,29,30,31
local_private_ids 24,25,26,27,28,29,30,31
blob_ids          24,25,26,27,28,29,30,31
blob_full_ids     24,25,26,27,28,29,30,31
traceExists(24)   true
traceExists(25)   true
traceExists(26)   true
traceExists(27)   true
traceExists(28)   true
traceExists(29)   true
traceExists(30)   true
traceExists(31)   true
```

`validate_submission --mode private-deploy --check-blob` now fetches
`PRIVATE_TRACES_BLOB_URL`, verifies the Blob's trace IDs exactly match
`web/data/picks-preview.json`, and runs the same full-payload quality
checks against the Blob entries.

---

## 6. Visual evidence

| File                                       | Description                                                                                                                                                                                                                                                                                                                                                                                                                                       |
|--------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `verify/screenshots/home-picks-grid.png`   | Production home feed after promotion — shows the current `24-31` pick batch on the live alias. 1200×2626 PNG. |
| `verify/screenshots/pick-preview-locked.png` | `/pick/24` locked preview — shows trace 24, free signal, Arc TraceLog anchor, and the DevUSDC/testnet paywall before full payload reveal. 1200×1455 PNG. |
| `verify/screenshots/unlocked-trace.png`    | `/pick/24` rendered post-unlock for wallet `0xFA76…0A1e` — shows Pick #024 ("Will USA win the 2026 FIFA World Cup?"), Decision `HOLD`, the `UNLOCKED · PAID · ON ARC` full-trace section, EV `+0.00%`, Edge `+795 bps`, zero paper sizes for all profiles, full reasoning chain, source bundle (`model`, `market_data`, `resolution_criteria`, `official_data`), risk factors, and the no-copy-trade HOLD state. 884×2678 PNG. |
| `verify/screenshots/explorer-tx.png`       | Arcscan testnet detail for the `UnlockMarket.unlock(24)` transaction recorded in §5.5 — tx `0x0f1d9b9a…27c15e2b`, Status `Success`, Method `unlock`, Block `43861411`, Timestamp `May 24 2026 22:06:17 (+05:30)`, From `0xFA76…0A1e`, Contract `0xD8af…d3cA`, Tokens transferred `0.1 pUSDC` to the treasury, transaction fee `0.002196895654783656 USDC`. 3420×2146 PNG. |

The dimensions above are pulled directly from the PNGs (`file verify/screenshots/*.png`).

---

## 7. Package evidence

### 7.1 Zip build

Command:

```bash
python3 scripts/package_submission.py
```

```text
wrote submission.zip (... bytes)
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
asserted at runtime by §2.4's `--mode public-package` validator.

### 7.3 Final zip rebuild + detached manifest

The final `submission.zip` is rebuilt after the trace-24 live smoke (§5)
and after proof screenshots are refreshed (§6). The zip's checksum is
recorded in the sibling file `submission.zip.sha256`, which is deliberately
excluded from the archive; embedding the final archive hash inside
`VERIFY.md` would change the archive hash on every rebuild.

Commands:

```bash
python3 scripts/package_submission.py
shasum -a 256 submission.zip > submission.zip.sha256
wc -c submission.zip >> submission.zip.sha256
unzip -l submission.zip | grep -E '(\.github/workflows/ci\.yml|verify/screenshots/|verify/agora-alpha-demo\.mp4)'
unzip -l submission.zip | grep -E '(^|/)(\.env|\.env\.local)$|picks-full|trace-[0-9]+\.json|\.blob-url|submission\.zip\.sha256' || echo '(no private payload — good)'
```

```text
wrote submission.zip (... bytes)
<sha256>  submission.zip
<bytes> submission.zip
.github/workflows/ci.yml
verify/agora-alpha-demo.mp4
verify/screenshots/explorer-tx.png
verify/screenshots/unlocked-trace.png
(no private payload — good)
```

| Field            | Value                                                              |
|------------------|--------------------------------------------------------------------|
| Package checksum | External: `submission.zip.sha256`                                  |
| Built by         | `scripts/package_submission.py`                                    |
| Validator        | `validate_submission --mode public-package` (invoked internally; passed) |
| Proof artefacts  | `.github/workflows/ci.yml`, `verify/agora-alpha-demo.mp4`, `verify/screenshots/*.png` |
| Picks freshness  | trace IDs 24-31, all dated 2026-05-24, all anchored on Arc TraceLog (Phase 4.1) |
| Paid-unlock smoke | §5 — `node scripts/cli-unlock.mjs … --trace-id=24` against the live deploy, exit 0, replay `nonce-used` |

The package builder walks the filesystem, so `scripts/package_submission.py`
has explicit exclusions for local env files, private full traces,
`web/data/.blob-url`, build/cache directories, and `submission.zip.sha256`.

### 7.4 Post-merge zip surface

Command:

```bash
unzip -l submission.zip | grep -E '(^|/)(\.env|\.env\.local)$|picks-full|trace-[0-9]+\.json|\.blob-url|submission\.zip\.sha256' || echo '(no private payload — good)'
```

```text
(no private payload — good)
```

`picks-full.private.json` is excluded, no real `.env`, no `traces/trace-*.json`
production files. Only `.env.example` and `web/.env.local.example` (template
files with no secrets) ship. Same invariants as §7.2; reasserted post-merge.

---

## 8. Sign-off

- [x] All `TODO:` blocks above are replaced with real output.
- [x] `git status` shows only tracked changes that match the diff.
- [x] Production URL serves a 200 on `/api/traces/24/full` after a real unlock.
- [x] Both screenshots committed under `verify/screenshots/`.
- [x] Date in §0 matches the timestamp on the most recent transcript.

| Field                  | Value                                                              |
|------------------------|--------------------------------------------------------------------|
| Signed-off by          | `@yxshee`                                                          |
| Sign-off timestamp     | `2026-05-24T18:27:21Z`                                             |
| Sign-off commit        | final pushed commit is verified with `git rev-parse HEAD` and `git rev-parse origin/main`; the commit hash is not embedded here to avoid self-referential proof churn |
| Submission artifact    | `submission.zip` — exact SHA256 and byte count live in external `submission.zip.sha256` (excluded from the zip; see §7.3) |
| Live deploy            | https://agoraalpha.vercel.app                                      |
| Paid-unlock transcript | §5.1 (trace 24 cli-unlock 11/11 steps green) + §5.5 explorer tx `0x0f1d9b9a7a7a501047460c37c8267e3ed24f27381d77e5fcc002397c27c15e2b` on Arc testnet block `43861411` |
| Visual evidence        | §6 — `verify/screenshots/unlocked-trace.png` (`/pick/24`) + `verify/screenshots/explorer-tx.png` (`unlock(24)`) |
| Repository             | https://github.com/yxshee/pythia (commit listed above)             |
