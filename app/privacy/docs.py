"""The privacy policy, written from the code (10.1).

PRIVACY.md, PRIVACY.tr.md and the in-app page /privacy.html are made here, from
the same lists the app uses (app/privacy/hosts.py: every server; data.py: every
file). tests/test_privacy_docs.py regenerates them and fails when a file is out
of date, so the policy cannot say something the code does not do. Edit the
words here, then run:  python scripts/gen_privacy.py
"""
from __future__ import annotations

import html as _html
import re
from pathlib import Path

from app.privacy.data import ITEMS
from app.privacy.hosts import HOSTS

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "app" / "web" / "static" / "guide.html"

WHEN = {
    "en": {"always": "Read as the app runs", "keys": "Only after you enter that service's key", "update": "Only when you ask",
           "link": "A link you may click; the app does not connect", "local": "This PC only",
           "library": "Used by a bundled part when you use that service"},
    "tr": {"always": "Uygulama çalışırken okunur", "keys": "Sadece o servisin anahtarını girince", "update": "Sadece sen istersen",
           "link": "Tıklayabileceğin bağlantı; uygulama bağlanmaz", "local": "Sadece bu PC",
           "library": "O servisi kullanınca gömülü bir parça kullanır"},
}

TEXT = {
    "en": {
        "title": "Privacy",
        "lead": "Money Tree is a program on your PC. There is no account and no server of ours. This page says what is kept, what leaves the PC and who gets it. It is written from the code, and a test fails when the two disagree.",
        "short": "The short version",
        "short_items": [
            "**Nothing is sent to us.** BofStudios has no server, no account system and no way to see your data.",
            "**No ads, no tracking, no analytics, no crash reports, no selling of data.**",
            "**Your keys** are stored encrypted for your Windows user (DPAPI). They are sent only to the service they belong to, and never to an AI.",
            "**Everything is in one folder** on your PC. In Settings > Privacy and data you can open it, export it, and clear what the bot keeps about you.",
            "**The app talks to a short, public list of servers** (below). A test fails if the code names a server that is not on the list.",
            "**The code is open.** Read it, or ask someone to read it, on GitHub.",
        ],
        "stored": "What is kept on your PC",
        "stored_note": "The folder is `%LOCALAPPDATA%\\BofStudios\\Money Tree AI`. Files marked secret are never put in an export.",
        "stored_cols": ("File", "What it is", "Secret"),
        "yes": "yes", "no": "",
        "hosts": "Who the app talks to",
        "hosts_note": "This is the whole list. When a service appears twice, it has more than one address.",
        "hosts_cols": ("Who", "Address", "What goes there", "When", "Their privacy page"),
        "policy_link": "privacy page",
        "ai": "What goes to an AI",
        "ai_items": [
            "Only if you connect one: Groq, Google Gemini or Claude with a key you entered, or Ollama, which runs on your PC and sends nothing out.",
            "What is sent: the question you type; a short note about the bot (symbols, prices, positions; amounts depend on the level you choose below); headlines the bot read; facts you asked it to remember; screenshots you add to a question.",
            "What is never sent: your keys, the dashboard password, your account numbers, your name or e-mail (the app does not hold them).",
            "Screenshots go to Groq. They go to Google Gemini only if you allow it in Settings, because on Google's free tier Google may use what it gets to improve its products and people may read it.",
            "Groq says it does not keep inference data by default, but it may log it for up to 30 days. Read each company's page for what it does with data; the links are in the table above.",
            "Settings > Privacy and data shows exactly what the AI was last sent.",
        ],
        "choices": "Your choices",
        "choices_items": [
            "**What the AI sees:** everything, only percentages and symbols, or nothing about your account.",
            "**Remember the chat:** off means the conversation is not saved on your PC and earlier messages are not sent.",
            "**Phone access:** off by default for a new install. Off means only this PC can open the dashboard.",
            "**Screenshots to Gemini:** off by default.",
            "**Log files:** how long they are kept (1 to 90 days). They have keys removed.",
            "**Export:** a zip of your data without keys and without the password.",
            "**Clear:** the chat and memory, what the bot learned, Lab results, logs, or all four. Your trades and keys are not cleared there: remove keys under Money and keys, or close the app and delete the folder.",
        ],
        "security": "How the dashboard is protected",
        "security_items": [
            "It needs a password. The first visit with the link logs the browser in with an HttpOnly cookie and removes the password from the address bar.",
            "It listens only on this PC, unless you turn on phone access.",
            "Five wrong tries lock that address for a minute, then longer.",
            "A change must come from the page's own address, so another web page cannot press buttons here.",
            "Real money is never armed by the app itself. Stop is checked right before every order.",
        ],
        "kids": "Children",
        "kids_text": "Trading real money needs a brokerage account in an adult's name; that is the broker's rule, not ours. The app asks for no age, name or identity.",
        "money": "Not financial advice",
        "money_text": "Money Tree is software. Nothing in it is a recommendation to buy or sell. Read the terms in the guide and in TERMS.txt.",
        "changes": "Changes and questions",
        "changes_text": "This page changes only with the code, so every change is in the public history on GitHub. Questions: open an issue there. A security problem: use the private report described in SECURITY.md.",
    },
    "tr": {
        "title": "Gizlilik",
        "lead": "Money Tree senin bilgisayarında çalışan bir programdır. Hesap yok, bizim sunucumuz yok. Bu sayfa neyin saklandığını, neyin PC'den çıktığını ve kime gittiğini söyler. Koddan üretilir; ikisi uyuşmazsa bir test kırılır.",
        "short": "Kısaca",
        "short_items": [
            "**Bize hiçbir şey gönderilmez.** BofStudios'un sunucusu, hesap sistemi ve verini görme yolu yok.",
            "**Reklam yok, izleme yok, analitik yok, çökme raporu yok, veri satışı yok.**",
            "**Anahtarların** Windows kullanıcın için şifreli saklanır (DPAPI). Sadece ait oldukları servise gider, yapay zekâya asla.",
            "**Her şey tek klasörde**, PC'nde. Ayarlar > Gizlilik ve veri'den açabilir, dışa aktarabilir ve botun senin hakkında tuttuklarını silebilirsin.",
            "**Uygulama kısa ve açık bir sunucu listesiyle konuşur** (aşağıda). Kod listede olmayan bir sunucuyu anarsa test kırılır.",
            "**Kod açık.** GitHub'da oku ya da birine okut.",
        ],
        "stored": "PC'nde neler saklanır",
        "stored_note": "Klasör `%LOCALAPPDATA%\\BofStudios\\Money Tree AI`. Gizli işaretli dosyalar dışa aktarmaya asla girmez.",
        "stored_cols": ("Dosya", "Ne olduğu", "Gizli"),
        "yes": "evet", "no": "",
        "hosts": "Uygulama kimlerle konuşuyor",
        "hosts_note": "Listenin tamamı bu. Bir servis iki kez görünüyorsa birden fazla adresi var.",
        "hosts_cols": ("Kim", "Adres", "Oraya ne gider", "Ne zaman", "Gizlilik sayfaları"),
        "policy_link": "gizlilik sayfası",
        "ai": "Yapay zekâya ne gider",
        "ai_items": [
            "Sadece sen bağlarsan: girdiğin anahtarla Groq, Google Gemini ya da Claude; ya da PC'nde çalışan ve dışarı hiçbir şey göndermeyen Ollama.",
            "Gidenler: yazdığın soru; bot hakkında kısa bir not (hisse adları, fiyatlar, pozisyonlar; tutarlar aşağıda seçtiğin düzeye göre); botun okuduğu haber başlıkları; hatırlamasını istediğin bilgiler; soruna eklediğin ekran görüntüleri.",
            "Asla gitmeyenler: anahtarların, panel şifresi, hesap numaraların, adın ya da e-postan (uygulama bunları tutmaz).",
            "Ekran görüntüleri Groq'a gider. Google Gemini'ye sadece Ayarlar'dan izin verirsen gider; çünkü Google'ın ücretsiz katmanında Google gelenleri ürünlerini geliştirmek için kullanabilir ve insanlar okuyabilir.",
            "Groq varsayılan olarak çıkarım verisini saklamadığını söylüyor ama en çok 30 gün kayıt tutabilir. Her şirketin veriyle ne yaptığı için kendi sayfasını oku; bağlantılar yukarıdaki tabloda.",
            "Ayarlar > Gizlilik ve veri, yapay zekâya en son ne gönderildiğini aynen gösterir.",
        ],
        "choices": "Seçimlerin",
        "choices_items": [
            "**Yapay zekâ ne görüyor:** her şey, sadece yüzdeler ve hisse adları ya da hesabın hakkında hiçbir şey.",
            "**Sohbeti hatırla:** kapalıysa sohbet PC'ne kaydedilmez ve eski mesajlar gönderilmez.",
            "**Telefondan erişim:** yeni kurulumda varsayılan kapalı. Kapalıysa paneli sadece bu PC açabilir.",
            "**Ekran görüntüsü Gemini'ye:** varsayılan kapalı.",
            "**Kayıt dosyaları:** ne kadar tutulacağı (1 ile 90 gün). Anahtarlar temizlenmiştir.",
            "**Dışa aktar:** anahtarsız ve şifresiz bir zip.",
            "**Temizle:** sohbet ve hafıza, botun öğrendikleri, Lab sonuçları, kayıtlar ya da dördü birden. İşlemlerin ve anahtarların orada silinmez: anahtarları Para ve anahtarlar'dan sil ya da uygulamayı kapatıp klasörü sil.",
        ],
        "security": "Panel nasıl korunur",
        "security_items": [
            "Şifre ister. Bağlantıyla ilk ziyaret tarayıcıyı HttpOnly bir çerezle içeri alır ve şifreyi adres çubuğundan siler.",
            "Sadece bu PC'de dinler; telefondan erişimi sen açmadıkça.",
            "Beş yanlış deneme o adresi bir dakika, sonra daha uzun süre kilitler.",
            "Bir değişiklik sayfanın kendi adresinden gelmeli; başka bir web sayfası buradaki düğmelere basamaz.",
            "Gerçek parayı uygulamanın kendisi asla kurmaz. Durdur, her emirden hemen önce kontrol edilir.",
        ],
        "kids": "Çocuklar",
        "kids_text": "Gerçek para ile işlem için yetişkin adına bir aracı kurum hesabı gerekir; bu bizim değil, aracı kurumun kuralı. Uygulama yaş, ad ya da kimlik sormaz.",
        "money": "Finansal tavsiye değildir",
        "money_text": "Money Tree bir yazılımdır. İçindeki hiçbir şey al ya da sat önerisi değildir. Şartları kılavuzda ve TERMS.txt içinde oku.",
        "changes": "Değişiklikler ve sorular",
        "changes_text": "Bu sayfa sadece kodla birlikte değişir; yani her değişiklik GitHub'daki herkese açık geçmişte durur. Sorular için orada bir issue aç. Güvenlik sorunu için SECURITY.md'deki özel bildirimi kullan.",
    },
}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def markdown(lang: str) -> str:
    x = TEXT[lang]
    out = [f"# {x['title']}", "", x["lead"], "", f"## {x['short']}", ""]
    out += [f"- {i}" for i in x["short_items"]]
    out += ["", f"## {x['stored']}", "", x["stored_note"], "", "| " + " | ".join(x["stored_cols"]) + " |", "|---|---|---|"]
    for it in ITEMS:
        out.append(f"| `{it.path}` | {_cell(it.en if lang == 'en' else it.tr)} | {x['yes'] if it.secret else x['no']} |")
    out += ["", f"## {x['hosts']}", "", x["hosts_note"], "", "| " + " | ".join(x["hosts_cols"]) + " |", "|---|---|---|---|---|"]
    for h in sorted(HOSTS, key=lambda h: (list(WHEN['en']).index(h.when), h.who, h.host)):
        link = f"[{x['policy_link']}]({h.policy})" if h.policy else ""
        out.append(f"| {_cell(h.who)} | `{h.host}` | {_cell(h.what if lang == 'en' else h.wat)} | {WHEN[lang][h.when]} | {link} |")
    for key, items in (("ai", "ai_items"), ("choices", "choices_items"), ("security", "security_items")):
        out += ["", f"## {x[key]}", ""] + [f"- {i}" for i in x[items]]
    for key in ("kids", "money", "changes"):
        out += ["", f"## {x[key]}", "", x[f"{key}_text"]]
    return "\n".join(out) + "\n"


