# Gizlilik

Money Tree senin bilgisayarında çalışan bir programdır. Hesap yok, bizim sunucumuz yok. Bu sayfa neyin saklandığını, neyin PC'den çıktığını ve kime gittiğini söyler. Koddan üretilir; ikisi uyuşmazsa bir test kırılır.

## Kısaca

- **Bize hiçbir şey gönderilmez.** BofStudios'un sunucusu, hesap sistemi ve verini görme yolu yok.
- **Reklam yok, izleme yok, analitik yok, çökme raporu yok, veri satışı yok.**
- **Anahtarların** Windows kullanıcın için şifreli saklanır (DPAPI). Sadece ait oldukları servise gider, yapay zekâya asla.
- **Her şey tek klasörde**, PC'nde. Ayarlar > Gizlilik ve veri'den açabilir, dışa aktarabilir ve botun senin hakkında tuttuklarını silebilirsin.
- **Uygulama kısa ve açık bir sunucu listesiyle konuşur** (aşağıda). Kod listede olmayan bir sunucuyu anarsa test kırılır.
- **Kod açık.** GitHub'da oku ya da birine okut.

## PC'nde neler saklanır

Klasör `%LOCALAPPDATA%\BofStudios\Money Tree AI`. Gizli işaretli dosyalar dışa aktarmaya asla girmez.

| Dosya | Ne olduğu | Gizli |
|---|---|---|
| `data/keys.dat` | Alpaca ve yapay zekâ anahtarların, bu Windows kullanıcısı için şifreli. | evet |
| `.env` | Elle yazdıysan anahtarların. | evet |
| `data/dashboard.token` | Panelin ve telefon bağlantısının şifresi. | evet |
| `data/trading.db` | Tüm işlemler, hesap değeri kayıtları ve kaydedilen mumlar (CSV olarak verilir). |  |
| `data/user_profile.json` | Seçimlerin: dil, kararı kimin verdiği, izleme listesi. |  |
| `data/mentor_memory.json` | Yapay zekâyla sohbetin ve hatırlamasını istediğin bilgiler. |  |
| `data/mentor_feed.json` | Uygulamanın yan sohbette söyledikleri. |  |
| `data/brain` | Botun öğrendikleri: haber hafızası, strateji ilerlemesi, sürü. |  |
| `data/lab.json` | Son Lab tekrarı ve avantaj filtresi anahtarı. |  |
| `data/privacy.json` | Bu gizlilik seçimleri. |  |
| `data/journal.json` | Sayaçlar: uygulamanın ne kadar çalıştığı. |  |
| `data/engine_state.json` | Açık pozisyonlar ve durdurma bayrağı, yeniden başlatmaya dayanmak için. |  |
| `data/risk_day.json` | Günlük sınır için bugünkü zarar sayacı. |  |
| `data/live_feed.json` | Canlı akışın son satırları. |  |
| `logs` | Kayıt dosyaları, anahtarlar temizlenmiş. |  |

## Uygulama kimlerle konuşuyor

Listenin tamamı bu. Bir servis iki kez görünüyorsa birden fazla adresi var.

