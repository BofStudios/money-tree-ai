"""Your data on this PC (10.1): what is kept, an export, and what can be cleared.

Everything the app stores is under one folder (app/common/home.py). The
inventory below says, file by file, what it is. Keys and the dashboard
password are marked secret and are never put in an export.

Clearing works through the running app (it holds these files open and
rewrites them), so the files are never deleted from underneath it. The trade
history and the keys are not cleared from here: remove the keys under
Settings > Money and keys, or close the app and delete the folder.
"""
from __future__ import annotations

import csv
import io
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Item:
    path: str          # relative to the data home
    group: str         # keys | trades | profile | chat | learned | lab | logs | state | choices
    en: str
    tr: str
    secret: bool = False
    export: bool = True


ITEMS: tuple[Item, ...] = (
    Item("data/keys.dat", "keys", "Your Alpaca and AI keys, encrypted for this Windows user.",
         "Alpaca ve yapay zekâ anahtarların, bu Windows kullanıcısı için şifreli.", secret=True, export=False),
    Item(".env", "keys", "Keys you wrote by hand, if you did.", "Elle yazdıysan anahtarların.", secret=True, export=False),
    Item("data/dashboard.token", "keys", "The password of the dashboard and the phone link.",
         "Panelin ve telefon bağlantısının şifresi.", secret=True, export=False),
    Item("data/trading.db", "trades", "Every trade, equity snapshot and saved candle (exported as a CSV).",
         "Tüm işlemler, hesap değeri kayıtları ve kaydedilen mumlar (CSV olarak verilir).", export=False),
    Item("data/user_profile.json", "profile", "Your choices: language, who decides, watchlist.",
         "Seçimlerin: dil, kararı kimin verdiği, izleme listesi."),
    Item("data/mentor_memory.json", "chat", "Your chat with the AI and the facts you asked it to remember.",
         "Yapay zekâyla sohbetin ve hatırlamasını istediğin bilgiler."),
    Item("data/mentor_feed.json", "chat", "What the app said in the side chat.", "Uygulamanın yan sohbette söyledikleri."),
    Item("data/brain", "learned", "What the bot learned: news memory, strategy progress, the swarm.",
         "Botun öğrendikleri: haber hafızası, strateji ilerlemesi, sürü."),
    Item("data/lab.json", "lab", "The last Lab replay and the edge switch.", "Son Lab tekrarı ve avantaj filtresi anahtarı."),
    Item("data/privacy.json", "choices", "These privacy choices.", "Bu gizlilik seçimleri."),
    Item("data/journal.json", "state", "Counters: how long the app has run.", "Sayaçlar: uygulamanın ne kadar çalıştığı."),
    Item("data/engine_state.json", "state", "Open positions and the stop flag, to survive a restart.",
         "Açık pozisyonlar ve durdurma bayrağı, yeniden başlatmaya dayanmak için."),
    Item("data/risk_day.json", "state", "Today's loss count for the daily limit.", "Günlük sınır için bugünkü zarar sayacı."),
    Item("data/live_feed.json", "state", "The last lines of the live feed.", "Canlı akışın son satırları."),
    Item("logs", "logs", "Log files, with keys removed.", "Kayıt dosyaları, anahtarlar temizlenmiş."),
)

CLEARABLE = ("chat", "learned", "lab", "logs")


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    if p.is_dir():
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return 0


def inventory(home: Path) -> list[dict]:
    rows = []
    for it in ITEMS:
        p = home / it.path
        rows.append({
            "path": it.path, "group": it.group, "en": it.en, "tr": it.tr, "secret": it.secret,
            "exists": p.exists(), "bytes": _size(p),
            "changed": p.stat().st_mtime if p.exists() else None,
            "in_export": it.export and not it.secret,
        })
    return rows


def trades_csv(trades: list[dict]) -> str:
    out = io.StringIO()
    cols = ["symbol", "side", "qty", "entry_price", "exit_price", "pnl", "pnl_pct",
            "opened_at", "closed_at", "entry_reason", "exit_reason"]
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for t in trades:
        w.writerow(t)
    return out.getvalue()


def export_zip(home: Path, trades: list[dict], dest_dir: Path | None = None) -> Path:
    """A zip of what is yours, in <home>/exports. Never keys, the password or .env."""
    dest_dir = dest_dir or (home / "exports")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"money-tree-data-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("trades.csv", trades_csv(trades))
        z.writestr("README.txt", "Your Money Tree data. No keys, no password. "
                                 "trades.csv is your trade history; the .json files are your choices, chat and what the bot learned.\n")
        for it in ITEMS:
            if it.secret or not it.export:
                continue
            p = home / it.path
            if p.is_file():
                z.write(p, it.path)
            elif p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file():
                        z.write(f, f.relative_to(home).as_posix())
    return out


def prune_logs(log_dir: Path, days: int, now: float | None = None) -> int:
    """Delete log files older than `days` (the one being written is never old)."""
    now = now or time.time()
    removed = 0
    if not log_dir.is_dir():
        return 0
    for f in log_dir.iterdir():
        if f.is_file() and now - f.stat().st_mtime > days * 86400:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass            # still open: left for next time
    return removed


def summary_json(items: list[dict]) -> str:
    return json.dumps(items, indent=2)