def _inline(text: str) -> str:
    """The little markdown used above: **bold**, `code`, [text](url)."""
    t = _html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return re.sub(r"\[(.+?)\]\((https://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', t)


def _section(lang: str) -> str:
    x = TEXT[lang]
    h = ['<div data-lang="%s">' % lang, f"  <h1>Money Tree <em>{_html.escape(x['title'])}</em></h1>", f'  <p class="lead">{_inline(x["lead"])}</p>']
    h += [f"  <h2>{x['short']}</h2>", "  <ul>"] + [f"    <li>{_inline(i)}</li>" for i in x["short_items"]] + ["  </ul>"]
    h += [f"  <h2>{x['stored']}</h2>", f"  <p>{_inline(x['stored_note'])}</p>", "  <table>",
          "    <tr>" + "".join(f"<th>{c}</th>" for c in x["stored_cols"]) + "</tr>"]
    for it in ITEMS:
        h.append(f"    <tr><td><code>{_html.escape(it.path)}</code></td><td>{_html.escape(it.en if lang == 'en' else it.tr)}</td>"
                 f"<td>{x['yes'] if it.secret else x['no']}</td></tr>")
    h += ["  </table>", f"  <h2>{x['hosts']}</h2>", f"  <p>{_inline(x['hosts_note'])}</p>", "  <table>",
          "    <tr>" + "".join(f"<th>{c}</th>" for c in x["hosts_cols"]) + "</tr>"]
    for host in sorted(HOSTS, key=lambda h: (list(WHEN['en']).index(h.when), h.who, h.host)):
        link = _inline(f"[{x['policy_link']}]({host.policy})") if host.policy else ""
        h.append(f"    <tr><td>{_html.escape(host.who)}</td><td><code>{_html.escape(host.host)}</code></td>"
                 f"<td>{_html.escape(host.what if lang == 'en' else host.wat)}</td><td>{WHEN[lang][host.when]}</td><td>{link}</td></tr>")
    h.append("  </table>")
    for key, items in (("ai", "ai_items"), ("choices", "choices_items"), ("security", "security_items")):
        h += [f"  <h2>{x[key]}</h2>", "  <ul>"] + [f"    <li>{_inline(i)}</li>" for i in x[items]] + ["  </ul>"]
    for key in ("kids", "money", "changes"):
        h += [f"  <h2>{x[key]}</h2>", f"  <p>{_inline(x[key + '_text'])}</p>"]
    h.append("</div>")
    return "\n".join(h)


def page() -> str:
    """privacy.html: the guide's look and language switch, the policy's words."""
    guide = GUIDE.read_text(encoding="utf-8")
    style = re.search(r"<style>.*?</style>", guide, re.S).group(0)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Money Tree Privacy</title>
<meta name="description" content="What Money Tree keeps on your PC, what leaves it, and who gets it.">
{style}
</head>
<body class="en">
<header class="top">
  <img src="/logo.png" alt="">
  <b>Money Tree</b>
  <span class="sp"></span>
  <div class="lang"><button data-set="en" class="on">English</button> <button data-set="tr">Türkçe</button></div>
</header>
<main>
<!-- Made by scripts/gen_privacy.py from app/privacy/docs.py. Do not edit by hand. -->
{_section("en")}

{_section("tr")}
</main>
<script src="/guide.js"></script>
</body>
</html>
"""


def outputs() -> dict[Path, str]:
    return {ROOT / "PRIVACY.md": markdown("en"), ROOT / "PRIVACY.tr.md": markdown("tr"),
            ROOT / "app" / "web" / "static" / "privacy.html": page()}
