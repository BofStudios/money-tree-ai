# Privacy

Money Tree is a program on your PC. There is no account and no server of ours. This page says what is kept, what leaves the PC and who gets it. It is written from the code, and a test fails when the two disagree.

## The short version

- **Nothing is sent to us.** BofStudios has no server, no account system and no way to see your data.
- **No ads, no tracking, no analytics, no crash reports, no selling of data.**
- **Your keys** are stored encrypted for your Windows user (DPAPI). They are sent only to the service they belong to, and never to an AI.
- **Everything is in one folder** on your PC. In Settings > Privacy and data you can open it, export it, and clear what the bot keeps about you.
- **The app talks to a short, public list of servers** (below). A test fails if the code names a server that is not on the list.
- **The code is open.** Read it, or ask someone to read it, on GitHub.

## What is kept on your PC

The folder is `%LOCALAPPDATA%\BofStudios\Money Tree AI`. Files marked secret are never put in an export.

| File | What it is | Secret |
|---|---|---|
| `data/keys.dat` | Your Alpaca and AI keys, encrypted for this Windows user. | yes |
| `.env` | Keys you wrote by hand, if you did. | yes |
| `data/dashboard.token` | The password of the dashboard and the phone link. | yes |
| `data/trading.db` | Every trade, equity snapshot and saved candle (exported as a CSV). |  |
| `data/user_profile.json` | Your choices: language, who decides, watchlist. |  |
| `data/mentor_memory.json` | Your chat with the AI and the facts you asked it to remember. |  |
| `data/mentor_feed.json` | What the app said in the side chat. |  |
| `data/brain` | What the bot learned: news memory, strategy progress, the swarm. |  |
| `data/lab.json` | The last Lab replay and the edge switch. |  |
| `data/privacy.json` | These privacy choices. |  |
| `data/journal.json` | Counters: how long the app has run. |  |
| `data/engine_state.json` | Open positions and the stop flag, to survive a restart. |  |
| `data/risk_day.json` | Today's loss count for the daily limit. |  |
| `data/live_feed.json` | The last lines of the live feed. |  |
| `logs` | Log files, with keys removed. |  |

## Who the app talks to

This is the whole list. When a service appears twice, it has more than one address.

