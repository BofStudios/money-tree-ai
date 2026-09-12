/* Translations, in one place.
 *
 * Two rules that keep this from rotting:
 *   1. No language checks anywhere else in the app. Call t("key") and move on.
 *   2. English is the source of truth and the fallback. A key missing from
 *      Turkish renders the English string, never an empty box or the raw key.
 *
 * The Turkish column is written as Turkish finance is actually spoken, not
 * word-for-word from the English — "momentum güçlü görünüyor", not a literal
 * rendering that reads like a machine wrote it.
 */

const STRINGS = {
  en: {
    /* shell */
    "app.name": "Money Tree AI",
    "nav.home": "Home",
    "nav.research": "Research",
    "nav.chart": "Chart",
    "nav.market": "Market",
    "nav.catalysts": "Catalysts",
    "nav.activity": "Activity",
    "nav.live": "Live",
    "nav.settings": "Settings",

    /* market state */
    "market.open": "Market open",
    "market.closed": "Market closed",
    "market.closedUntil": "Closed until {when}",
    "market.premarket": "Pre-market",
    "market.afterhours": "After hours",
    "market.delayed": "Data delayed",
    "market.updated": "Updated {ago}",

    /* money honesty */
    "money.practice": "Practice money",
    "money.practiceBody":
      "You have not deposited anything. The bot is trading pretend money against real live prices, so you can watch how it behaves before any of your own money is involved.",
    "money.atRisk": "Your real money at risk",
    "money.midas": "Midas mode · scorecard only",
    "money.midasBody":
      "The bot holds no money. Your money is in Midas, where only you can move it. The figure above is a running score of what its calls would have made.",
    "money.controlled": "Money the bot controls",
    "money.realArmed": "Real money · armed",
    "money.realIdle": "Real money · not armed",

    /* research */
    "research.title": "Research",
    "research.search": "Search a company or ticker",
    "research.searchHint": "Try a name like Apple, or a ticker like AAPL",
    "research.depth": "How deep should I go?",
    "research.depth.quick": "Quick check",
    "research.depth.quickWhat": "Price, trend, and the one thing worth noticing",
    "research.depth.standard": "Standard",
    "research.depth.standardWhat": "Business, financials, valuation, technicals, risks",
    "research.depth.deep": "Deep dive",
    "research.depth.deepWhat": "Every section in detail, with the numbers",
    "research.depth.full": "Full research",
    "research.depth.fullWhat": "Everything, plus ownership, scenarios and what to watch",
    "research.attention": "What should I pay special attention to?",
    "research.attentionHint": "Pick any number, or skip and I'll decide",
    "research.plan": "Here's how I'll analyse this",
    "research.planSkipped": "Not available for this company",
    "research.start": "Start analysis",
    "research.running": "Analysing",
    "research.again": "Analyse again",
    "research.ask": "Ask about this company",
    "research.askPlaceholder": "Ask anything about {symbol}",
    "research.noAI":
      "No AI is connected, so I can show you the data but not write the analysis.",

    /* sections */
    "section.overview": "Overview",
    "section.price": "Price",
    "section.technicals": "Technical picture",
    "section.quality": "Financial health",
    "section.valuation": "Valuation",
    "section.statements": "Financial statements",
    "section.earnings": "Earnings",
    "section.analysts": "Analyst expectations",
    "section.dividend": "Dividend",
    "section.ownership": "Ownership",
    "section.news": "News",
    "section.risks": "Risks",

    /* metrics */
    "metric.price": "Price",
    "metric.change": "Change",
    "metric.marketCap": "Market cap",
    "metric.pe": "P/E",
    "metric.forwardPe": "Forward P/E",
    "metric.peg": "PEG",
    "metric.ps": "P/S",
    "metric.pb": "P/B",
    "metric.evEbitda": "EV/EBITDA",
    "metric.evRevenue": "EV/Revenue",
    "metric.eps": "EPS",
    "metric.fcfYield": "FCF yield",
    "metric.dividendYield": "Dividend yield",
    "metric.revenue": "Revenue",
    "metric.revenueGrowth": "Revenue growth",
    "metric.earningsGrowth": "Earnings growth",
    "metric.grossMargin": "Gross margin",
    "metric.operatingMargin": "Operating margin",
    "metric.netMargin": "Net margin",
    "metric.roe": "Return on equity",
    "metric.roa": "Return on assets",
    "metric.fcf": "Free cash flow",
    "metric.cash": "Cash",
    "metric.debt": "Total debt",
    "metric.netDebt": "Net debt",
    "metric.debtEquity": "Debt / equity",
    "metric.currentRatio": "Current ratio",
    "metric.beta": "Beta",
    "metric.volume": "Volume",
    "metric.avgVolume": "Average volume",
    "metric.relVolume": "Relative volume",
    "metric.week52": "52-week range",
    "metric.fromHigh": "From 52w high",
    "metric.fromLow": "From 52w low",
    "metric.nextEarnings": "Next earnings",
    "metric.targetMean": "Average target",
    "metric.consensus": "Consensus",
    "metric.analysts": "Analysts covering",
    "metric.payout": "Payout ratio",
    "metric.exDate": "Ex-dividend date",

    /* technical states */
    "state.bullish": "Trending up",
    "state.bearish": "Trending down",
    "state.mixed": "Mixed",
    "state.strong": "Strong",
    "state.moderate": "Moderate",
    "state.weak": "Weak",
    "state.high": "High",
    "state.medium": "Medium",
    "state.low": "Low",
    "state.increasing": "Increasing",
    "state.declining": "Declining",
    "state.normal": "Normal",
    "state.support": "Potential support",
    "state.resistance": "Potential resistance",

    /* modes */
    "mode.simple": "Simple",
    "mode.advanced": "Advanced",
    "mode.simpleHint": "Plain language. Numbers stay one tap away.",
    "mode.advancedHint": "Raw indicator values and full ratio tables.",
    "action.why": "Why?",
    "action.explain": "Explain",
    "action.close": "Close",
    "action.retry": "Try again",
    "action.skip": "Skip",
    "action.back": "Back",
    "action.next": "Continue",
    "action.done": "Done",
    "action.addWatchlist": "Add to watchlist",
    "action.compare": "Compare",
    "action.save": "Save",

    /* explain panel */
    "explain.what": "What it means",
    "explain.why": "Why it matters",
    "explain.watch": "What to watch",
    "explain.here": "For this company",

    /* onboarding */
    "onboard.welcome": "Let's set up your workspace",
    "onboard.intro":
      "You don't need to know anything about technical analysis — I'll handle the complicated parts and explain as we go.",
    "onboard.begin": "Get started",
    "onboard.later": "Skip for now",
    "onboard.almost": "Almost there",
    "onboard.done": "You're set",
    "onboard.doneBody":
      "I'll use this to decide how much detail to give you. You can change any of it in Settings.",
    "onboard.q.goal": "What are you mainly using this for?",
    "onboard.q.horizon": "How long do you usually think about holding something?",
    "onboard.q.focus": "What matters most to you?",
    "onboard.q.volatility": "How comfortable are you with large price swings?",
    "onboard.q.detail": "How much detail should I give you?",
    "onboard.q.level": "How familiar are you with market terminology?",

    /* answers */
    "a.unknown": "I'm not sure",
    "a.explore": "Explore companies",
    "a.track": "Track my watchlist",
    "a.opportunities": "Find opportunities",
    "a.learn": "Learn investing",
    "a.analyze": "Analyse a company",
    "a.days": "A few days",
    "a.weeks": "A few weeks",
    "a.months": "A few months",
    "a.1_3_years": "1–3 years",
    "a.3_plus_years": "3+ years",
    "a.growth": "Growth",
    "a.stability": "Stability",
    "a.dividends": "Dividends",
    "a.value": "Value",
    "a.momentum": "Momentum",
    "a.quality": "Quality",
    "a.low": "Not very",
    "a.moderate": "Somewhat",
    "a.high": "Very",
    "a.simple": "Keep it simple",
    "a.balanced": "Balanced",
    "a.deep": "Go deep",
    "a.everything": "Explain everything",
    "a.beginner": "New to this",
    "a.intermediate": "I know the basics",
    "a.advanced": "Very familiar",
    "a.profitability": "Profitability",
    "a.valuation": "Valuation",
    "a.debt": "Debt",
    "a.cash_flow": "Cash flow",
    "a.news": "Recent news",
    "a.competition": "Competition",
    "a.risks": "Risks",
    "a.earnings": "Earnings",
    "a.ownership": "Ownership",
    "a.yes": "Yes",
    "a.no": "No",

    /* settings */
    "settings.title": "Settings",
    "settings.language": "Language",
    "settings.ai": "AI preferences",
    "settings.aiSetup": "AI setup",
    "settings.aiProvider": "Answering model",
    "settings.useFreeGroq": "Use free model (Groq)",
    "settings.useFreeGroqHint": "No card, no account beyond a free key.",
    "settings.enterManually": "Enter manually",
    "settings.enterManuallyHint": "Paste your own key for Groq, Gemini, or Anthropic.",
    "settings.pasteKey": "Paste your API key",
    "settings.aiSetupSaved": "Saved. {model} is answering now.",
    "settings.aiSetupNoGroqKey":
      "No free Groq key on file yet. Get one free at console.groq.com/keys, then use \"Enter manually\".",
    "settings.aiSetupFailed": "Saved the key, but couldn't reach the model — double-check it's correct.",
    "settings.tone": "Answer length",
    "settings.depth": "Default research depth",
    "settings.level": "Your experience level",
    "settings.advanced": "Advanced mode",
    "settings.memory": "What the AI remembers",
    "settings.profile": "Your profile",
    "settings.profileHint":
      "This is everything the AI knows about your preferences. Nothing else is stored.",
    "settings.resetProfile": "Reset profile",

    /* states */
    "empty.watchlist": "Your watchlist is empty.",
    "empty.watchlistBody": "Add companies you want to keep an eye on.",
    "empty.research": "Nothing researched yet.",
    "empty.researchBody": "Search for a company above to get started.",
    "empty.news": "No recent news for this company.",
    "error.data": "Market data is temporarily unavailable.",
    "error.dataBody": "The provider didn't respond. Nothing was changed.",
    "error.notFound": "Couldn't find that company.",
    "loading.data": "Loading market data",
    "loading.analysis": "Writing your analysis",
    "na": "Not available",
    "naHint": "The data provider doesn't supply this figure.",
    "disclaimer": "Research and education, not financial advice.",
  },

  tr: {
    "nav.home": "Ana Sayfa",
    "nav.research": "Araştırma",
    "nav.chart": "Grafik",
    "nav.market": "Piyasa",
    "nav.catalysts": "Katalizörler",
    "nav.activity": "Hareketler",
    "nav.live": "Canlı",
    "nav.settings": "Ayarlar",

    "market.open": "Piyasa açık",
    "market.closed": "Piyasa kapalı",
    "market.closedUntil": "{when} tarihine kadar kapalı",
    "market.premarket": "Açılış öncesi",
    "market.afterhours": "Kapanış sonrası",
    "market.delayed": "Veri gecikmeli",
    "market.updated": "{ago} güncellendi",

    "money.practice": "Deneme parası",
    "money.practiceBody":
      "Henüz hiç para yatırmadın. Bot gerçek fiyatlara karşı sahte parayla işlem yapıyor; böylece kendi paran risk altına girmeden nasıl davrandığını izleyebilirsin.",
    "money.atRisk": "Risk altındaki gerçek paran",
    "money.midas": "Midas modu · yalnızca karne",
    "money.midasBody":
      "Bot hiç para tutmuyor. Paran Midas'ta ve oraya yalnızca sen erişebiliyorsun. Yukarıdaki rakam, botun önerilerinin ne getireceğini gösteren bir karne.",
    "money.controlled": "Botun kontrol ettiği para",
    "money.realArmed": "Gerçek para · devrede",
    "money.realIdle": "Gerçek para · devre dışı",

    "research.title": "Araştırma",
    "research.search": "Şirket veya sembol ara",
    "research.searchHint": "Apple gibi bir isim ya da AAPL gibi bir sembol dene",
    "research.depth": "Ne kadar derine ineyim?",
    "research.depth.quick": "Hızlı bakış",
    "research.depth.quickWhat": "Fiyat, trend ve dikkat çeken tek şey",
    "research.depth.standard": "Standart",
    "research.depth.standardWhat": "İş modeli, finansallar, değerleme, teknik görünüm, riskler",
    "research.depth.deep": "Derin inceleme",
    "research.depth.deepWhat": "Her bölüm detaylı, rakamlarıyla birlikte",
    "research.depth.full": "Tam araştırma",
    "research.depth.fullWhat": "Her şey; ortaklık yapısı, senaryolar ve izlenecekler dahil",
    "research.attention": "Özellikle neye dikkat etmemi istersin?",
    "research.attentionHint": "İstediğin kadar seç, ya da atla — ben karar veririm",
    "research.plan": "Bu şirketi şöyle inceleyeceğim",
    "research.planSkipped": "Bu şirket için veri yok",
    "research.start": "Analizi başlat",
    "research.running": "İnceleniyor",
    "research.again": "Yeniden incele",
    "research.ask": "Bu şirket hakkında sor",
    "research.askPlaceholder": "{symbol} hakkında istediğini sor",
    "research.noAI":
      "Bağlı bir AI yok; verileri gösterebilirim ama analizi yazamam.",

    "section.overview": "Genel bakış",
    "section.price": "Fiyat",
    "section.technicals": "Teknik görünüm",
    "section.quality": "Finansal sağlık",
    "section.valuation": "Değerleme",
    "section.statements": "Finansal tablolar",
    "section.earnings": "Bilanço",
    "section.analysts": "Analist beklentileri",
    "section.dividend": "Temettü",
    "section.ownership": "Ortaklık yapısı",
    "section.news": "Haberler",
    "section.risks": "Riskler",

    "metric.price": "Fiyat",
    "metric.change": "Değişim",
    "metric.marketCap": "Piyasa değeri",
    "metric.pe": "F/K",
    "metric.forwardPe": "İleriye dönük F/K",
    "metric.peg": "PEG",
    "metric.ps": "PD/Satış",
    "metric.pb": "PD/DD",
    "metric.evEbitda": "FD/FAVÖK",
    "metric.evRevenue": "FD/Satış",
    "metric.eps": "Hisse başı kâr",
    "metric.fcfYield": "Serbest nakit verimi",
    "metric.dividendYield": "Temettü verimi",
    "metric.revenue": "Satış geliri",
    "metric.revenueGrowth": "Satış büyümesi",
    "metric.earningsGrowth": "Kâr büyümesi",
    "metric.grossMargin": "Brüt marj",
    "metric.operatingMargin": "Faaliyet marjı",
    "metric.netMargin": "Net marj",
    "metric.roe": "Özkaynak kârlılığı",
    "metric.roa": "Aktif kârlılığı",
    "metric.fcf": "Serbest nakit akışı",
    "metric.cash": "Nakit",
    "metric.debt": "Toplam borç",
    "metric.netDebt": "Net borç",
    "metric.debtEquity": "Borç / özkaynak",
    "metric.currentRatio": "Cari oran",
    "metric.beta": "Beta",
    "metric.volume": "Hacim",
    "metric.avgVolume": "Ortalama hacim",
    "metric.relVolume": "Göreli hacim",
    "metric.week52": "52 haftalık aralık",
    "metric.fromHigh": "52h zirveden",
    "metric.fromLow": "52h dipten",
    "metric.nextEarnings": "Sonraki bilanço",
    "metric.targetMean": "Ortalama hedef",
    "metric.consensus": "Konsensüs",
    "metric.analysts": "Takip eden analist",
    "metric.payout": "Dağıtım oranı",
    "metric.exDate": "Temettü kesim tarihi",

    "state.bullish": "Yükseliş eğiliminde",
    "state.bearish": "Düşüş eğiliminde",
    "state.mixed": "Karışık",
    "state.strong": "Güçlü",
    "state.moderate": "Orta",
    "state.weak": "Zayıf",
    "state.high": "Yüksek",
    "state.medium": "Orta",
    "state.low": "Düşük",
    "state.increasing": "Artıyor",
    "state.declining": "Azalıyor",
    "state.normal": "Normal",
    "state.support": "Olası destek",
    "state.resistance": "Olası direnç",

    "mode.simple": "Sade",
    "mode.advanced": "Gelişmiş",
    "mode.simpleHint": "Sade dil. Rakamlar bir dokunuş uzağında.",
    "mode.advancedHint": "Ham gösterge değerleri ve tam oran tabloları.",
    "action.why": "Neden?",
    "action.explain": "Açıkla",
    "action.close": "Kapat",
    "action.retry": "Tekrar dene",
    "action.skip": "Atla",
    "action.back": "Geri",
    "action.next": "Devam",
    "action.done": "Tamam",
    "action.addWatchlist": "Takip listesine ekle",
    "action.compare": "Karşılaştır",

    "explain.what": "Ne anlama geliyor",
    "explain.why": "Neden önemli",
    "explain.watch": "Neye dikkat etmeli",
    "explain.here": "Bu şirket için",

    "onboard.welcome": "Çalışma alanını kuralım",
    "onboard.intro":
      "Teknik analiz bilmene gerek yok — karmaşık kısımları ben hallederim, yol boyunca açıklarım.",
    "onboard.begin": "Başlayalım",
    "onboard.later": "Şimdilik atla",
    "onboard.almost": "Az kaldı",
    "onboard.done": "Hazırsın",
    "onboard.doneBody":
      "Sana ne kadar detay vereceğime bunlara bakarak karar vereceğim. Hepsini Ayarlar'dan değiştirebilirsin.",
    "onboard.q.goal": "Burayı esas olarak ne için kullanıyorsun?",
    "onboard.q.horizon": "Bir yatırımı genelde ne kadar süre tutmayı düşünürsün?",
    "onboard.q.focus": "Senin için en önemlisi ne?",
    "onboard.q.volatility": "Sert fiyat dalgalanmaları seni ne kadar rahatsız eder?",
    "onboard.q.detail": "Sana ne kadar detay vereyim?",
    "onboard.q.level": "Piyasa terimlerine ne kadar aşinasın?",

    "a.unknown": "Bilmiyorum",
    "a.explore": "Şirketleri keşfetmek",
    "a.track": "Takip listemi izlemek",
    "a.opportunities": "Fırsat aramak",
    "a.learn": "Yatırımı öğrenmek",
    "a.analyze": "Bir şirketi incelemek",
    "a.days": "Birkaç gün",
    "a.weeks": "Birkaç hafta",
    "a.months": "Birkaç ay",
    "a.1_3_years": "1–3 yıl",
    "a.3_plus_years": "3+ yıl",
    "a.growth": "Büyüme",
    "a.stability": "İstikrar",
    "a.dividends": "Temettü",
    "a.value": "Ucuzluk",
    "a.momentum": "Momentum",
    "a.quality": "Kalite",
    "a.low": "Pek değil",
    "a.moderate": "Biraz",
    "a.high": "Oldukça",
    "a.simple": "Sade tut",
    "a.balanced": "Dengeli",
    "a.deep": "Derine in",
    "a.everything": "Her şeyi açıkla",
    "a.beginner": "Yeniyim",
    "a.intermediate": "Temelleri biliyorum",
    "a.advanced": "Oldukça aşinayım",
    "a.profitability": "Kârlılık",
    "a.valuation": "Değerleme",
    "a.debt": "Borç",
    "a.cash_flow": "Nakit akışı",
    "a.news": "Son haberler",
    "a.competition": "Rekabet",
    "a.risks": "Riskler",
    "a.earnings": "Bilanço",
    "a.ownership": "Ortaklık yapısı",
    "a.yes": "Evet",
    "a.no": "Hayır",

    "settings.title": "Ayarlar",
    "settings.language": "Dil",
    "settings.ai": "AI tercihleri",
    "settings.aiSetup": "AI kurulumu",
    "settings.aiProvider": "Cevaplayan model",
    "settings.useFreeGroq": "Ücretsiz model kullan (Groq)",
    "settings.useFreeGroqHint": "Kart yok, sadece ücretsiz bir anahtar yeterli.",
    "settings.enterManually": "Elle gir",
    "settings.enterManuallyHint": "Groq, Gemini veya Anthropic için kendi anahtarını yapıştır.",
    "settings.pasteKey": "API anahtarını yapıştır",
    "settings.aiSetupSaved": "Kaydedildi. Artık {model} cevap veriyor.",
    "settings.aiSetupNoGroqKey":
      "Henüz kayıtlı ücretsiz bir Groq anahtarı yok. console.groq.com/keys adresinden ücretsiz al, sonra \"Elle gir\"i kullan.",
    "settings.aiSetupFailed": "Anahtar kaydedildi ama modele ulaşılamadı — doğru olduğundan emin ol.",
    "action.save": "Kaydet",
    "settings.tone": "Cevap uzunluğu",
    "settings.depth": "Varsayılan araştırma derinliği",
    "settings.level": "Deneyim seviyen",
    "settings.advanced": "Gelişmiş mod",
    "settings.memory": "AI'ın hatırladıkları",
    "settings.profile": "Profilin",
    "settings.profileHint":
      "AI'ın tercihlerin hakkında bildiği her şey bu. Bunun dışında bir şey saklanmıyor.",
    "settings.resetProfile": "Profili sıfırla",

    "empty.watchlist": "Takip listen boş.",
    "empty.watchlistBody": "Göz kulak olmak istediğin şirketleri ekle.",
    "empty.research": "Henüz bir araştırma yok.",
    "empty.researchBody": "Başlamak için yukarıdan bir şirket ara.",
    "empty.news": "Bu şirket için güncel haber yok.",
    "error.data": "Piyasa verisine şu an ulaşılamıyor.",
    "error.dataBody": "Sağlayıcı yanıt vermedi. Hiçbir şey değişmedi.",
    "error.notFound": "O şirket bulunamadı.",
    "loading.data": "Piyasa verisi yükleniyor",
    "loading.analysis": "Analizin yazılıyor",
    "na": "Veri yok",
    "naHint": "Veri sağlayıcı bu rakamı vermiyor.",
    "disclaimer": "Araştırma ve eğitim amaçlıdır, yatırım tavsiyesi değildir.",
  },
};

let current = "en";

/** Look a string up, falling back to English, then to the key itself. */
export function t(key, vars) {
  const table = STRINGS[current] || STRINGS.en;
  let out = table[key];
  if (out === undefined) out = STRINGS.en[key];
  if (out === undefined) return key;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      out = out.replaceAll(`{${name}}`, String(value));
    }
  }
  return out;
}

export function setLanguage(code) {
  current = STRINGS[code] ? code : "en";
  document.documentElement.lang = current;
  applyTranslations();
  return current;
}

export function getLanguage() {
  return current;
}

/** Rewrite every element carrying a data-i18n attribute. */
export function applyTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  root.querySelectorAll("[data-i18n-label]").forEach((el) => {
    el.setAttribute("aria-label", t(el.dataset.i18nLabel));
  });
}

/** Which languages exist, for the settings picker. */
export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "tr", label: "Türkçe" },
];
