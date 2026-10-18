# Money Tree AI: the full tutorial

Türkçe: [TUTORIAL.tr.md](TUTORIAL.tr.md)

> [!WARNING]
> Research software, not financial advice. No promise of profit. Trading can lose money, also more than you
> expect. Start with practice money. You are responsible for every trade on your account.

**Contents**
1. [What it is and how it decides](#1-what-it-is-and-how-it-decides)
2. [Install](#2-install)
3. [First start](#3-first-start)
4. [Alpaca, step by step](#4-alpaca-step-by-step)
5. [Connect a free AI](#5-connect-a-free-ai)
6. [Practice money, then real money](#6-practice-money-then-real-money)
7. [Arm, Stop and Start](#7-arm-stop-and-start)
8. [The Modes tab, explained](#8-the-modes-tab-explained)
9. [Every screen](#9-every-screen)
10. [News trading in detail](#10-news-trading-in-detail)
11. [How it gets better](#11-how-it-gets-better)
12. [Memory and your data](#12-memory-and-your-data)
13. [Safety limits](#13-safety-limits)
14. [Phone and Telegram](#14-phone-and-telegram)
15. [A good first week](#15-a-good-first-week)
16. [Problems and fixes](#16-problems-and-fixes)
17. [Build from source](#17-build-from-source)

---

## 1. What it is and how it decides

Money Tree AI is a Windows desktop app. It looks at a list of US stocks, reads the news, checks the companies,
and places orders through **your own Alpaca account**. Every step is shown in the **Live** tab with its reason.

A buy must pass these gates, in order:

| Gate | Question | Who can say no |
|---|---|---|
| Stop | Did you press STOP? | You, always, first |
| Market clock | Is the US market open? | The calendar |
| Signal | Does the strategy want to buy? | The strategy (the swarm's champion) |
| Research | Five checks on the company, the daily trend, the news, past results | The research desk |
| AI check | Is there a red flag in the news (a halt, fraud, results due)? | The AI |
| Risk rules | Is the size small enough? Is there cash? Is a slot free? | The risk manager |
| Arming | (Real money only) Did you arm it? | You |
| Autonomy | Full auto, or does it wait for your OK? | You |

A falling daily chart does not block a buy (except in Careful style); it halves the size. The stop-loss, the daily
loss limit and arming never change with a mode.

## 2. Install

1. Download `MoneyTreeAI-Desktop-<version>-win64.zip` from the
   [latest release](https://github.com/BofStudios/money-tree-ai/releases/latest) and unpack it anywhere
   (for example `Downloads\Money Tree`).
2. Run `Money Tree AI.exe`. Windows SmartScreen may say "Windows protected your PC" because the app is not signed:
   click **More info**, then **Run anyway**.
3. The logo shows at once. The window opens in 5 to 15 seconds.
4. Only one copy runs. Clicking the icon again brings the open window to the front.
5. Closing the window hides it to the tray. **Right-click the tray icon, Quit** to stop the bot.

Windows 10 or 11, 64-bit, about 1 GB free disk and 8 GB memory.

## 3. First start

The app asks a few questions. Tick the risk box first: it says this is software, not advice.

1. **Market:** US, Europe (through US listings) or both.
2. **How long to hold:** days (15-minute charts), weeks (1-hour) or months (daily).
3. **Who decides:** full auto, ask me first, or ideas only.
4. **Small account:** on lets it buy fractions of a share (needs a broker that allows it, Alpaca does).

Then it asks how much CPU the bots may use. Choose **Full** or **Light**; you can change it later in Modes.
Every answer can be changed later.

## 4. Alpaca, step by step

[Alpaca](https://alpaca.markets) is the US broker the bot trades through. It has a free **paper** (practice)
account and a live account. Menu names on their site can change; look for the same words.

### 4.1 Make the account
1. Go to alpaca.markets and sign up with your e-mail.
2. Verify the e-mail. You land in the dashboard. A **paper trading** account exists at once; it has fake money and
   needs no identity checks.
3. For **real money** you must also finish Alpaca's identity (KYC) form and fund the account. Whether your country
   is accepted, the age rule and the funding options are Alpaca's, so read their pages first. The account holder is
   responsible for the account.

### 4.2 Get API keys for practice money
1. In the dashboard, switch to **Paper Trading** (top left).
2. Find **API Keys** (right side or under the account menu) and press **Generate New Key**.
3. Copy the **Key** and the **Secret** now. The secret is shown **once**. If you lose it, generate a new pair.
4. Paper keys start with `PK`.

### 4.3 Put the keys in the app
1. In Money Tree: **Settings → Money & keys**.
2. Paste the key and the secret in the **paper** boxes and press **Save**. The app checks them with Alpaca first;
   if they are refused you get the reason.
3. The keys are stored encrypted for your Windows user. The page only shows the last four characters.
4. The app restarts on your Alpaca paper account. The Home card says **Alpaca paper**.

### 4.4 Real money (only when you are ready)
1. In the Alpaca dashboard switch to **Live Trading** and generate live keys (they start with `AK`).
2. Paste them in the **live** boxes in Settings → Money & keys.
3. Open **Modes → Money → Real money** (or the Home card **Switch to real money**). Type the confirmation words
   that the app asks for. The app restarts on the live account.
4. The Home card says **REAL MONEY**. The bot only **watches** until you arm it (section 7).

Money moves in and out of Alpaca only inside Alpaca's own site or app. Money Tree never asks for bank details and
never moves money.

## 5. Connect a free AI

The AI explains trades, answers in the chat and judges breaking news. Without it the bot still trades on its
rules, but news trading only acts on very clear news about a company.

1. Make a free key at [console.groq.com](https://console.groq.com) (or Google AI Studio for Gemini).
2. **Settings → AI → Use free Groq**, paste the key.
3. If one AI is busy or out of credit, the app uses another one you connected. Settings shows which, and why.

Only headlines and short facts go to the AI, never your keys.

## 6. Practice money, then real money

| Level | Money | Prices | When |
|---|---|---|---|
| Simulation | On this PC only | Free public | No keys at all |
| Alpaca paper | Alpaca's fake money | Alpaca | After paper keys |
| Real money | Yours | Alpaca | After live keys, typed confirmation and arming |

Run on practice money for at least two weeks. Look at the **scorecard** on Home: it compares the bot with simply
holding SPY. If the bot is behind, real money would be behind too.

## 7. Arm, Stop and Start

- **Arm real money** (Modes → Money, or the Home card). With real money the bot only watches until you arm it. It
  disarms itself at the daily loss limit, when you press Disarm and when the app closes. **After every start of
  the app, arm it again.** The Home card, the header pill, a Windows notice and a Telegram message with an Arm
  button remind you.
- **STOP** (red, top right). From that moment the bot buys nothing and sells nothing on a signal. The stop-loss and
  take-profit stay active. Stop is remembered after a restart. You can also type `stop` in the chat.
- **Start** lets it trade again. Type `start` in the chat.

The Home card **Is it trading?** lists every gate and which one is closed.

## 8. The Modes tab, explained

### Money
- **Practice**: real prices, practice money.
- **Real money**: your Alpaca live account. Shows armed or not armed. Arm and Disarm buttons.

### Speed
| Speed | What it does | Use when |
|---|---|---|
| Eco | Strategy bots run at 15% power. One look a minute. | The PC must stay quiet and cool |
| Normal | Bots at full power. One look a minute. **Auto eco** slows them to 25% while you use the PC. | Default |
| Ultra | A bot on every CPU core (up to 16), 13 more news sources (central banks, the SEC, the FDA, the Pentagon, big company newsrooms), news checks 3 times as often, a look every 15 seconds, 16 more large stocks, room for four news trades, 3 times the AI thinking. A red edge and an ULTRA badge. A warning with a tick comes first. | You leave the PC on and want maximum reaction speed |

Ultra does not mean more profit. It uses the whole computer and more of your free AI quota.

### Trading style
| Style | Company checks | News must be | Daily chart falling |
|---|---|---|---|
| Careful | Only BUY ZONE companies | 75% sure | Blocks the buy |
| Balanced (default) | Skips AVOID companies | 60% sure | Halves the order |
| Bold | Off | 55% sure | Halves the order |

### Who decides
- **Full auto**: buys and sells by itself inside the limits.
- **Ask me first**: each buy waits a few minutes for your Approve (Home, Telegram). Stop cancels waiting buys.
- **Ideas only**: only suggests, never buys.

### Smart features
News trading, Improve itself (the strategy bots), Find new stocks (up to three that the whole market talks about),
AI double-check, Learn from results, News check, Auto eco.

## 9. Every screen

| Screen | What it shows |
|---|---|
| Home | Your money, **Is it trading?**, the bot against SPY, what it holds, today's result, Start/Stop/Scan |
| Modes | Everything in section 8 |
| Live | Every step as it happens, with the reason, in plain words |
| Brain | **Reflex** (news decisions), **Picks** (five company checks), **News radar**, **Learning**, **Memory**, **Gates** |
| Swarm | The ten strategy bots, their results, and the strategy the account trades with. Reset puts the original back |
| Research | Look up any US stock: financials, filings, an AI summary, questions |
| Chart, Market, News, Catalysts, Activity | Prices, the market, headlines, dated events, history |
| Settings | Getting started, keys, AI, language, your data folder, the guide |

The **AI panel** on the left answers questions ("why no trades?"). Tell it "remember ..." and it keeps the note.

## 10. News trading in detail

1. **Read.** Every few seconds: central banks, the White House, the SEC, company newsrooms, press wires, and
   Alpaca's news wire. Only news from the last 15 minutes can trigger a trade.
2. **Ripple.** Who the news is about, and who else it moves (a chip launch also moves memory, power and cooling).
3. **Think.** The AI works through it in steps and rates each stock: up or down, how sure, for how many hours.
   Minor news (awards, rebrands, routine partnerships) is rated low.
4. **Confirm.** The price must agree within ten minutes: up a little, but not a move that is already over. Penny
   stocks (under $5) and thin stocks are skipped.
5. **Act.** The buy passes the same gates as every trade, with a time limit. Bad news about a stock it holds can
   sell it.

See every decision in **Brain → Reflex**.

## 11. How it gets better

- **Strategy bots** breed thousands of strategies and test them on months of real prices. A new one replaces the
  current one only if it wins on prices no bot trained on, by a margin, and holds up on a second unseen stretch.
  Each bot remembers its best finds between runs.
- **Learning from results**: every buy signal is followed to the end; setups that lose are made smaller or blocked.
- **News memory**: every news idea is checked against the real price a trading day later. Kinds of news that worked
  are trusted up to 30% more, kinds that did not up to 30% less. The AI sees this record.
- **Brain → Memory** shows the level, the counts and how it grew.

It needs time: weeks, not days.

## 12. Memory and your data

Everything lives in `%LOCALAPPDATA%\BofStudios\Money Tree AI`:

| Item | Where |
|---|---|
| Keys (encrypted) | `data\keys.dat` |
| Trades and equity | `data\trading.db` |
| What it learned | `data\brain\` |
| Settings | `config\config.yaml`, `.env` |
| Logs | `logs\` |

Updates reuse this folder. **Back up:** quit the app, copy the folder. **New PC:** copy it, then enter your keys
again (they are encrypted for one Windows user). **Start over:** Brain → Learning → Forget, or delete the folder
while the app is closed.

## 13. Safety limits

| Limit | Meaning |
|---|---|
| Risk per trade | Money lost if the stop-loss fills = a fixed small part of the account |
| Daily loss limit | At the limit real money disarms for the day. A restart does not reset it |
| Positions | A cap on open stocks and on the share of the account in one stock |
| Stop-loss and target | On every buy. Whole-share buys keep them at Alpaca, so they work with the PC off |
| Pauses | A cooldown after a trade, a pause after several stop-outs, a pause on a big drawdown |

Edit them in `config\config.yaml`. The personal build has no caps; choose small values yourself.

## 14. Phone and Telegram

- **Phone link:** tray icon menu → **Copy phone link**. Same Wi-Fi. The link holds a private password; do not share it.
- **Telegram:** make a bot with @BotFather, put the token in `.env` as `TELEGRAM_BOT_TOKEN` and your chat id as
  `TELEGRAM_CHAT_IDS`. You get fills, approvals and the arm reminder, and can use `/status`, `/stop`, `/start`.

## 15. A good first week

1. Day 1: install, practice money, connect the AI. Leave Eco or Normal on.
2. Days 1-7: read **Live** and **Brain → Reflex** daily. Ask the AI "why no trades?" if it is quiet.
3. After two weeks: open the scorecard. Ahead of SPY or not? Read the losing trades.
4. Only then think about real money, with an amount you can lose, then arm it by hand.

## 16. Problems and fixes

| Problem | Fix |
|---|---|
| It never buys | Open **Is it trading?** on Home. Usually: real money not armed, STOP on, "Ideas only", market closed, no cash |
| Alpaca refuses the keys | Paper keys start with `PK`, live with `AK`. Copy again, or generate a new pair |
| "Market is closed" | US stocks trade 9:30 to 16:00 New York time, Monday to Friday, except holidays |
| The AI is silent | Free keys have rate limits. Wait a minute or add a second provider |
| Grey or slow window | It reloads itself. After two crashes the next start draws without the GPU |
| Hot or loud PC | Modes → Speed → Eco |
| Logs | `%LOCALAPPDATA%\BofStudios\Money Tree AI\logs` (keys are removed) |

## 17. Build from source

```bash
pip install -r requirements.txt
python -m app.main                 # run
python -m pytest -q tests          # tests
python scripts/build_exe.py --personal   # exe in dist/
```

From source the data folder is the repository itself. Set `MONEYTREE_HOME` to use another folder.
