# Money Tree AI

An automated US stock trading bot with a desktop app, a phone dashboard, a
Telegram bot you can talk to, and an AI that explains every decision it makes —
live, in a panel down the left-hand side.

It runs in one of three modes:

| Mode | What it does | What you need |
|---|---|---|
| **`signal`** | **Midas mode.** Analyses the market and tells you exactly what to buy or sell; you place it in Midas yourself. | Nothing. No brokerage API. |
| `paper` | Trades by itself with simulated money on real prices. | Nothing. |
| `live` | Trades by itself with real money through Alpaca. | An Alpaca account. |

## Why signal mode exists

**Midas has no API.** Their own broker listing says so plainly: *"Algoritmik işlem
ve API erişimi sunulmamaktadır"* — algorithmic trading and API access are not
offered. No bot can place an order in Midas, and the only ways around that
(reverse-engineering their private app API, or scripting taps on the phone) break
their terms, risk your account, and shatter on every app update.

So the bot splits the job. It does the part a computer is good at — watching eight
tickers all day, computing indicators, sizing positions, enforcing stops — and
hands you the part only you can do: pressing buy in Midas. You get a message with
the ticker, share count, entry, stop, target and the reason. You place it, tap
**Taken**, and the bot tracks that position and tells you when to get out.

If you later want full automation, open a free Alpaca account (it accepts Turkish
residents — US residency is **not** required), set `mode: live`, and the same
brain starts placing its own orders. Nothing else changes.

## Setup

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

```bash
copy config\.env.example .env
copy config\config.example.yaml config\config.yaml
```

`.env` holds your keys and never leaves your machine. `config/config.yaml` holds
the watchlist, timeframe and risk limits.

Signal mode needs **no keys at all** — market data comes from a free public feed.

### Telegram (recommended)

