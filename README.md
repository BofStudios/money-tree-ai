# Money Tree AI

A Windows desktop app for researching US stocks and testing a mechanical trading
strategy. It has a desktop window, a phone dashboard on the same Wi-Fi, a Telegram
bot you can talk to, and an AI panel that narrates every decision — and only ever
reasons about data it can actually see. Open source, MIT. It runs on your machine
and sends your data nowhere.

**It does not promise returns.** In a year of hourly backtests the built-in
EMA/RSI strategy landed within a rounding error of break-even; the risk rules
(adapted from Freqtrade) cut the worst drawdown by more than half but did not make
it profitable — the full table is under
[Did any of it help?](#did-any-of-it-help). This is a research and education tool,
not investment advice.

It trades only through Alpaca, in one of two modes:

| Mode | What it does | What you need |
|---|---|---|
| `live` | Trades by itself with real money through Alpaca, behind an explicit **Arm** step that starts disarmed every run. | An Alpaca account and its live keys. |
| `paper` | Trades by itself with practice money: your Alpaca paper account once its keys are saved, otherwise a simulation on this PC. | Nothing. Alpaca paper keys are optional. |

Practice money stays because it is the only way to see the bot work before any
money is at risk, and because a new Alpaca live account cannot trade until it
is funded. (Midas signal mode was removed in 4.0: an old config that still says
`signal` starts on practice money.)

## Desktop 4.0: Stop that stops, plain words, two editions

**Stop.** The red **STOP** switch is in the top bar on every screen. From the
moment you press it the bot sends no buy order and sells nothing on a signal,
even in the middle of a scan: the check sits right before the order is sent.
Buys waiting for your approval are cancelled. Stop-loss and take-profit stay
active, because they protect what you hold. The stop is saved to
`data/engine_state.json`, so a restart does not start trading again; only
**START** does. Typing `stop` (or `dur`, `durdur`) in the chat or in Telegram
does the same thing at once. It never goes to the AI, which could say it
stopped the bot without doing it.

**Plain words.** Every step in the Live tab, the narrator and the AI answers
follow ASD-STE100 Simplified Technical English rules: one fact per sentence,
active voice, simple tenses. A step says what the bot does, the line under it
says what happened, and a finished step starts with "Done". The Turkish texts
follow the same rules.

**Two editions** (`app/edition.py`):

| | Personal (your copy) | Pro (the copy you sell) |
|---|---|---|
| Built with | source, or `build_exe.py --personal` | `build_exe.py` |
| Licence key | no | yes, checked against Lemon Squeezy |
| Telegram | yes | no, nothing is pre-connected |
| Risk per trade | your setting | at most 1% |
| Daily loss limit | your setting | at most 3% |
| Open positions | your setting | at most 5 |
| One stock | your setting | at most 25% of the account |
| Strategy bots | up to 10 | up to 4 |

The Pro limits are applied when the app starts, so editing `config.yaml` can
lower them but never raise them.

**Your keys never ship.** Alpaca, AI and Telegram keys live in `.env`, the
encrypted key store and `data/`. The build copies none of them and stops with
an error if one of those files ends up in the output.

### Selling the Pro edition

1. Create a product on [Lemon Squeezy](https://www.lemonsqueezy.com) with
   licence keys turned on and an activation limit (for example 2 PCs).
2. Put its store id and product id in `app/common/licensing.py`
   (`STORE_ID`, `PRODUCT_ID`).
3. Install Inno Setup once: `winget install JRSoftware.InnoSetup --scope user`.
4. Run `.venv\Scripts\python scripts\build_exe.py`. It writes
   `dist\MoneyTreeAI-Setup-<version>.exe`, the installer you sell.

The licence check needs no secret, so nothing private is inside the exe. A
buyer activates once per PC, and **Settings → Licence** frees the PC to move the
key to another one.

## Desktop 3.0: the research desk and the swarm

**A research desk before every buy.** Each stock gets the five checks a careful
long-term investor asks — business, moat, management, value, risk — from the
company's own SEC filings (data.sec.gov, no key), the same thresholds as the phone
app. On top of that, alternative data: 8-K events (earnings, leadership changes,
delisting or accounting warnings), insider filings in the last 30 days, the next
results date worked out from the rhythm of past ones, and Wikipedia page views as
a measure of how much attention a stock is getting. News comes from Alpaca's feed,
both for the stocks being watched and the whole market's wire. Headlines are
scored by a transparent word list, red flags (trading halts, bankruptcy, offerings,
fraud, guidance cuts, earnings in the next day) stop buys, and the AI reads the
headlines and can veto a buy. It also finds stocks the whole market keeps talking
about and runs the five checks on them.

**Learning from results.** Every buy signal is followed in its head — bought or
not — to its stop, target or sell signal. Once a kind of signal (for example *bad
news + far above its average*) has at least ten results that lose on average, it
becomes a rule: those buys are blocked, and mixed ones are bought smaller.

**The swarm: ten strategy bots in parallel.** Ten processes (Hawk, Viper, Raven,
Titan, Comet, Blaze, Specter, Nova, Onyx, Fang) each evolve trading strategies —
trend, breakout and pullback families — on real candles, together tens of thousands
of strategies a second. Only one strategy ever trades the account. A bot's best
replaces it only when it beats it on two stretches of history no bot trained on,
over enough trades (15 and 10), by a clear margin, at most once every 30 minutes;
a daily re-check rolls a change back if it stops working. The other bots
paper-trade their best on live candles for the leaderboard. **Reset** brings back
the original strategy at any time.

**It is heavy, and it says so.** On start the app warns that ten bots can use
1–2 GB of RAM and most CPU cores: other apps slow down, laptops heat up and drain
faster. Choose full power, light (two bots at 15%), or quit; bots and power can be
changed any time on the Swarm tab, and the bots run at below-normal priority.

**What it cannot do.** Evolved strategies that won on the past can still lose on
the future, and no check can see everything. This is not investment advice.

The look is new too: a yellow-dominant black theme and a new emblem
(`assets/mark.svg`, rendered by `scripts/make_logo.py` into the app icon, the
dashboard and `assets/pfp.png`).

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

Practice money needs **no keys at all**: market data comes from a free public feed.

### Alpaca keys

Paste them in the app: **Settings → Money & keys**. Each pair is checked with
Alpaca before anything is saved, then stored encrypted on this PC with Windows
DPAPI (`data/keys.dat`) — only your Windows account can read it back, and the page
never shows a key again, only its last four characters. Paper and live keys are
kept apart, so practice and real money never mix. Keys in `.env` still work; keys
saved in the app win.

New keys, or a switch between practice and real money, restart the app. Both are
refused from other devices unless `DASHBOARD_TOKEN` is set, because they decide
which account real orders go to. Switching to real money means typing a word, not
clicking a button — and the bot still starts disarmed.

If Alpaca refuses the saved keys at startup (say you regenerated them on the
phone), the app does not crash: it runs on the simulation, says so in the Live
tab, and marks the keys in red in Settings until you paste new ones.

### Telegram (personal edition only)

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

## The Android app

`android/` holds a separate app that runs the same strategy on the phone itself,
so the bot keeps trading with the PC off. Get the APK from the
[releases](https://github.com/BofStudios/money-tree-ai/releases) (the
`android-v…` ones) and open it on the phone; a new version installs over the old
one and keeps your keys and settings.

- **Around the clock.** A foreground service with an ongoing notification. While
  the US market is open it holds the processor awake so it looks every minute —
  Android's Doze would otherwise stretch that into many minutes with the screen
  off. While closed it sleeps, and an alarm wakes it a few minutes before the
  open. A heartbeat alarm restarts it if Android kills it, and it comes back after
  a reboot or an update. Allow it to run in the background when setup asks.
- **A notification for every trade.** *Just bought 0.0412 NVDA* — then the AI's
  two-sentence explanation added to the same notification. *Just sold NVDA ·
  +$0.42 profit (+2.3%)*, including when a stop or target fills at Alpaca while
  the phone is off. A summary when the market closes. On the *Everything* level,
  silent notes on what it is researching, stops it raised and buys the AI called
  off. Refused orders say why.
- **A research desk between the signal and the order (3.0).** Four gates, each of
  which can hold a buy back or make it smaller, none of which can start one:
  - *Five checks* from each company's own annual reports at the SEC (free XBRL
    API, no key): does the business make money, can rivals copy it (margins and
    returns), does management create value (buybacks vs. dilution, debt), is the
    price below a conservative value estimate (owner earnings discounted at 10%,
    converted for euro and krone reporters and ADR ratios), and what could go
    wrong. The answer is BUY ZONE, WAIT or AVOID; ETFs are judged on their trend.
  - *The daily trend*: no buying against a daily chart below its 50-day average.
  - *The news radar*: the Alpaca wire read on every look, scored by a finance word
    list (and by an AI when connected), sorted into topics, with red flags —
    offerings, halts, guidance cuts, earnings due — that hold buys back.
  - *What it learned*: every buy signal is followed to its stop, target or sell
    signal whether it was bought or not, and each kind of signal (RSI band, news
    mood, time of day, daily trend, the five checks, the stock) is scored in R.
    Averages are shrunk toward zero, and a kind only becomes a rule after ten
    results — so a few unlucky trades never do.
  Then two different AI models (with a free Groq key) read the headlines and the
  research side by side; either can stop the buy. All of it is on the Brain tab.
- **It improves itself (4.0).** Around the clock, a population of strategy
  settings (EMA lengths, RSI entry and exit, stop distance in ATRs, target ratio)
  is bred, mutated and replayed on months of real candles — thousands per
  second on a phone, at full speed on the charger and a tenth of that on
  battery. A new setting is adopted only if it beats the current one by 0.08R
  per trade on a stretch it never trained on (at least 15 trades) and also holds
  up on a second unseen stretch (at least 10 trades); at most once per half
  hour, logged with its numbers, and re-checked against the original every day
  with an automatic rollback. On pure random data it adopts nothing or one lucky
  setting a month, which the daily re-check can undo. It never touches the
  owner's risk per trade, position cap or daily loss limit.
- **Alternative data (4.0).** From the SEC's filing index (no key): new 8-Ks by
  item — bankruptcy, delisting notices, unreliable past financials and
  unregistered share sales are red flags — Form 4 insider-filing counts, and the
  next results date estimated from the company's own filing rhythm. From
  Wikipedia: daily attention against its usual level. All of it feeds the
  checks, the learner (attention is one of the buckets) and the AI's brief.
- **The whole market's news (4.0).** Besides the watchlist, the entire Alpaca
  news wire is read on every look. The most talked-about stocks are checked —
  tradable here, $5 or more, news not negative, the five checks at least a
  strong WAIT — and up to three are watched for three days.
- **Analysis around the clock (4.0).** With the market closed it still looks
  every quarter hour (news, filings, discovery, training), and sends a morning
  briefing half an hour before the open. A card on Home offers new versions as
  they are released on GitHub.
- **Stop means stop.** Stopping withdraws any buy order still waiting at Alpaca,
  a look already under way cannot send one, and no notification button brings a
  stopped bot back — only *Start* does. Every order the bot sends is listed with
  its time on the Portfolio tab.
- **Small accounts.** With under $500 it buys fractions of a share, but a whole
  share still wins wherever one fits, so its stop and target go to Alpaca as a
  bracket. A fraction's stop is placed at Alpaca as a stop order every trading
  day (Alpaca only takes day orders on fractions); its target is watched by the
  phone. Alpaca retired the pattern-day-trader limit on 4 June 2026, so a small
  account is no longer capped at three day trades a week.
- **Setup asks what matters.** Market, trade length, autonomy, roughly how much
  money, how bold each trade is (0.5%, 1% or 2% of the account per stop-out),
  how many positions at once, where to stop for the day, how much of the account
  it may use, which notifications, whether the AI may veto, and how picky the
  five checks are. All of it can be changed later in Settings.
- **Real money starts paused.** Every start is disarmed, and the armed state is
  never saved. A restart the owner did not start themselves — a reboot, an
  update, Android killing it — says so with a notification, and the home screen
  offers a one-tap *Arm* behind the phone's lock. Stops keep working meanwhile.

## What you get

**Dashboard** — tabs along the bottom, live New York and İstanbul clocks in the
header, and a market bar that reads *"Market closed until Monday 16:30 İstanbul
(09:30 New York) — opens in 2d 4h 51m"* and counts down by the second. Every
screen is in English and Turkish.

| Tab | What is on it |
|---|---|
| **Home** | Money first: whose money this is (real, Alpaca paper or simulated), the balance, today's change, what the AI has made or lost you, buttons for adding or withdrawing money through Alpaca, and *Switch to real money*, which opens the typed confirmation — never Alpaca. Then what the bot is doing right now, buys waiting for your OK, holdings and the day's numbers |
| **Live** | Every step the engine takes, as it takes it: checking the market, reading the account, fetching bars, analysing each stock, reading the news, placing an order, moving a stop, asking the AI to explain a buy. A step spins for exactly as long as the real call takes, shows its result underneath, and turns red if it failed. Filter to trades or problems, or press **Look now** |
| **Research** | A full company screen per symbol (below) |
| **Brain** | The five checks per stock with alt data, the news radar (mood per stock, the market wire, red flags, topics), what it has learned, and switches for every gate |
| **Swarm** | The ten bots: strategies tested, the strategy the account trades and how it scores on unseen data, the leaderboard, every change it made, power and bot count |
| **Chart** | Full-height candles with EMAs, entry/stop/target lines drawn on any held position, plus a plain-English read of the symbol |
| **Market** | Every ticker with price, window change, trend, EMA gap, RSI and volatility. Click a row to jump to its chart |
| **News** | Headlines for everything being watched |
| **Catalysts** | Events you expect to move a stock (below) |
| **Activity** | Every closed trade with entry, exit, P&L and the reason it closed |
| **Setup** | The step-by-step guide to trading real money, with live status per step |
| **Settings** | Money & keys, the market (US, Europe or both), trade length, autonomy, small-account mode, language and the AI |

**Money** — a screen for putting money in and taking it out, taken from Alpaca's
own funding guide: from Turkey, *Local Currency Transfer* (1.5%, at most $40) or
an international wire in US dollars, and how withdrawals and their fees work. One
button opens Alpaca. **The app never shows bank details and never moves money** —
only send money to the details shown inside your own Alpaca account.

**Windows notifications** — a buy, a sell, or a buy waiting for your OK pops up
from the tray while the window is not in front, the same moments the phone app
notifies about.

**Which market** — the first question on first launch: US stocks, European
companies, or both. Alpaca trades US exchanges only, so European companies are
bought through their US listings (ASML, SAP, Novo Nordisk, AstraZeneca, Shell,
TotalEnergies, Unilever) and VGK, a fund of the European market.

**Company research** — a full screen per symbol, built from a free data provider
(roughly 15 minutes delayed). Company profile, price snapshot, valuation ratios,
quality metrics, the three financial statements, earnings history with the
surprise on each report, analyst ratings and price targets, institutional
holders, insider transactions, and dividend history. Every block shows which
source supplied the number and how fresh it is. A **Simple / Advanced** toggle
sets how much explanation sits next to each figure — the underlying data is the
same at both levels. A number the provider does not have is shown as *"not
available"*, never a zero or an estimate, and the AI is told in its prompt that
it may not reason about a field it cannot see.

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

Runs need fractional shares (a $5 stake cannot buy a whole $300 share). That is
**small-account mode** in Settings, on by default and supported by Alpaca.

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
remember I am a beginner, explain things simply
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

- **Stop wins.** The STOP switch is checked right before every order, saved across
  restarts, and also works by typing `stop` in the chat or Telegram.
- **Stops live at Alpaca.** A whole-share buy goes in as a GTC bracket, so its
  stop-loss and target sit at Alpaca and protect the position overnight and while
  this PC is off (a DAY bracket's stop would expire at the close). A trailing stop
  is moved at Alpaca too, not just in the app's memory.
- **Fractional buys are the exception.** Alpaca refuses brackets on them, so their
  stop is watched by the app, which has to be running. When at least one whole
  share fits, the bot buys whole shares so the stop can sit at Alpaca.
- **It only touches what it bought.** Every order carries a `mtd-` client id; a
  sell cancels only that position's own stop and target, and positions it did not
  open are listed but never sold. A position a stop closed while the app was off
  is booked from Alpaca's real fill when it next looks.
- **Keys are encrypted at rest** and never sent back to the page.
- Live trading **starts disarmed every time.** Nothing persists the armed state,
  so a crash or restart can never leave it trading unattended.
- `mode: live` only *permits* live trading. You still press **Arm** and confirm.
- Every trade gets a **stop-loss and take-profit** — at Alpaca where it can, checked
  on every scan otherwise.
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
  execution/   practice (simulation) and Alpaca order handling
  strategy/    indicators, Strategy interface, EMA/RSI strategy
  risk/        sizing, stops, arm/disarm, daily loss kill switch
  engine/      the watchlist scanner, the Live feed's words, markets, backtester
  edition.py   personal vs pro: licence, Telegram, fixed safety limits
  brain/       the five checks, SEC/news/alt-data sources, news radar, learning, the swarm
  common/      the Live step monitor, the encrypted key store, in-app restart
  mentor/      rule-based narrator + optional AI (Groq, Gemini, Ollama, Claude)
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
- On Alpaca, whole-share positions carry their stop and target at the broker and
  survive the app being closed. Fractional positions, the simulation and signal
  mode rely on the app running to enforce their stops.
- The bot only trades while the US market is open. It idles overnight and at
  weekends, and the dashboard shows the countdown to the next open.
- Long only, one position per symbol. US-listed shares only.
