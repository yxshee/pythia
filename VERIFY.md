# Pythia Agora Alpha — Master Deploy Verification Prompt

## Release evidence — 2026-05-23

Final local and production checks passed before creating `submission.zip`:

```text
agent:     uv run python -m unittest discover -s tests
           12 tests passed

agent:     uv run python -m pythia.scripts.validate_submission
           submission data ok: 8 home markets, 8 private full traces

web:       pnpm exec tsc --noEmit
           passed

web:       pnpm build
           Next.js production build passed

contracts: forge test -vvv
           42 tests passed

live:      https://agoraalpha.vercel.app
           / returned 200 with 8 pick links and security headers
           /pick/16 returned 200
           /pick/1 returned 404
           SSR HTML had 0 occurrences of full-payload JSON keys, private snapshot names, or fixture source markers
           /api/rpc rejected eth_sendRawTransaction with 403
           /api/rpc rejected oversized body with 413
           /api/rpc rejected 11-call batch with 400
           /api/traces/16/full rejected missing fields with 400
           CLI wallet-equivalent flow minted DevUSDC, approved 0.10, unlocked registered trace 16,
           signed a nonce-bound message, fetched full payload with 200, and rejected replay with nonce-used

onchain:   UnlockMarket 0xD8af5ebe36AC9eA736f40D749674FF1B0f4bd3cA
           traceExists(9..16) = true
           traceExists(999) = false
```

You are a senior QA engineer auditing the production deploy. Be exhaustive. Be skeptical. Cite file:line for every finding.

## Target
- **Live URL**: `https://agoraalpha.vercel.app` (override with first argument if the user passes a different URL)
- **Repo**: `/Users/Shared/pythia` (web app under `web/`)
- **Stack**: Next.js 16 App Router · React 19 · Tailwind v4 · static + 30s ISR · server routes: `/api/rpc` (Arc proxy) and `/api/traces/[id]/full` (wallet-signature-gated paywall fetch)

## Required tools
- **Chrome DevTools MCP** — primary browser (`navigate_page`, `take_snapshot`, `list_console_messages`, `list_network_requests`, `lighthouse_audit`, `take_screenshot`, `resize_page`, `evaluate_script`)
- **Bash** — `curl`, `grep`, `git`, `npx tsc`, `npm run build`
- **Read / Edit / Write** — code-level audits and the auto-fixes listed below

If Chrome DevTools MCP is unavailable, fall back to `curl -sIL` for header/status checks plus Playwright if installed; otherwise stop and tell the user.

## Critical context — read before suggesting any Next.js code
`web/AGENTS.md` warns: "This is NOT the Next.js you know. APIs and conventions may differ from training data. Read `node_modules/next/dist/docs/` before writing code." Verify any Next.js API against the installed docs before recommending it.

## Method
Execute Phase 1 → Phase 12 in order. Keep a running scratchpad of findings. Produce the report at the end in the exact format under §"Final report".

---

### Phase 1 — Pre-flight
- [ ] `curl -sI https://agoraalpha.vercel.app` → status 200, capture all response headers for Phase 11.
- [ ] Confirm `git status` is clean. If not, list dirty files and **ask** before any auto-fix.
- [ ] `git rev-parse --short HEAD` → record for the report.

### Phase 2 — Smoke + 404 surface
- [ ] `navigate_page /` → 200, document `<title>` non-empty and not "Next.js"; `list_console_messages` returns **zero** errors/warnings (record any); `list_network_requests` shows no 4xx/5xx.
- [ ] `navigate_page /pick/{first_trace_id_from_home}` → same checks.
- [ ] `navigate_page /pick/999999` → 404 page (Next.js default), **not** 500.
- [ ] `navigate_page /this-route-does-not-exist` → 404.

### Phase 3 — Navigation integrity
- [ ] Click logo "Agora / ALPHA" → lands on `/`.
- [ ] Click "Picks" → `/`.
- [ ] "Hackathon ↗" link: `href = https://agora.thecanteenapp.com/`, `target=_blank`, `rel` contains `noopener`. Reach the external URL with `curl -sIL` → final status 200.
- [ ] Grep `web/components/header.tsx` and any layout for nav links; confirm **no** dead routes.

### Phase 4 — Functional flows
- [ ] Click the first pick card on `/` → routes to `/pick/{trace_id}`.
- [ ] On the detail page:
  - "← back to picks" link returns to `/`.
  - "Unlock 0.10 DevUSDC" button is wired: connect-wallet opens an injected-wallet picker; on Arc (chain `5042002`) the button approves exact 0.10 USDC and calls `UnlockMarket.unlock(traceId)`. Verify the call lands by checking the on-chain anchor card refreshes. **DO** flag any stale date copy adjacent to the button.
  - Arc trace hash element exposes the full hash via `title` (hover tooltip).
  - Every external link (`docs.arc.network`, etc.) opens in a new tab with `rel=noopener`.

### Phase 5 — Data integrity
On `/`:
- [ ] Each pick card has non-empty question text, a decision in `{BUY_YES, BUY_NO, HOLD}`, and probabilities formatted `XX.X%`.
- [ ] Heading "Today's picks · N" — N equals rendered card count.