1. Message [@BotFather](https://t.me/BotFather), send `/newbot`, follow the prompts.
2. Put the token in `.env` as `TELEGRAM_BOT_TOKEN`.
3. Message [@userinfobot](https://t.me/userinfobot) to get your numeric chat id.
4. Put it in `.env` as `TELEGRAM_CHAT_IDS`. Only listed ids can talk to the bot.
5. **Open your new bot and press Start.** Telegram does not let a bot message you
   until you have messaged it first — skip this and the log says `Chat not found`.

Copy the token as text, not from a screenshot: `l` and `1`, `O` and `0` look
identical in Telegram's font, and a single wrong character gets the token rejected.

## Run

Double-click **`Money Tree AI.bat`**. That is the whole thing — it starts the app
with no console window.

To build a real `.exe` you can pin to the taskbar:

```bash
.venv\Scripts\python scripts\make_logo.py
.venv\Scripts\python scripts\build_exe.py
```

That produces `dist\Money Tree AI\Money Tree AI.exe`. It is a folder build, not a
single file — a one-file build has to unpack Qt's browser engine to a temp
directory on every launch, which is slow and sometimes upsets antivirus. Copy the
whole folder wherever you like and put your `.env` beside the exe.

**The exe keeps its own `data/`.** It reads `config/`, `.env` and `data/` from
beside itself, so it has a separate database from the source checkout — an open
run does not follow you across. To carry one over, copy `data\trading.db` into the
exe folder while both are closed. Run one or the other, not both: they would fight
over the same port and the same database.

From a terminal, if you prefer:

```bash
.venv\Scripts\python -m app.main
```

The console prints a desktop link and a phone link. Open the phone link in your
browser while on the same Wi-Fi. Closing the window keeps the bot running in the
system tray.

### Running it around the clock

```bash
.venv\Scripts\python scripts\install_startup.py
```

That puts a shortcut in your Startup folder so the bot comes back up on its own
after a reboot. `--remove` takes it out again.

Be clear-eyed about what this gets you: the bot runs whenever the PC is on and
awake. It stops when the machine sleeps or shuts down. Genuinely uninterrupted
running needs a machine that never sleeps, or a small VPS — see *Known limits*.

Headless, for a server or a spare machine:

```bash
.venv\Scripts\python -m app.main --headless
```

## What you get

**Dashboard** — six tabs across the top, live New York and İstanbul clocks in the
header, and a market bar that reads *"Market closed until Monday 16:30 İstanbul
(09:30 New York) — opens in 2d 4h 51m"* and counts down by the second.

| Tab | What is on it |
|---|---|
| **Overview** | The run (below), equity, daily P&L against the loss budget, open positions, performance, and a live feed of what the bot is thinking |
| **Chart** | Full-height candles with EMAs, entry/stop/target lines drawn on any held position, plus a plain-English read of the symbol |
| **Watchlist** | Every ticker with price, window change, trend, EMA gap, RSI and volatility. Click a row to jump to its chart |
| **Mentor** | The live chat (below) |
| **History** | Every closed trade with entry, exit, P&L and the reason it closed |
| **Go Live** | The step-by-step guide to trading real money, with live status per step |

**Signal cards** — when the bot finds a trade, a card appears at the top of the
dashboard and a message lands in Telegram: shares, entry, stop, target, cash at
risk, reward-to-risk, and why. Two buttons: **Taken** (with an optional real fill
price) or **Skipped**.

**The run** — hand the bot a small stake and name a target: pick $1/$5/$10/$25/$50/$100
and 1.5×/2×/3×/5×, and it trades **only that money**, one position at a time, until it
reaches the target or falls through the floor. A progress dial tracks it live, and it
ends itself either way.

Before you start, it shows the arithmetic rather than a promise:

> $5.00 → $10.00 — Each win adds 4% and each loss takes 2%. Getting there needs roughly
> **18 winning trades with no losers in between** — losses push it further away. The run
> ends by itself if the stake falls to $2.50.

That number is computed, not decorative. Doubling a stake with a 4% target is a long
shot, and the app says so up front. **No money changes hands — this is paper money, and
nothing is charged or withdrawn.**

Runs need fractional shares (a $5 stake cannot buy a whole $300 share), which is on by
default and supported by Alpaca.

**Catalysts** — a calendar of events you expect to move a stock: a game launch, a
film, an earnings date, a ruling. You add the event, the ticker, the date and why
you think it matters. The app counts down, tells you when your entry window opens,
and puts the real headlines for that ticker next to your thesis so you can see
whether the story still holds.

Dates can be loose — `2026-11` means "some time in November", which is usually all
a release window gives you.

Two things this deliberately does **not** do:

- **It does not trade for you.** Catalysts are a calendar and an alarm clock for
  trades *you* decide to make. The mechanical EMA strategy runs separately and
  ignores them. Mixing a discretionary event bet into an automated trend system
  would make both worse and neither explainable.
- **It does not pretend events are free money.** A date everyone knows is already
  in the price. Stocks routinely peak *before* the event and sell off on the day —
  "buy the rumour, sell the news" is a cliché because it keeps happening. And a
  delay can undo the whole thesis: Take-Two has fallen on every GTA 6 delay. The
  app says this on the screen, not just here.

**The AI panel** — a permanent column down the left of the app. The bot narrates
itself into it as it works, and the composer at the bottom is always there, so you
can ask a question from any screen without leaving what you were looking at. On a
phone it slides up as a sheet from the button in the top-left.

It remembers the conversation, so follow-ups work: ask *"why didn't you buy NVDA"*
and then just *"and what about TSLA"*.

```
AAPL at 309.42 — EMA12 309.55 is below EMA26 310.40 (-0.27%), holding for 30 bars. RSI 42.
AAPL caught my eye: EMA12 is -0.27% against EMA26 with RSI at 42.
AAPL: sizing 8 at 309.42 = $2,475.36, 9.9% of $25,000.00 equity.
AAPL: stop 303.23, target 321.80. Risking $49.51 to make $99.01 — 2.0:1.
META: wanted to buy but I hold 0 and have 3 signals waiting, and my cap is 3.
```

Every number there is measured, not generated — the rule-based mentor cannot
invent a price, and it never predicts where anything will go.

### Giving it a real AI

Connect a language model and the panel also answers free-text questions, in the
chat and in Telegram. Four backends; `provider: auto` in `config.yaml` picks the
first that works, and it tries the free ones first so nothing bills you by
accident.

| Backend | Cost | Account | Setup |
|---|---|---|---|
| **Ollama** | free | none at all | Install from [ollama.com](https://ollama.com), then `ollama pull llama3.2` |
| **Gemini** | free tier | free, no card | Key from [aistudio.google.com](https://aistudio.google.com/apikey) → `GEMINI_API_KEY` |
| **Groq** | free tier | free, no card | Key from [console.groq.com](https://console.groq.com/keys) → `GROQ_API_KEY` |
| **Claude** | paid | paid | `ANTHROPIC_API_KEY` |

Ollama is the only one that needs no account: the model runs on your own
machine, so nothing you type leaves it. It is also the slowest, and the first
answer after a restart takes a while because the model has to load into memory.

The panel header names whichever model is actually answering, so you are never
guessing. With none of them configured the bot still narrates — it just cannot
hold a conversation, and it says so instead of pretending.

### What it remembers

Tell it something once and it keeps it, across restarts:

```
remember I place my real trades in Midas, not Alpaca
remember I am a beginner, keep it short
```

Those facts sit in the system prompt on every later answer, so it stops
re-explaining what you already know. They are listed at the top of the panel with
an × to drop one, and stored in `data/mentor_memory.json` — plain JSON you can
read or delete. The recent conversation is saved beside them, so closing the app
no longer loses the thread.

Same thing from your phone: `/remember ...`, `/memory`, `/forget 2`.

**Telegram** — `/status`, `/run`, `/positions`, `/watchlist`, `/pnl`, `/signals`,
`/chart AAPL`, `/catalysts`, `/remember`, `/memory`, `/forget`, `/add`,
`/remove`, `/close`, `/arm`, `/disarm`, `/equity 5000`.
Or just type a question. The command menu registers itself on startup.

To give the bot an avatar:

```bash
.venv\Scripts\python scripts\make_avatar.py
```

then send `assets/logo.png` to @BotFather with `/setuserpic`. Telegram only lets a
person set a bot's picture, so this last step cannot be automated.

## Backtest before you trust it

```bash
.venv\Scripts\python scripts\fetch_history.py --watchlist --timeframe 1h
.venv\Scripts\python scripts\run_backtest.py --watchlist --timeframe 1h
```

The backtest runs the same strategy through the same risk rules as the live
engine. **Do this first.** A default EMA crossover is not a money printer — on a
year of hourly BTC data the untuned defaults lost about 5%. Tune the settings in
`config.yaml` against real history before you act on a single signal.

## How it sizes and protects a trade

The risk machinery is borrowed from the open-source bots that have been doing this
for years — [Freqtrade](https://github.com/freqtrade/freqtrade) (53k stars) and the
position-sizing practice Jesse and most professional desks use.

**The stop comes first, the size falls out of it.** Rather than always spending a
fixed slice of the account, the bot fixes the *cash it can lose* — `risk_per_trade_pct`
of equity — and derives the share count from how far away the stop is. A tight stop
buys more shares, a wide stop buys fewer, and the money at risk is the same either
way. `max_position_pct` is still a hard ceiling on top.

**The stop is set from ATR, not a flat percentage.** A calm stock gets a tight stop,
a volatile one gets room to breathe, clamped between `min_stop_pct` and `max_stop_pct`.
The take-profit sits `reward_risk` stop-distances away, so the reward-to-risk ratio
holds no matter how wide the stop turned out.

**A trailing stop follows winners.** Once a trade is up by `activate_at_pct`, the stop
starts following the peak `trail_pct` behind it and never moves back down.

**Protections pause new entries** after the patterns that drain accounts:

| Lock | Trigger | Effect |
|---|---|---|
| Cooldown | any trade closes | that symbol only, `cooldown_minutes` |
| Stoploss guard | `stoploss_guard_trades` stop-outs inside the lookback | every symbol, `stoploss_guard_stop_minutes` |
| Max drawdown | equity falls `max_drawdown_pct` from its peak | every symbol, `max_drawdown_stop_minutes` |

Open positions are still managed while a lock is active — only new entries pause.

> One config trap worth knowing: if `risk_per_trade_pct` is set high relative to
> `max_position_pct`, the position cap binds first and risk sizing stops doing
> anything. The defaults are chosen so the risk rule is what actually decides.

### Did any of it help?

Measured on a year of hourly candles across the eight default symbols, adding one
piece at a time:

| Setup | Trades | Win rate | Return | Worst drawdown | Profit factor |
|---|---:|---:|---:|---:|---:|
| Original — fixed size, flat 2% stop | 588 | 42.7% | +0.53% | 11.69% | 1.04 |
| + ATR stop | 588 | 40.5% | +0.13% | 11.10% | 1.01 |
| + risk-based sizing | 588 | 40.5% | +0.19% | 10.03% | 1.02 |
| + trailing stop | 588 | 44.0% | +0.09% | 5.85% | 1.01 |
| + protections | 587 | 44.1% | +0.14% | 5.43% | 1.01 |

**Read this honestly.** The risk machinery cut the worst drawdown by more than half
(11.7% → 5.4%) and lifted the win rate, which is exactly what it is for. It did
**not** make the strategy profitable — every setup lands within a rounding error of
break-even, and profit factor never leaves 1.0.

Better risk control makes a losing strategy lose more slowly. It does not turn it
into a winning one. The EMA-crossover entry is the part that needs work — that is
what `scripts/run_backtest.py` is for.

## Safety model

- **Signal mode cannot spend your money.** It has no brokerage credentials.
- Live trading **starts disarmed every time.** Nothing persists the armed state,
  so a crash or restart can never leave it trading unattended.
- `mode: live` only *permits* live trading. You still press **Arm** and confirm.
- Every trade gets a **stop-loss and take-profit**, checked on every scan.
- A **daily loss limit** disarms live trading automatically when hit.
- Position size is capped per trade, and the number of open positions is capped.
- Telegram only obeys the chat ids in `TELEGRAM_CHAT_IDS`.
- Set `DASHBOARD_TOKEN` in `.env` — without it, anyone on your Wi-Fi who finds
  the port can control the bot.

## Tests

```bash
.venv\Scripts\python -m pytest tests -q
```

## Project layout

```
app/
  data/        market data sources (Yahoo keyless, Alpaca)
  execution/   signal (Midas), paper, and Alpaca order handling
  strategy/    indicators, Strategy interface, EMA/RSI strategy
  risk/        sizing, stops, arm/disarm, daily loss kill switch
  engine/      the watchlist scanner and the backtester
  mentor/      rule-based narrator + optional Claude commentary
  notify/      Telegram bot and message formatting
  storage/     SQLite: trades, open positions, equity curve, candle cache
  web/         FastAPI server, WebSocket, dashboard (HTML/CSS/JS)
  gui/         PySide6 window and tray icon
```

Adding a market means writing one `MarketDataSource` and one `Executor`. The
strategy, risk and engine code does not change.

## If the exe will not start

A windowed build has nowhere to print a crash, so it writes one instead:
`dist\Money Tree AI\logs\crash.log`. The last line names the actual problem.

Two traps that already bit this build, in case they come back:

- **`sys.stdout` is `None` in a `--noconsole` build.** Anything that prints, or
  any logging handler that writes to a stream, raises `AttributeError` on a
  `NoneType`. `app/main.py` swaps in a null stream before doing anything else,
  and uvicorn is started with `log_config=None` because its colour formatter
  calls `sys.stdout.isatty()`.
- **PyInstaller cannot see dynamic imports.** uvicorn picks its event loop and
  protocol classes by name at runtime, so they need `--collect-submodules
  uvicorn`; the same goes for the broker and AI SDKs.

## Known limits

- Yahoo data is delayed roughly 15 minutes. Fine for 15m-and-slower strategies,
  not for scalping. Alpaca keys switch it to a live IEX feed.
- Stops are enforced by the engine, so the bot must be running for them to fire.
  In `live` mode orders are sent as Alpaca brackets, so those sit on the exchange
  and survive the bot being closed.
- The bot only trades while the US market is open. It idles overnight and at
  weekends, and the dashboard shows the countdown to the next open.
- Long only, whole shares, one position per symbol.
