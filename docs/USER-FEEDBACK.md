# User Feedback

Early validation for the long-tail sports prediction-market wedge.

This file is a live scaffold. Empty rows mean the response has not landed yet
— the file fills in as testers reply. See git history for response
timestamps; no quote in this file is paraphrased or composed.

## Methodology

We are validating one specific claim before scaling the agent: **would
a Polymarket sports trader pay 0.10 DevUSDC to read Pythia's reasoning
before placing a bet on a long-tail outcome?** Target segments:

1. NBA bettors active on Polymarket (Spurs / Knicks / Finals odds).
2. NHL bettors active on Polymarket (Stanley Cup futures).
3. Cross-vertical Polymarket users who already trade prediction-market
   reasoning newsletters (Manifold, Kalshi watchers).

Each tester is shown one live trace from `agoraalpha.vercel.app/pick/<id>`
matching their vertical, walked through the public preview, and asked
whether the paid full trace would change a real bet. Responses captured
verbatim. No quote is composed.

## Outreach script

```text
I built a paid AI reasoning trace for long-tail sports prediction markets.
Can you look at one NBA/NHL/World Cup trace and tell me:
1. Would you pay 0.10 USDC to unlock this before betting?
2. What source would make you trust it?
3. Would you prefer injury/news/odds movement/liquidity data?
```

## Responses

| Tester | Vertical | Would pay? | Main feedback | Requested source |
|---|---|---|---|---|
| [awaiting tester 1 response] | — | — | — | — |
| [awaiting tester 2 response] | — | — | — | — |
| [awaiting tester 3 response] | — | — | — | — |

## Completed unlock screenshots

None yet. The first external paid unlock will be recorded at
`verify/screenshots/external-unlock-1.png` with the tester's wallet address
(if consent given) or redacted (if not).

## Honesty note

The hackathon scoring rubric weights traction at 30%. Faking testers would
score worse than reporting zero, because reviewers can check the live
unlock-count surface and the `UnlockMarket` contract on Arcscan. The
`TractionStrip` component in the live app is deliberately blank in the
external-unlocks slot until the contract shows external paid unlocks
beyond the operator wallet `0xFA76…0A1e`.
