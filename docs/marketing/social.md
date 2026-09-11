# Money Tree AI — Social copy

All copy below is fact-checked against the current README and source. No
figures appear here that aren't in the README's backtest table. Do not add
numbers, testimonials, or screenshots that aren't in this file or the repo.

## Instagram (bof_labs) — carousel captions

**Post caption (use with the 8-slide carousel in `scratchpad/mtcarousel/`):**

> Borsa uygulaman sana yüz tane sayı gösterir, hiçbirini açıklamaz.
>
> Money Tree AI aynı sayıları gösterir ama yanına ne anlama geldiğini yazar —
> Basit / Gelişmiş iki seviye, aynı gerçek veri. Bir alan yoksa "yok" der,
> sıfır ya da tahmin uydurmaz.
>
> Kendi mekanik EMA/RSI stratejini sahte parayla test edebilirsin. Dürüst
> olalım: bir yıllık backtestte strateji kâr sınırında — asıl değer risk
> yönetiminde (en kötü düşüşü %11.7'den %5.4'e indirdi). Kâr vaadi yok,
> yatırım tavsiyesi değil.
>
> Açık kaynak, Windows'ta senin makinende çalışır. Link bio'da.
>
> #python #opensource #trading #algotrading #fintech #indiehacker

## X / Twitter thread

1/ Money Tree AI: bir borsa araştırma + backtest aracı. Açık kaynak, yerel
çalışır, kâr vaat etmiyor.

2/ Sorun: borsa uygulamaları sana 100 sayı gösterir, hiçbirini açıklamaz. Ya
kör uçarsın ya birinin sinyaline güvenirsin.

3/ Money Tree AI'da her rakamın yanında ne anlama geldiği yazar — Basit /
Gelişmiş toggle, altındaki veri aynı. Veri yoksa "yok" der, tahmin üretmez
(kaynak: app/research/models.py, Provenance).

4/ Kendi mekanik stratejini gerçek fiyatlarla, sahte parayla test et. Risk
motoru Freqtrade'den uyarlandı.

5/ Dürüstlük: bir yıllık backtestte (588 trade, saatlik, 8 sembol) strateji
kâr sınırında — profit factor hiç 1.0'ı geçmiyor. Risk kuralları en kötü
düşüşü %11.7'den %5.4'e indirdi ama stratejiyi kârlı yapmadı. Tam tablo
README'de.

6/ Açık kaynak (MIT), Windows'ta senin makinende, Ollama ile ücretsiz ve
yerel AI. github.com/BofStudios/money-tree-ai

## Reddit (r/algotrading, r/Python, r/opensource — post as a genuine share, not an ad)

**Title:** Built an open-source US stock research + backtest tool that refuses
to fake missing data (Python/PySide6)

**Body:**

Been working on this for a while — a desktop app that pulls company research
(financials, valuation, analyst targets, insider trades) from a free data
provider and explains it at whatever finance-literacy level you're at, plus a
mechanical EMA/RSI strategy you can backtest and paper-trade before risking
anything real.

The thing I actually care about: if a data field isn't available, it shows
"not available" — never a zero, never an estimate standing in for missing
data. That's enforced in the data model, not just a UI convention.

Being upfront about the strategy itself: a year of hourly backtests across 8
symbols lands within a rounding error of break-even. The risk management
(sizing, ATR stops, trailing stop, drawdown/cooldown locks — adapted from
Freqtrade) cut the worst drawdown from 11.7% to 5.4% and improved win rate, but
it did **not** make the EMA/RSI entry profitable. Full table's in the README.
This is a research/education tool, not a way to print money — if you want that
part solved, `scripts/run_backtest.py` is right there.

Open source, MIT, Windows, runs locally: github.com/BofStudios/money-tree-ai

Happy to answer questions about the architecture or the backtest methodology.

## Notes for whoever posts this

- Never claim a feature not in this file or the README. If unsure, check
  `app/` before publishing.
- Every backtest number must match the README's "Did any of it help?" table
  exactly — no rounding in a more flattering direction.
- No fabricated screenshots of returns, no fake comment/like counts, no
  "I made $X" framing anywhere.
