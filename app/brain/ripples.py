"""The ripple map: which stocks a piece of news moves, and why.

First order is the company the news is about. Second order is who sells to it,
powers it, competes with it or depends on the same policy. Each link carries
its reason, in English and Turkish, so the screen can show the chain of
thought. The AI may confirm, drop or re-weigh these links; it may not invent
tickers outside this map and the headline's own companies.

Only large, liquid US listings: the bot must be able to get in and out fast.
Long only, so a negative link means "do not buy, and sell if held".
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    symbol: str
    effect: int          # +1 helps, -1 hurts
    why: str
    why_tr: str


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    name_tr: str
    any_of: tuple[str, ...]       # at least one must appear
    with_any: tuple[str, ...]     # and at least one of these (empty: not needed)
    links: tuple[Link, ...]

    def matches(self, text: str) -> bool:
        if not any(_has(text, w) for w in self.any_of):
            return False
        return not self.with_any or any(_has(text, w) for w in self.with_any)


def _has(text: str, phrase: str) -> bool:
    # whole words at the start, so "cut" does not match "executive" and "rate cut" matches "rate cuts"
    return re.search(r"(?<![a-z])" + re.escape(phrase), text) is not None


L = Link
THEMES: tuple[Theme, ...] = (
    Theme("AI_COMPUTE", "AI chips and compute", "Yapay zekâ çipleri ve hesaplama",
          ("nvidia", "blackwell", "rubin", "gpu", "ai chip", "ai accelerator", "ai supercomputer", "ai factory"),
          ("launch", "unveil", "announce", "introduc", "new ", "record", "partner", "order", "deliver",
           "ship", "demand", "expand", "deploy", "build"),
          (L("NVDA", +1, "NVIDIA makes the AI chips", "AI çiplerini NVIDIA yapar"),
           L("TSM", +1, "TSMC manufactures NVIDIA's chips", "NVIDIA'nın çiplerini TSMC üretir"),
           L("MU", +1, "Micron sells the HBM memory that AI chips use", "AI çiplerinin kullandığı HBM belleği Micron satar"),
           L("AVGO", +1, "Broadcom sells AI networking and custom chips", "Broadcom AI ağ ve özel çip satar"),
           L("ASML", +1, "ASML makes the machines that print advanced chips", "Gelişmiş çipleri basan makineleri ASML yapar"),
           L("ANET", +1, "Arista sells data-center networking", "Arista veri merkezi ağ ekipmanı satar"),
           L("VRT", +1, "Vertiv sells power and cooling for AI racks", "Vertiv AI rafları için güç ve soğutma satar"),
           L("CEG", +1, "AI data centers need much electricity; Constellation sells nuclear power",
             "AI veri merkezleri çok elektrik ister; Constellation nükleer elektrik satar"))),
    Theme("DC_POWER", "Power for data centers", "Veri merkezleri için enerji",
          ("data center", "data centre", "hyperscale"),
          ("power", "electricity", "energy", "nuclear", "gigawatt", "grid", "utility"),
          (L("CEG", +1, "Constellation sells nuclear power to data centers", "Constellation veri merkezlerine nükleer elektrik satar"),
           L("VST", +1, "Vistra sells power to data centers", "Vistra veri merkezlerine elektrik satar"),
           L("NRG", +1, "NRG sells power", "NRG elektrik satar"),
           L("GEV", +1, "GE Vernova makes turbines and grid equipment", "GE Vernova türbin ve şebeke ekipmanı yapar"),
           L("ETN", +1, "Eaton makes electrical equipment for data centers", "Eaton veri merkezleri için elektrik ekipmanı yapar"),
           L("VRT", +1, "Vertiv sells power and cooling equipment", "Vertiv güç ve soğutma ekipmanı satar"))),
    Theme("AI_DEALS", "Big AI deals and spending", "Büyük AI anlaşmaları ve harcamaları",
          ("openai", "anthropic", "stargate", "hyperscaler", "capex", "capital expenditure", "ai infrastructure"),
          ("deal", "partner", "invest", "billion", "expand", "agreement", "contract", "spend", "commit"),
          (L("MSFT", +1, "Microsoft hosts and resells big AI models", "Microsoft büyük AI modellerini barındırır ve satar"),
           L("ORCL", +1, "Oracle rents AI cloud capacity", "Oracle AI bulut kapasitesi kiralar"),
           L("AMZN", +1, "Amazon rents AI cloud capacity", "Amazon AI bulut kapasitesi kiralar"),
           L("GOOGL", +1, "Google rents AI cloud capacity and makes TPUs", "Google AI bulut kapasitesi kiralar, TPU yapar"),
           L("NVDA", +1, "AI spending buys NVIDIA chips", "AI harcaması NVIDIA çipi alır"),
           L("AVGO", +1, "AI spending buys Broadcom networking and custom chips", "AI harcaması Broadcom ağ ve özel çipi alır"))),
    Theme("CHIP_CURBS", "Chip export limits", "Çip ihracat kısıtları",
          ("export control", "export ban", "export restriction", "export curb", "entity list", "chip ban"),
          ("china", "chip", "semiconductor", "nvidia", "gpu"),
          (L("NVDA", -1, "NVIDIA loses China sales", "NVIDIA Çin satışlarını kaybeder"),
           L("AMD", -1, "AMD loses China sales", "AMD Çin satışlarını kaybeder"),
           L("AMAT", -1, "Applied Materials sells much equipment to China", "Applied Materials Çin'e çok ekipman satar"),
           L("LRCX", -1, "Lam Research sells much equipment to China", "Lam Research Çin'e çok ekipman satar"))),
    Theme("TARIFFS_UP", "New or higher tariffs", "Yeni ya da daha yüksek gümrük vergisi",
          ("tariff", "import tax", "import duties", "duties on"),
          ("impose", "raise", "increase", "new", "announce", "hike", "sign", "proclamation", "order", "%"),
          (L("AAPL", -1, "Apple builds most iPhones abroad", "Apple çoğu iPhone'u yurt dışında üretir"),
           L("NKE", -1, "Nike makes most products in Asia", "Nike ürünlerinin çoğunu Asya'da üretir"),
           L("GM", -1, "GM imports parts and cars", "GM parça ve araç ithal eder"),
           L("F", -1, "Ford imports parts", "Ford parça ithal eder"))),
    Theme("STEEL", "Steel and aluminum protection", "Çelik ve alüminyum koruması",
          ("steel", "aluminum", "aluminium"),
          ("tariff", "duties", "section 232", "import", "protect"),
          (L("NUE", +1, "Nucor makes steel in the US", "Nucor ABD'de çelik üretir"),
           L("STLD", +1, "Steel Dynamics makes steel in the US", "Steel Dynamics ABD'de çelik üretir"),
           L("AA", +1, "Alcoa makes aluminum", "Alcoa alüminyum üretir"))),
    Theme("TRADE_DEAL", "Trade deal or tariff relief", "Ticaret anlaşması ya da vergi indirimi",
          ("trade deal", "trade agreement", "tariff pause", "tariff relief", "lower tariffs", "reduce tariffs",
           "tariff cut", "tariff reduction", "framework agreement"),
          (),
          (L("AAPL", +1, "Lower tariffs cut Apple's costs", "Düşük vergi Apple'ın maliyetini düşürür"),
           L("NKE", +1, "Lower tariffs cut Nike's costs", "Düşük vergi Nike'ın maliyetini düşürür"),
           L("CAT", +1, "Caterpillar sells machines worldwide", "Caterpillar dünyaya makine satar"),
           L("DE", +1, "Deere sells to farmers who export crops", "Deere ürün ihraç eden çiftçilere satar"))),
    Theme("RATE_CUT", "Interest rate cut", "Faiz indirimi",
          ("lower the target range", "lowered the target range", "reduce the target range", "rate cut",
           "cut interest rates", "cuts interest rates", "cuts rates", "lowers rates", "lowered rates"),
          (),
          (L("DHI", +1, "Lower rates make mortgages cheaper; D.R. Horton builds homes", "Düşük faiz konut kredisini ucuzlatır; D.R. Horton ev yapar"),
           L("LEN", +1, "Lower rates help home builders", "Düşük faiz ev yapan şirketlere yarar"),
           L("HD", +1, "Home Depot sells to home buyers and builders", "Home Depot ev alanlara ve yapanlara satar"),
           L("IWM", +1, "Small companies borrow more, so lower rates help them", "Küçük şirketler daha çok borçlanır, düşük faiz yarar"))),
    Theme("RATE_HIKE", "Interest rate rise", "Faiz artırımı",
          ("raise the target range", "raised the target range", "rate hike", "raise interest rates",
           "raises rates", "raised rates"),
          (),
          (L("DHI", -1, "Higher rates make mortgages expensive", "Yüksek faiz konut kredisini pahalılaştırır"),
           L("LEN", -1, "Higher rates hurt home builders", "Yüksek faiz ev yapan şirketlere zarar verir"))),
    Theme("OIL_SHOCK", "Oil supply shock", "Petrol arz şoku",
          ("opec", "crude", "oil supply", "oil prices", "strait of hormuz", "oil field", "oil tanker"),
          ("cut", "disrupt", "attack", "sanction", "embargo", "halt", "surge", "jump", "blockade"),
          (L("XOM", +1, "Exxon earns more when oil is expensive", "Petrol pahalıyken Exxon daha çok kazanır"),
           L("CVX", +1, "Chevron earns more when oil is expensive", "Petrol pahalıyken Chevron daha çok kazanır"),
           L("OXY", +1, "Occidental earns more when oil is expensive", "Petrol pahalıyken Occidental daha çok kazanır"),
           L("DAL", -1, "Airlines pay more for fuel", "Havayolları yakıta daha çok öder"),
           L("UAL", -1, "Airlines pay more for fuel", "Havayolları yakıta daha çok öder"))),
    Theme("ENERGY_POLICY", "Drilling and energy policy", "Sondaj ve enerji politikası",
          ("energy dominance", "oil and gas leas", "lng export", "offshore leas", "energy emergency",
           "drilling permit", "oil and gas drilling", "federal lands for oil"),
          (),
          (L("XOM", +1, "More drilling permits help Exxon", "Daha çok sondaj izni Exxon'a yarar"),
           L("EOG", +1, "More drilling permits help EOG", "Daha çok sondaj izni EOG'ye yarar"),
           L("LNG", +1, "Cheniere exports liquefied gas", "Cheniere sıvılaştırılmış gaz ihraç eder"),
           L("KMI", +1, "Kinder Morgan runs gas pipelines", "Kinder Morgan gaz boru hatları işletir"))),
    Theme("NUCLEAR", "Nuclear power push", "Nükleer enerji hamlesi",
          ("nuclear", "reactor", "uranium"),
          ("executive order", "build", "approve", "license", "expand", "policy", "deploy", "fund", "restart"),
          (L("CEG", +1, "Constellation runs the most US nuclear plants", "Constellation ABD'nin en çok nükleer santralini işletir"),
           L("CCJ", +1, "Cameco mines uranium", "Cameco uranyum çıkarır"),
           L("BWXT", +1, "BWX Technologies makes nuclear parts", "BWX Technologies nükleer parça yapar"),
           L("VST", +1, "Vistra runs nuclear plants", "Vistra nükleer santral işletir"))),
    Theme("DEFENSE", "Defense spending", "Savunma harcaması",
          ("defense spending", "defense budget", "pentagon", "department of war", "department of defense",
           "military aid", "missile defense", "golden dome", "nato"),
          (),
          (L("LMT", +1, "Lockheed Martin builds jets and missiles", "Lockheed Martin jet ve füze yapar"),
           L("RTX", +1, "RTX builds missiles and engines", "RTX füze ve motor yapar"),
           L("NOC", +1, "Northrop Grumman builds defense systems", "Northrop Grumman savunma sistemleri yapar"),
           L("GD", +1, "General Dynamics builds ships and vehicles", "General Dynamics gemi ve araç yapar"),
           L("PLTR", +1, "Palantir sells defense software", "Palantir savunma yazılımı satar"))),
    Theme("CRYPTO", "Crypto policy or rally", "Kripto politikası ya da yükselişi",
          ("bitcoin", "crypto", "stablecoin", "digital asset"),
          ("approve", "reserve", "executive order", "etf", "record", "rally", "law", "sign", "strategic",
           "legislation", "framework"),
          (L("COIN", +1, "Coinbase earns fees on crypto trades", "Coinbase kripto işlemlerinden komisyon alır"),
           L("MSTR", +1, "Strategy holds a lot of bitcoin", "Strategy çok bitcoin tutar"),
           L("HOOD", +1, "Robinhood earns fees on crypto trades", "Robinhood kripto işlemlerinden komisyon alır"))),
    Theme("DRUG_PRICES", "Drug price pressure", "İlaç fiyatı baskısı",
          ("drug pricing", "drug prices", "most favored nation", "most-favored-nation", "medicare negotiat"),
          (),
          (L("PFE", -1, "Pfizer sells fewer dollars of drugs at lower prices", "Düşük fiyat Pfizer'ın gelirini düşürür"),
           L("LLY", -1, "Lower drug prices cut Eli Lilly's revenue", "Düşük ilaç fiyatı Eli Lilly'nin gelirini düşürür"),
           L("MRK", -1, "Lower drug prices cut Merck's revenue", "Düşük ilaç fiyatı Merck'in gelirini düşürür"))),
)

# Company names the headline may use instead of a ticker.
NAMES = {
    "nvidia": "NVDA", "apple": "AAPL", "microsoft": "MSFT", "tesla": "TSLA", "amazon": "AMZN",
    "alphabet": "GOOGL", "google": "GOOGL", "meta platforms": "META", "advanced micro devices": "AMD",
    "intel": "INTC", "broadcom": "AVGO", "tsmc": "TSM", "taiwan semiconductor": "TSM", "micron": "MU",
    "oracle": "ORCL", "palantir": "PLTR", "netflix": "NFLX", "boeing": "BA", "lockheed": "LMT",
    "exxon": "XOM", "chevron": "CVX", "coinbase": "COIN", "qualcomm": "QCOM", "arista": "ANET",
    "super micro": "SMCI", "supermicro": "SMCI", "salesforce": "CRM", "adobe": "ADBE", "uber": "UBER",
    "walmart": "WMT", "costco": "COST", "jpmorgan": "JPM", "goldman sachs": "GS", "eli lilly": "LLY",
    "novo nordisk": "NVO", "pfizer": "PFE", "constellation energy": "CEG", "vistra": "VST", "asml": "ASML",
    "applied materials": "AMAT", "lam research": "LRCX", "dell": "DELL", "ibm": "IBM", "cisco": "CSCO",
    "palo alto networks": "PANW", "crowdstrike": "CRWD", "shopify": "SHOP", "disney": "DIS",
}

# Words that make news about a company good or bad for its own stock.
GOOD_EVENTS = ("beats", "beat estimates", "tops estimates", "record revenue", "raises guidance", "raises outlook",
               "raises full-year", "raises its", "share repurchase", "buyback", "raises dividend", "fda approv",
               "fda clear", "wins contract", "awarded", "selected by", "partnership with nvidia",
               "collaboration with nvidia", "partners with nvidia", "to be acquired", "agrees to be acquired",
               "upgrade", "record quarter", "added to the s&p", "exceeds expectations")
BAD_EVENTS = ("misses", "cuts guidance", "lowers guidance", "lowers outlook", "profit warning", "recall",
              "investigation", "subpoena", "lawsuit", "downgrade", "public offering", "delist", "bankruptcy",
              "halt", "restat", "resigns", "fraud", "layoffs", "data breach")

UNIVERSE = frozenset({l.symbol for t in THEMES for l in t.links} | set(NAMES.values()))


def match(text: str) -> list[Theme]:
    low = " " + text.lower() + " "
    return [t for t in THEMES if t.matches(low)]


def companies_in(text: str) -> list[str]:
    """Big companies named in full words: "Intel" yes, "Intelligence" no."""
    low = " " + text.lower() + " "
    return list(dict.fromkeys(sym for name, sym in NAMES.items()
                              if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low)))


def company_tone(text: str) -> int:
    """+1 when the news is clearly good for the company it is about, -1 bad, 0 unclear."""
    low = " " + text.lower() + " "
    good = sum(1 for w in GOOD_EVENTS if _has(low, w))
    bad = sum(1 for w in BAD_EVENTS if _has(low, w))
    return 1 if good > bad else -1 if bad > good else 0