| Who | Address | What goes there | When | Their privacy page |
|---|---|---|---|---|
| Apple newsroom | `www.apple.com` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| Bank of England | `www.bankofengland.co.uk` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| Bank of Japan | `www.boj.or.jp` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| Business Wire | `feed.businesswire.com` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| European Central Bank | `www.ecb.europa.eu` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| Frankfurter | `api.frankfurter.dev` | Public exchange rates. | Read as the app runs |  |
| GlobeNewswire | `www.globenewswire.com` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| Google blog | `blog.google` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| Microsoft newsroom | `news.microsoft.com` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| NVIDIA newsroom | `nvidianews.nvidia.com` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| OpenAI news | `openai.com` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| PR Newswire | `www.prnewswire.com` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| The White House | `www.whitehouse.gov` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| US Dept. of Defense | `www.defense.gov` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| US Dept. of Energy | `www.energy.gov` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| US EIA | `www.eia.gov` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| US FDA | `www.fda.gov` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| US Federal Reserve | `www.federalreserve.gov` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| US SEC | `www.sec.gov` | Public press releases. | Read as the app runs | [privacy page](https://www.sec.gov/privacy) |
| US SEC (EDGAR) | `data.sec.gov` | Public company filings. | Read as the app runs | [privacy page](https://www.sec.gov/privacy) |
| US SEC (EDGAR) | `efts.sec.gov` | Search of public filings. | Read as the app runs | [privacy page](https://www.sec.gov/privacy) |
| US Trade Representative | `ustr.gov` | Public news and announcements are read. Nothing about you is sent, only the request itself. | Read as the app runs |  |
| Wikimedia | `en.wikipedia.org` | A company's page name, for the page-views signal. | Read as the app runs | [privacy page](https://foundation.wikimedia.org/wiki/Policy:Privacy_policy) |
| Wikimedia | `wikimedia.org` | Public page-view counts. | Read as the app runs | [privacy page](https://foundation.wikimedia.org/wiki/Policy:Privacy_policy) |
| Alpaca | `api.alpaca.markets` | Your orders, positions and account; prices and news. Your Alpaca keys sign each request. | Only after you enter that service's key | [privacy page](https://alpaca.markets/disclosures) |
| Alpaca | `data.alpaca.markets` | Prices, one-minute candles and news. | Only after you enter that service's key | [privacy page](https://alpaca.markets/disclosures) |
| Alpaca | `paper-api.alpaca.markets` | The same, for the practice (paper) account. | Only after you enter that service's key | [privacy page](https://alpaca.markets/disclosures) |
| Google (Gemini) | `generativelanguage.googleapis.com` | The same as Groq. On Google's free tier, Google may use what you send to improve its products and people may read it. Screenshots go there only if you allow it in Settings. | Only after you enter that service's key | [privacy page](https://aistudio.google.com/docs/terms) |
| Groq | `api.groq.com` | Your question, a short bot state (symbols, prices, positions, depending on the AI privacy level), and screenshots you add. Never your keys. Groq says it does not keep inference data by default, but may log it for up to 30 days. | Only after you enter that service's key | [privacy page](https://groq.com/privacy-policy) |
| GitHub | `api.github.com` | Asks for the newest release number of this app. Sends nothing about you. | Only when you ask | [privacy page](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) |
| Alpaca | `alpaca.markets` | A link to Alpaca's pages. | A link you may click; the app does not connect | [privacy page](https://alpaca.markets/disclosures) |
| Alpaca | `app.alpaca.markets` | A link to open an account or create keys. | A link you may click; the app does not connect | [privacy page](https://alpaca.markets/disclosures) |
| GitHub | `github.com` | A link to the app's source code. | A link you may click; the app does not connect | [privacy page](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) |
| Groq | `console.groq.com` | A link to create a free key. | A link you may click; the app does not connect | [privacy page](https://groq.com/privacy-policy) |
| This PC | `127.0.0.1` | The app's own window and an AI you run yourself (Ollama). Never leaves the PC. | This PC only |  |
| Anthropic (Claude) | `api.anthropic.com` | The same as Groq, only if you entered a Claude key. | Used by a bundled part when you use that service | [privacy page](https://www.anthropic.com/legal/privacy) |
| Telegram | `api.telegram.org` | Alerts you asked for, to your own chat, only if you entered a bot token. | Used by a bundled part when you use that service | [privacy page](https://telegram.org/privacy) |
| Yahoo Finance | `query1.finance.yahoo.com` | Prices and candles when no Alpaca key is set or Alpaca is resting, and the one-minute bars of the Lab's replay (symbols only). | Used by a bundled part when you use that service | [privacy page](https://legal.yahoo.com/us/en/yahoo/privacy/index.html) |

## What goes to an AI

- Only if you connect one: Groq, Google Gemini or Claude with a key you entered, or Ollama, which runs on your PC and sends nothing out.
- What is sent: the question you type; a short note about the bot (symbols, prices, positions; amounts depend on the level you choose below); headlines the bot read; facts you asked it to remember; screenshots you add to a question.
- What is never sent: your keys, the dashboard password, your account numbers, your name or e-mail (the app does not hold them).
- Screenshots go to Groq. They go to Google Gemini only if you allow it in Settings, because on Google's free tier Google may use what it gets to improve its products and people may read it.
- Groq says it does not keep inference data by default, but it may log it for up to 30 days. Read each company's page for what it does with data; the links are in the table above.
- Settings > Privacy and data shows exactly what the AI was last sent.

## Your choices

- **What the AI sees:** everything, only percentages and symbols, or nothing about your account.
- **Remember the chat:** off means the conversation is not saved on your PC and earlier messages are not sent.
- **Phone access:** off by default for a new install. Off means only this PC can open the dashboard.
- **Screenshots to Gemini:** off by default.
- **Log files:** how long they are kept (1 to 90 days). They have keys removed.
- **Export:** a zip of your data without keys and without the password.
- **Clear:** the chat and memory, what the bot learned, Lab results, logs, or all four. Your trades and keys are not cleared there: remove keys under Money and keys, or close the app and delete the folder.

## How the dashboard is protected

- It needs a password. The first visit with the link logs the browser in with an HttpOnly cookie and removes the password from the address bar.
- It listens only on this PC, unless you turn on phone access.
- Five wrong tries lock that address for a minute, then longer.
- A change must come from the page's own address, so another web page cannot press buttons here.
- Real money is never armed by the app itself. Stop is checked right before every order.

## Children

Trading real money needs a brokerage account in an adult's name; that is the broker's rule, not ours. The app asks for no age, name or identity.

## Not financial advice

Money Tree is software. Nothing in it is a recommendation to buy or sell. Read the terms in the guide and in TERMS.txt.

## Changes and questions

This page changes only with the code, so every change is in the public history on GitHub. Questions: open an issue there. A security problem: use the private report described in SECURITY.md.