On `/pick/{id}`:
- [ ] Pick number padded to 3 digits.
- [ ] `generated_at` rendered as locale string, NOT "Invalid Date".
- [ ] Delta sign matches relation between `agent_probability_yes` and `current_implied_yes` (positive → agent thinks YES is undervalued).
- [ ] All preview fields render (confidence, risk, resolves, builder code, Arc trace hash, theme).

### Phase 6 — Responsive
Use `resize_page` and take a screenshot at each:
- [ ] 375×812 (mobile) — no horizontal scroll, header readable, cards stack 1-col.
- [ ] 768×1024 (tablet) — grid breaks to multi-col where expected.
- [ ] 1280×800 (desktop) — `max-w-6xl` constraint visible, layout balanced.

### Phase 7 — Accessibility
- [ ] `lighthouse_audit` (a11y) on `/` and `/pick/{id}` → score ≥ 95. Record exact score.
- [ ] One `<h1>` per page; heading levels not skipped.
- [ ] Color contrast on parchment/ink palette passes WCAG AA (Lighthouse covers this; spot-check `text-ink-faint` on `bg-marble`).
- [ ] Decorative SVGs (Greek-key background, "→" glyph) marked `aria-hidden` or have meaningful alt.
- [ ] Keyboard pass: Tab through both pages — every interactive element is reachable with visible focus.

### Phase 8 — Performance
- [ ] `lighthouse_audit` (performance, mobile) on `/` → score ≥ 85; `LCP < 2.5s`; `CLS < 0.1`.
- [ ] Same on `/pick/{id}`.
- [ ] No render-blocking resources besides Google Fonts; fonts load `display=swap` (verify via DevTools).
- [ ] `x-vercel-cache: HIT` or `STALE` on a second request (ISR working).

### Phase 9 — SEO & metadata
- [ ] `<title>` and `<meta name="description">` present and meaningful.
- [ ] OG tags: `og:title`, `og:description`, `og:image`, `og:url` — `og:url` matches the deployed origin.
- [ ] Favicon (`icon.svg`) returns 200 in the network tab.
- [ ] `robots.txt` and `sitemap.xml` — note whether present; if absent and the user wants SEO, flag (don't add).

### Phase 10 — Console & network hygiene
- [ ] Zero console errors / warnings across both pages and all three viewports (note deprecations).
- [ ] Zero failed asset requests.
- [ ] No CORS errors.

### Phase 11 — Security headers (from Phase 1 capture)
- [ ] `strict-transport-security` present.
- [ ] `x-content-type-options: nosniff` present.
- [ ] `referrer-policy` set to `strict-origin-when-cross-origin` or stricter.
- [ ] `x-frame-options: DENY` OR CSP `frame-ancestors 'none'`.
- [ ] CSP — confirm the minimal policy from `next.config.ts` is present.

### Phase 12 — Code-level audit
- [ ] `cd web && npx tsc --noEmit` — zero errors.
- [ ] `cd web && npm run build` — succeeds; note bundle sizes.
- [ ] Search web source for unfinished-code sentinels and list findings.
- [ ] `grep -rn "console\.log" web/` — none in production code.
- [ ] Unused-export sweep: any export in `web/lib/**` and `web/components/**` with zero importers — list them.
- [ ] Hardcoded dates in source — list each.

---

## Known issues — recheck before reporting

The previous dead export, stale dated badge, and hardcoded version badge were
removed before this prompt was refreshed. Reconfirm they remain absent during
Phase 12, then report any new findings from the current tree.

## Fix protocol
- **Auto-fix without asking**: dead exports, unused imports, stale hardcoded dates that have already passed, missing `rel=noopener`, missing `aria-hidden` on decorative SVGs, obvious typos in non-product copy.
- **Ask first**: any user-visible copy change beyond a stale date, design-token edits, `next.config.ts` edits, dependency add/remove, anything affecting rendered layout.
- **Report only (no edits this pass)**: missing tests, missing CI, missing CSP, missing `robots.txt`/`sitemap.xml`, missing error boundary / custom 500, observability gaps.
- **Stop conditions**: production unreachable (5xx) → abort + report; `npm run build` fails after any auto-fix → revert + report; a "safe" fix grows to touch >3 files → ask first.

## Final report

Print exactly this structure, then stop.

```
# Verification Report — agoraalpha.vercel.app
Date: <ISO>
Commit: <short SHA>

## Passed (N checks)
- <one line each>

## Bugs (N found · M auto-fixed · K awaiting approval · J out-of-scope)
- [P0|P1|P2|P3] <description> — <file:line> — <FIXED | NEEDS APPROVAL | DEFERRED>

## Redundancies removed
- <file:line> — <what was removed>

## Needs manual review
- <file:line> — <why I did not auto-fix>

## Lighthouse
- /       perf <N> · a11y <N> · best-prac <N> · seo <N>
- /pick/* perf <N> · a11y <N> · best-prac <N> · seo <N>

## Evidence
Screenshots: /tmp/pythia-verify-<timestamp>/
```

## How to run
Paste this entire file into Claude Code (Chrome DevTools MCP enabled). Or: `claude --print "$(cat VERIFY.md)"`.
