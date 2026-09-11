# Money Tree AI — Positioning

## What it actually is

A Windows desktop app (+ phone dashboard + Telegram bot) for researching US
stocks and mechanically testing a trading strategy. Open source, MIT, runs
locally. Three modes: `signal` (tells you what to do, you execute in Midas —
built because Midas has no trading API), `paper` (simulated money, real
prices), `live` (real money via Alpaca, gated behind an explicit Arm step that
starts disarmed on every run).

Verified against source (`app/research/`, `app/strategy/`, `app/risk/`):
the company-research screen, the Simple/Advanced reading-level toggle, and the
"no data = says so, never a zero or a guess" behavior are all real and shipping,
not brief-only claims.

## What it is not

Not a signals service. Not an investment advisor. Not a promise of profit. The
EMA/RSI strategy's own backtest (588 trades, 1yr hourly, 8 symbols) lands within
a rounding error of break-even at every stage — profit factor never leaves 1.0.
Risk management (adapted from Freqtrade) cut worst drawdown from 11.7% to 5.4%
and raised win rate, but did not make the strategy profitable. This number is
published in the README, not hidden.

## Primary positioning

**"Understand US stocks without a finance background."**

The wedge is the research screen + Simple/Advanced toggle: same real data
(Yahoo-sourced, ~15min delayed, every field shows its source and freshness),
explained at the reader's level instead of assuming fluency in P/E ratios and
EMA gaps. This is the thing competitors (a screener, a Bloomberg terminal, a
subreddit) don't do — they show numbers, not what the numbers mean to a
non-finance person.

## Supporting pillars

1. **Honest by construction, not by disclaimer.** A missing field renders as
   "not available," never a placeholder zero or an invented estimate — this is
   enforced in `app/research/models.py`'s `Provenance` dataclass, not just
   written on a landing page. The backtest that says "this doesn't clearly
   work" ships in the same README as the pitch.
2. **Runs on your machine.** Local-first: Ollama backend needs no account and
   nothing you type leaves the machine. Your data, your `.env`, your box.

## What we will never say

No profit/return promises, no "X% win rate" pulled out of context, no fabricated
reviews, screenshots, or user counts, no investment-advice framing, no
positioning the founder as a financial expert. Every backtest number quoted in
any content must trace back to the table in the README's "Did any of it help?"
section — never a cherry-picked row presented without the others.
