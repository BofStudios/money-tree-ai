"""Every server Money Tree talks to, in one list (10.1).

This list is the truth the privacy page, the Settings screen and the guide are
written from, and tests/test_privacy.py reads every address in the app's
sources and fails when one is not here: a new connection cannot be added
without being declared. There is no server of ours in it.

when
  always   read without a key, as the app runs (public data)
  keys     only after the owner entered that service's key
  update   only when the owner asks for it, or turns the check on
  link     a link the owner may click; the app does not connect
  local    this PC only
  library  inside a bundled library, not in the app's own source
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Host:
    host: str
    who: str
    what: str          # what goes there (English)
    wat: str           # the same in Turkish
    when: str
    policy: str = ""   # that company's own privacy page ("" = the site's own)
    platform: str = "both"       # desktop | android | both

    def to_dict(self) -> dict:
        return asdict(self)


_NEWS = ("Public news and announcements are read. Nothing about you is sent, only the request itself.",
         "Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek.")

HOSTS: tuple[Host, ...] = (
    # ---- your broker
    Host("api.alpaca.markets", "Alpaca", "Your orders, positions and account; prices and news. Your Alpaca keys sign each request.",
         "Emirlerin, pozisyonların ve hesabın; fiyatlar ve haberler. Alpaca anahtarların her isteği imzalar.",
         "keys", "https://alpaca.markets/disclosures"),
    Host("paper-api.alpaca.markets", "Alpaca", "The same, for the practice (paper) account.",
         "Aynısı, deneme (paper) hesabı için.", "keys", "https://alpaca.markets/disclosures"),
    Host("data.alpaca.markets", "Alpaca", "Prices, one-minute candles and news.", "Fiyatlar, 1 dakikalık mumlar ve haberler.",
         "keys", "https://alpaca.markets/disclosures"),
    Host("alpaca.markets", "Alpaca", "A link to Alpaca's pages.", "Alpaca sayfalarına bağlantı.", "link",
         "https://alpaca.markets/disclosures"),
    Host("app.alpaca.markets", "Alpaca", "A link to open an account or create keys.", "Hesap açmak ya da anahtar üretmek için bağlantı.",
         "link", "https://alpaca.markets/disclosures"),
    # ---- the AI you connect
    Host("api.groq.com", "Groq", "Your question, a short bot state (symbols, prices, positions, depending on the AI privacy level), "
         "and screenshots you add. Never your keys. Groq says it does not keep inference data by default, but may log it for up to 30 days.",
         "Sorun, kısa bir bot durumu (gizlilik düzeyine göre hisse, fiyat, pozisyon) ve eklediğin ekran görüntüleri. Anahtarların asla. "
         "Groq varsayılan olarak veriyi saklamadığını söylüyor ama en çok 30 gün kayıt tutabilir.",
         "keys", "https://groq.com/privacy-policy"),
    Host("console.groq.com", "Groq", "A link to create a free key.", "Ücretsiz anahtar üretmek için bağlantı.", "link",
         "https://groq.com/privacy-policy"),
    Host("generativelanguage.googleapis.com", "Google (Gemini)", "The same as Groq. On Google's free tier, Google may use what you send to improve its products "
         "and people may read it. Screenshots go there only if you allow it in Settings.",
         "Groq ile aynı. Google'ın ücretsiz katmanında Google gönderdiklerini ürünlerini geliştirmek için kullanabilir ve insanlar okuyabilir. "
         "Ekran görüntüsü buraya sadece Ayarlar'dan izin verirsen gider.",
         "keys", "https://aistudio.google.com/docs/terms", "desktop"),
    Host("api.anthropic.com", "Anthropic (Claude)", "The same as Groq, only if you entered a Claude key.", "Groq ile aynı, sadece Claude anahtarı girdiysen.",
         "library", "https://www.anthropic.com/legal/privacy", "desktop"),
    Host("api.telegram.org", "Telegram", "Alerts you asked for, to your own chat, only if you entered a bot token.",
         "İstediğin uyarılar, kendi sohbetine, sadece bot anahtarı girdiysen.", "library", "https://telegram.org/privacy", "desktop"),
    # ---- prices without a key
    Host("query1.finance.yahoo.com", "Yahoo Finance", "Prices and candles when no Alpaca key is set or Alpaca is resting, and the one-minute bars of the Lab's replay (symbols only).",
         "Alpaca anahtarı yokken ya da Alpaca dinlenirken fiyat ve mumlar, ve Lab tekrarının 1 dakikalık mumları (sadece hisse adları).", "library",
         "https://legal.yahoo.com/us/en/yahoo/privacy/index.html", "desktop"),
    Host("api.frankfurter.dev", "Frankfurter", "Public exchange rates.", "Herkese açık döviz kurları.", "always", "", "both"),
    # ---- public filings and attention
    Host("data.sec.gov", "US SEC (EDGAR)", "Public company filings.", "Şirketlerin herkese açık bildirimleri.", "always",
         "https://www.sec.gov/privacy"),
    Host("efts.sec.gov", "US SEC (EDGAR)", "Search of public filings.", "Herkese açık bildirimlerde arama.", "always",
         "https://www.sec.gov/privacy"),
    Host("www.sec.gov", "US SEC", "Public press releases.", "Herkese açık basın bildirileri.", "always",
         "https://www.sec.gov/privacy", "desktop"),
    Host("en.wikipedia.org", "Wikimedia", "A company's page name, for the page-views signal.",
         "Sayfa görüntülenme sinyali için şirketin sayfa adı.", "always",
         "https://foundation.wikimedia.org/wiki/Policy:Privacy_policy"),
    Host("wikimedia.org", "Wikimedia", "Public page-view counts.", "Herkese açık sayfa görüntülenme sayıları.", "always",
         "https://foundation.wikimedia.org/wiki/Policy:Privacy_policy"),
    Host("github.com", "GitHub", "A link to the app's source code.", "Uygulamanın kaynak koduna bağlantı.", "link",
         "https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement"),
    # ---- the owner's update check (Android)
    Host("api.github.com", "GitHub", "Asks for the newest release number of this app. Sends nothing about you.",
         "Uygulamanın en yeni sürüm numarasını sorar. Senin hakkında bir şey göndermez.", "update",
         "https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement", "android"),
    # ---- official feeds the news reflex reads (desktop)
    *(Host(h, who, *_NEWS, "always", "", "desktop") for h, who in (
        ("www.federalreserve.gov", "US Federal Reserve"), ("www.whitehouse.gov", "The White House"),
        ("ustr.gov", "US Trade Representative"), ("www.fda.gov", "US FDA"), ("www.energy.gov", "US Dept. of Energy"),
        ("www.eia.gov", "US EIA"), ("www.defense.gov", "US Dept. of Defense"), ("www.ecb.europa.eu", "European Central Bank"),
        ("www.bankofengland.co.uk", "Bank of England"), ("www.boj.or.jp", "Bank of Japan"),
        ("www.prnewswire.com", "PR Newswire"), ("www.globenewswire.com", "GlobeNewswire"),
        ("feed.businesswire.com", "Business Wire"), ("www.apple.com", "Apple newsroom"),
        ("news.microsoft.com", "Microsoft newsroom"), ("nvidianews.nvidia.com", "NVIDIA newsroom"),
        ("blog.google", "Google blog"), ("openai.com", "OpenAI news"),
    )),
    # ---- this PC
    Host("127.0.0.1", "This PC", "The app's own window and an AI you run yourself (Ollama). Never leaves the PC.",
         "Uygulamanın kendi penceresi ve kendin çalıştırdığın yapay zekâ (Ollama). PC'nden çıkmaz.", "local", "", "desktop"),
)

# Named in the sources but not a server the app contacts: XML namespaces, licence
# comments inside a bundled script. Listed so the test can tell them from a real connection.
NOT_CONNECTIONS = frozenset({
    "schemas.android.com", "www.w3.org", "www.apache.org", "www.tradingview.com",
})


def known() -> set[str]:
    return {h.host for h in HOSTS} | set(NOT_CONNECTIONS)


def as_dicts(platform: str = "desktop") -> list[dict]:
    return [h.to_dict() for h in HOSTS if h.platform in ("both", platform)]