| Kim | Adres | Oraya ne gider | Ne zaman | Gizlilik sayfaları |
|---|---|---|---|---|
| Apple newsroom | `www.apple.com` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| Bank of England | `www.bankofengland.co.uk` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| Bank of Japan | `www.boj.or.jp` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| Business Wire | `feed.businesswire.com` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| European Central Bank | `www.ecb.europa.eu` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| Frankfurter | `api.frankfurter.dev` | Herkese açık döviz kurları. | Uygulama çalışırken okunur |  |
| GlobeNewswire | `www.globenewswire.com` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| Google blog | `blog.google` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| Microsoft newsroom | `news.microsoft.com` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| NVIDIA newsroom | `nvidianews.nvidia.com` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| OpenAI news | `openai.com` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| PR Newswire | `www.prnewswire.com` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| The White House | `www.whitehouse.gov` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| US Dept. of Defense | `www.defense.gov` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| US Dept. of Energy | `www.energy.gov` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| US EIA | `www.eia.gov` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| US FDA | `www.fda.gov` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| US Federal Reserve | `www.federalreserve.gov` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| US SEC | `www.sec.gov` | Herkese açık basın bildirileri. | Uygulama çalışırken okunur | [gizlilik sayfası](https://www.sec.gov/privacy) |
| US SEC (EDGAR) | `data.sec.gov` | Şirketlerin herkese açık bildirimleri. | Uygulama çalışırken okunur | [gizlilik sayfası](https://www.sec.gov/privacy) |
| US SEC (EDGAR) | `efts.sec.gov` | Herkese açık bildirimlerde arama. | Uygulama çalışırken okunur | [gizlilik sayfası](https://www.sec.gov/privacy) |
| US Trade Representative | `ustr.gov` | Herkese açık haber ve duyurular okunur. Senin hakkında bir şey gönderilmez, yalnızca istek. | Uygulama çalışırken okunur |  |
| Wikimedia | `en.wikipedia.org` | Sayfa görüntülenme sinyali için şirketin sayfa adı. | Uygulama çalışırken okunur | [gizlilik sayfası](https://foundation.wikimedia.org/wiki/Policy:Privacy_policy) |
| Wikimedia | `wikimedia.org` | Herkese açık sayfa görüntülenme sayıları. | Uygulama çalışırken okunur | [gizlilik sayfası](https://foundation.wikimedia.org/wiki/Policy:Privacy_policy) |
| Alpaca | `api.alpaca.markets` | Emirlerin, pozisyonların ve hesabın; fiyatlar ve haberler. Alpaca anahtarların her isteği imzalar. | Sadece o servisin anahtarını girince | [gizlilik sayfası](https://alpaca.markets/disclosures) |
| Alpaca | `data.alpaca.markets` | Fiyatlar, 1 dakikalık mumlar ve haberler. | Sadece o servisin anahtarını girince | [gizlilik sayfası](https://alpaca.markets/disclosures) |
| Alpaca | `paper-api.alpaca.markets` | Aynısı, deneme (paper) hesabı için. | Sadece o servisin anahtarını girince | [gizlilik sayfası](https://alpaca.markets/disclosures) |
| Google (Gemini) | `generativelanguage.googleapis.com` | Groq ile aynı. Google'ın ücretsiz katmanında Google gönderdiklerini ürünlerini geliştirmek için kullanabilir ve insanlar okuyabilir. Ekran görüntüsü buraya sadece Ayarlar'dan izin verirsen gider. | Sadece o servisin anahtarını girince | [gizlilik sayfası](https://aistudio.google.com/docs/terms) |
| Groq | `api.groq.com` | Sorun, kısa bir bot durumu (gizlilik düzeyine göre hisse, fiyat, pozisyon) ve eklediğin ekran görüntüleri. Anahtarların asla. Groq varsayılan olarak veriyi saklamadığını söylüyor ama en çok 30 gün kayıt tutabilir. | Sadece o servisin anahtarını girince | [gizlilik sayfası](https://groq.com/privacy-policy) |
| GitHub | `api.github.com` | Uygulamanın en yeni sürüm numarasını sorar. Senin hakkında bir şey göndermez. | Sadece sen istersen | [gizlilik sayfası](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) |
| Alpaca | `alpaca.markets` | Alpaca sayfalarına bağlantı. | Tıklayabileceğin bağlantı; uygulama bağlanmaz | [gizlilik sayfası](https://alpaca.markets/disclosures) |
| Alpaca | `app.alpaca.markets` | Hesap açmak ya da anahtar üretmek için bağlantı. | Tıklayabileceğin bağlantı; uygulama bağlanmaz | [gizlilik sayfası](https://alpaca.markets/disclosures) |
| GitHub | `github.com` | Uygulamanın kaynak koduna bağlantı. | Tıklayabileceğin bağlantı; uygulama bağlanmaz | [gizlilik sayfası](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) |
| Groq | `console.groq.com` | Ücretsiz anahtar üretmek için bağlantı. | Tıklayabileceğin bağlantı; uygulama bağlanmaz | [gizlilik sayfası](https://groq.com/privacy-policy) |
| This PC | `127.0.0.1` | Uygulamanın kendi penceresi ve kendin çalıştırdığın yapay zekâ (Ollama). PC'nden çıkmaz. | Sadece bu PC |  |
| Anthropic (Claude) | `api.anthropic.com` | Groq ile aynı, sadece Claude anahtarı girdiysen. | O servisi kullanınca gömülü bir parça kullanır | [gizlilik sayfası](https://www.anthropic.com/legal/privacy) |
| Telegram | `api.telegram.org` | İstediğin uyarılar, kendi sohbetine, sadece bot anahtarı girdiysen. | O servisi kullanınca gömülü bir parça kullanır | [gizlilik sayfası](https://telegram.org/privacy) |
| Yahoo Finance | `query1.finance.yahoo.com` | Alpaca anahtarı yokken ya da Alpaca dinlenirken fiyat ve mumlar, ve Lab tekrarının 1 dakikalık mumları (sadece hisse adları). | O servisi kullanınca gömülü bir parça kullanır | [gizlilik sayfası](https://legal.yahoo.com/us/en/yahoo/privacy/index.html) |

## Yapay zekâya ne gider

- Sadece sen bağlarsan: girdiğin anahtarla Groq, Google Gemini ya da Claude; ya da PC'nde çalışan ve dışarı hiçbir şey göndermeyen Ollama.
- Gidenler: yazdığın soru; bot hakkında kısa bir not (hisse adları, fiyatlar, pozisyonlar; tutarlar aşağıda seçtiğin düzeye göre); botun okuduğu haber başlıkları; hatırlamasını istediğin bilgiler; soruna eklediğin ekran görüntüleri.
- Asla gitmeyenler: anahtarların, panel şifresi, hesap numaraların, adın ya da e-postan (uygulama bunları tutmaz).
- Ekran görüntüleri Groq'a gider. Google Gemini'ye sadece Ayarlar'dan izin verirsen gider; çünkü Google'ın ücretsiz katmanında Google gelenleri ürünlerini geliştirmek için kullanabilir ve insanlar okuyabilir.
- Groq varsayılan olarak çıkarım verisini saklamadığını söylüyor ama en çok 30 gün kayıt tutabilir. Her şirketin veriyle ne yaptığı için kendi sayfasını oku; bağlantılar yukarıdaki tabloda.
- Ayarlar > Gizlilik ve veri, yapay zekâya en son ne gönderildiğini aynen gösterir.

## Seçimlerin

- **Yapay zekâ ne görüyor:** her şey, sadece yüzdeler ve hisse adları ya da hesabın hakkında hiçbir şey.
- **Sohbeti hatırla:** kapalıysa sohbet PC'ne kaydedilmez ve eski mesajlar gönderilmez.
- **Telefondan erişim:** yeni kurulumda varsayılan kapalı. Kapalıysa paneli sadece bu PC açabilir.
- **Ekran görüntüsü Gemini'ye:** varsayılan kapalı.
- **Kayıt dosyaları:** ne kadar tutulacağı (1 ile 90 gün). Anahtarlar temizlenmiştir.
- **Dışa aktar:** anahtarsız ve şifresiz bir zip.
- **Temizle:** sohbet ve hafıza, botun öğrendikleri, Lab sonuçları, kayıtlar ya da dördü birden. İşlemlerin ve anahtarların orada silinmez: anahtarları Para ve anahtarlar'dan sil ya da uygulamayı kapatıp klasörü sil.

## Panel nasıl korunur

- Şifre ister. Bağlantıyla ilk ziyaret tarayıcıyı HttpOnly bir çerezle içeri alır ve şifreyi adres çubuğundan siler.
- Sadece bu PC'de dinler; telefondan erişimi sen açmadıkça.
- Beş yanlış deneme o adresi bir dakika, sonra daha uzun süre kilitler.
- Bir değişiklik sayfanın kendi adresinden gelmeli; başka bir web sayfası buradaki düğmelere basamaz.
- Gerçek parayı uygulamanın kendisi asla kurmaz. Durdur, her emirden hemen önce kontrol edilir.

## Çocuklar

Gerçek para ile işlem için yetişkin adına bir aracı kurum hesabı gerekir; bu bizim değil, aracı kurumun kuralı. Uygulama yaş, ad ya da kimlik sormaz.

## Finansal tavsiye değildir

Money Tree bir yazılımdır. İçindeki hiçbir şey al ya da sat önerisi değildir. Şartları kılavuzda ve TERMS.txt içinde oku.

## Değişiklikler ve sorular

Bu sayfa sadece kodla birlikte değişir; yani her değişiklik GitHub'daki herkese açık geçmişte durur. Sorular için orada bir issue aç. Güvenlik sorunu için SECURITY.md'deki özel bildirimi kullan.
