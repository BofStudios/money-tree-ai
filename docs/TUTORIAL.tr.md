# Money Tree AI: tam rehber

English: [TUTORIAL.md](TUTORIAL.md)

> [!WARNING]
> Araştırma yazılımıdır, yatırım tavsiyesi değildir. Kâr vaadi yoktur. İşlem para kaybettirebilir, beklediğinden
> fazlasını da. Deneme parasıyla başla. Hesabındaki her işlemden sen sorumlusun.

**İçindekiler**
1. [Nedir ve nasıl karar verir](#1-nedir-ve-nasıl-karar-verir)
2. [Kurulum](#2-kurulum)
3. [İlk açılış](#3-ilk-açılış)
4. [Alpaca, adım adım](#4-alpaca-adım-adım)
5. [Ücretsiz yapay zekâ](#5-ücretsiz-yapay-zekâ)
6. [Deneme parası, sonra gerçek para](#6-deneme-parası-sonra-gerçek-para)
7. [Kur, Durdur, Başlat](#7-kur-durdur-başlat)
8. [Modlar sekmesi, açıklamalı](#8-modlar-sekmesi-açıklamalı)
9. [Bütün ekranlar](#9-bütün-ekranlar)
10. [Haberle işlem, ayrıntılı](#10-haberle-işlem-ayrıntılı)
11. [Nasıl gelişir](#11-nasıl-gelişir)
12. [Hafıza ve verilerin](#12-hafıza-ve-verilerin)
13. [Güvenlik sınırları](#13-güvenlik-sınırları)
14. [Telefon ve Telegram](#14-telefon-ve-telegram)
15. [İyi bir ilk hafta](#15-iyi-bir-ilk-hafta)
16. [Sorunlar ve çözümler](#16-sorunlar-ve-çözümler)
17. [Kaynaktan derleme](#17-kaynaktan-derleme)

---

## 1. Nedir ve nasıl karar verir

Money Tree AI bir Windows masaüstü uygulamasıdır. ABD hisselerinden oluşan bir listeye bakar, haberleri okur,
şirketleri kontrol eder ve **kendi Alpaca hesabın** üzerinden emir verir. Her adım **Canlı** sekmesinde nedeniyle
birlikte görünür.

Bir alım şu kapılardan sırayla geçmek zorundadır:

| Kapı | Soru | Hayır diyebilen |
|---|---|---|
| Stop | STOP'a bastın mı? | Sen, her zaman, en önce |
| Piyasa saati | ABD piyasası açık mı? | Takvim |
| Sinyal | Strateji almak istiyor mu? | Strateji (sürünün şampiyonu) |
| Araştırma | Şirketin 5 kontrolü, günlük trend, haberler, geçmiş sonuçlar | Araştırma masası |
| Yapay zekâ kontrolü | Haberlerde kırmızı bayrak var mı (işlem durdurma, sahtekârlık, yakın sonuç)? | Yapay zekâ |
| Risk kuralları | Boyut yeterince küçük mü? Nakit var mı? Boş yer var mı? | Risk yöneticisi |
| Kurma | (Sadece gerçek para) Kurdun mu? | Sen |
| Karar veren | Tam otomatik mi, onayını mı bekler? | Sen |

Günlük grafiğin düşmesi alımı engellemez (Dikkatli tarz hariç); emri yarıya indirir. Zarar durdur, günlük zarar
sınırı ve kurma hiçbir modla değişmez.

## 2. Kurulum

1. [Son sürümden](https://github.com/BofStudios/money-tree-ai/releases/latest) `MoneyTreeAI-Desktop-<sürüm>-win64.zip`
   dosyasını indir, istediğin bir yere aç (örneğin `İndirilenler\Money Tree`).
2. `Money Tree AI.exe` dosyasını çalıştır. Uygulama imzalı olmadığı için Windows SmartScreen "Windows bilgisayarınızı
   korudu" diyebilir: **Ek bilgi**, sonra **Yine de çalıştır**'a tıkla.
3. Logo hemen görünür. Pencere 5–15 saniyede açılır.
4. Aynı anda tek kopya çalışır. Simgeye tekrar tıklarsan açık pencere öne gelir.
5. Pencereyi kapatmak onu sistem tepsisine gizler. Botu durdurmak için **tepsi simgesine sağ tık, Çık**.

Windows 10 ya da 11, 64 bit, yaklaşık 1 GB boş disk ve 8 GB bellek.

## 3. İlk açılış

Uygulama birkaç soru sorar. Önce risk kutusunu işaretle: bunun yazılım olduğunu, tavsiye olmadığını söyler.

1. **Piyasa:** ABD, Avrupa (ABD'deki listeleriyle) ya da ikisi.
2. **Ne kadar tutacak:** günler (15 dakikalık grafik), haftalar (1 saatlik) ya da aylar (günlük).
3. **Kim karar verir:** tam otomatik, önce bana sor ya da sadece fikir.
4. **Küçük hesap:** açıkken hissenin kesirlerini alabilir (aracı kurumun izin vermesi gerekir, Alpaca verir).

Sonra botların işlemciyi ne kadar kullanacağını sorar. **Tam** ya da **Hafif** seç; sonra Modlar'dan değiştirebilirsin.
Her cevap sonradan değiştirilebilir.

## 4. Alpaca, adım adım

[Alpaca](https://alpaca.markets), botun üzerinden işlem yaptığı ABD aracı kurumudur. Ücretsiz bir **paper** (deneme)
hesabı ve bir canlı hesabı vardır. Sitedeki menü adları değişebilir; aynı kelimeleri ara.

### 4.1 Hesabı aç
1. alpaca.markets adresine git, e-postanla kaydol.
2. E-postayı doğrula. Panele düşersin. Hemen bir **paper trading** hesabın vardır; sahte parası vardır, kimlik
   kontrolü istemez.
3. **Gerçek para** için Alpaca'nın kimlik (KYC) formunu bitirmen ve hesabı fonlaman gerekir. Ülkenin kabul edilip
   edilmediği, yaş şartı ve para yatırma seçenekleri Alpaca'nındır; önce onların sayfalarını oku. Hesabın
   sahibi hesaptan sorumludur.

### 4.2 Deneme parası için API anahtarı al
1. Panelde (sol üst) **Paper Trading**'e geç.
2. **API Keys** kısmını bul (sağ tarafta ya da hesap menüsünde) ve **Generate New Key**'e bas.
3. **Key**'i ve **Secret**'ı hemen kopyala. Secret **bir kez** gösterilir. Kaybedersen yeni çift oluştur.
4. Paper anahtarları `PK` ile başlar.

### 4.3 Anahtarları uygulamaya gir
1. Money Tree'de: **Ayarlar → Para ve anahtarlar**.
2. Key ve Secret'ı **paper** kutularına yapıştır ve **Kaydet**'e bas. Uygulama önce Alpaca ile kontrol eder;
   reddedilirse nedenini söyler.
3. Anahtarlar Windows kullanıcın için şifreli saklanır. Sayfa sadece son dört karakteri gösterir.
4. Uygulama Alpaca paper hesabınla yeniden başlar. Ana sayfa kartında **Alpaca paper** yazar.

### 4.4 Gerçek para (sadece hazır olunca)
1. Alpaca panelinde **Live Trading**'e geç ve canlı anahtar oluştur (`AK` ile başlar).
2. Ayarlar → Para ve anahtarlar'da **live** kutularına yapıştır.
3. **Modlar → Para → Gerçek para**'yı aç (ya da Ana sayfa kartında **Gerçek paraya geç**). Uygulamanın istediği
   onay cümlesini yaz. Uygulama canlı hesapla yeniden başlar.
4. Ana sayfa kartında **GERÇEK PARA** yazar. Bot, sen kurana kadar sadece **izler** (bölüm 7).

Para sadece Alpaca'nın kendi sitesinde ya da uygulamasında girer ve çıkar. Money Tree asla banka bilgisi istemez ve
para taşımaz.

## 5. Ücretsiz yapay zekâ

Yapay zekâ işlemleri açıklar, sohbette cevap verir ve son dakika haberleri değerlendirir. Olmadan da bot kurallarıyla
işlem yapar, ama haberle işlem sadece bir şirket hakkındaki çok açık haberde hareket eder.

1. [console.groq.com](https://console.groq.com) adresinden ücretsiz anahtar al (ya da Gemini için Google AI Studio).
2. **Ayarlar → Yapay zekâ → Ücretsiz Groq kullan**, anahtarı yapıştır.
3. Bir yapay zekâ meşgulse ya da kredisi bittiyse uygulama bağladığın diğerini kullanır. Ayarlar hangisi ve neden olduğunu gösterir.

Yapay zekâya sadece başlıklar ve kısa bilgiler gider, anahtarların asla.

## 6. Deneme parası, sonra gerçek para

| Seviye | Para | Fiyatlar | Ne zaman |
|---|---|---|---|
| Simülasyon | Sadece bu bilgisayarda | Ücretsiz açık | Hiç anahtar yok |
| Alpaca paper | Alpaca'nın sahte parası | Alpaca | Paper anahtarından sonra |
| Gerçek para | Senin | Alpaca | Canlı anahtar, yazarak onay ve kurmadan sonra |

Deneme parasıyla en az iki hafta çalıştır. Ana sayfadaki **karneye** bak: botu, aynı parayla SPY tutmakla
karşılaştırır. Bot gerideyse gerçek parada da geride olur.

## 7. Kur, Durdur, Başlat

- **Gerçek parayı kur** (Modlar → Para ya da Ana sayfa kartı). Gerçek parada bot, sen kurana kadar sadece izler.
  Günlük zarar sınırında, Kapat'a bastığında ve uygulama kapanınca kendini kapatır. **Uygulama her açıldığında yeniden
  kur.** Ana sayfa kartı, üstteki rozet, Windows bildirimi ve Kur tuşlu Telegram mesajı hatırlatır.
- **STOP** (kırmızı, sağ üst). O andan itibaren bot hiçbir şey almaz ve sinyalle satmaz. Zarar durdur ve kâr al aktif
  kalır. STOP yeniden başlatmadan sonra da hatırlanır. Sohbete `dur` da yazabilirsin.
- **Başlat** botun tekrar işlem yapmasını sağlar. Sohbete `başlat` yaz.

Ana sayfadaki **İşlem yapıyor mu?** kartı her kapıyı ve hangisinin kapalı olduğunu listeler.

## 8. Modlar sekmesi, açıklamalı

### Para
- **Deneme**: gerçek fiyatlar, deneme parası.
- **Gerçek para**: Alpaca canlı hesabın. Kurulu mu değil mi gösterir. Kur ve Kapat tuşları.

### Hız
| Hız | Ne yapar | Ne zaman |
|---|---|---|
| Eko | Strateji botları %15 güçte. Dakikada bir bakış. | Bilgisayar sessiz ve serin kalmalı |
| Normal | Botlar tam güçte. Dakikada bir bakış. **Otomatik eko**, sen bilgisayarı kullanırken onları %25'e indirir. | Varsayılan |
| Ultra | Her işlemci çekirdeğinde bir bot (en fazla 16), 13 haber kaynağı daha (merkez bankaları, SEC, FDA, Pentagon, büyük şirket haber odaları), 3 kat sık haber kontrolü, 15 saniyede bir bakış, 16 büyük hisse daha, dört haber işlemine yer, 3 kat yapay zekâ düşünmesi. Kırmızı kenar ve ULTRA rozeti. Önce tikli bir uyarı çıkar. | Bilgisayarı açık bırakıyorsun ve en yüksek tepki hızı istiyorsun |

Ultra daha çok kâr demek değildir. Tüm bilgisayarı ve ücretsiz yapay zekâ hakkının daha fazlasını kullanır.

### İşlem tarzı
| Tarz | Şirket kontrolleri | Haber ne kadar emin olmalı | Günlük grafik düşüyorsa |
|---|---|---|---|
| Dikkatli | Sadece ALIM BÖLGESİ şirketleri | %75 | Alımı engeller |
| Dengeli (varsayılan) | UZAK DUR şirketlerini atlar | %60 | Emri yarıya indirir |
| Cesur | Kapalı | %55 | Emri yarıya indirir |

### Kim karar verir
- **Tam otomatik**: sınırlar içinde kendi alır ve satar.
- **Önce bana sor**: her alım birkaç dakika senin Onayını bekler (Ana sayfa, Telegram). Stop bekleyen alımları iptal eder.
- **Sadece fikir**: sadece önerir, asla almaz.

### Akıllı özellikler
Haberle işlem, Kendini geliştir (strateji botları), Yeni hisse bul (tüm piyasanın konuştuğu en fazla üç hisse),
Yapay zekâ kontrolü, Sonuçlardan öğren, Haber kontrolü, Otomatik eko.

## 9. Bütün ekranlar

| Ekran | Ne gösterir |
|---|---|
| Ana Sayfa | Paran, **İşlem yapıyor mu?**, bot ve SPY, elindekiler, günün sonucu, Başlat/Durdur/Tara |
| Modlar | Bölüm 8'in hepsi |
| Canlı | Her adım anında, nedeniyle, düz dille |
| Beyin | **Refleks** (haber kararları), **Seçimler** (5 şirket kontrolü), **Haber radarı**, **Öğrenme**, **Hafıza**, **Kapılar** |
| Sürü | On strateji botu, sonuçları ve hesabın kullandığı strateji. Sıfırla, orijinali geri koyar |
| Araştırma | Herhangi bir ABD hissesine bak: finansallar, raporlar, yapay zekâ özeti, sorular |
| Grafik, Piyasa, Haberler, Katalizörler, Etkinlik | Fiyatlar, piyasa, başlıklar, tarihli olaylar, geçmiş |
| Ayarlar | Başlarken, anahtarlar, yapay zekâ, dil, veri klasörün, kılavuz |

Soldaki **yapay zekâ paneli** soruları cevaplar ("neden işlem yok?"). "hatırla ..." dersen notu saklar.

## 10. Haberle işlem, ayrıntılı

1. **Okur.** Birkaç saniyede bir: merkez bankaları, Beyaz Saray, SEC, şirket haber odaları, basın ajansları ve
   Alpaca'nın haber akışı. Sadece son 15 dakikanın haberi işlem tetikleyebilir.
2. **Dalga.** Haber kimin hakkında ve başka kimi hareket ettirir (bir çip lansmanı bellek, enerji ve soğutmayı da).
3. **Düşünür.** Yapay zekâ adım adım inceler ve her hisseyi puanlar: yukarı ya da aşağı, ne kadar emin, kaç saat.
   Önemsiz haberler (ödüller, marka yenileme, rutin ortaklıklar) düşük puan alır.
4. **Onaylar.** Fiyat on dakika içinde katılmalı: küçük bir yükseliş, ama bitmiş bir hareket değil. 5 doların altındaki
   ve az işlem gören hisseler atlanır.
5. **Hareket eder.** Alım, her işlemle aynı kapılardan süre sınırıyla geçer. Elindeki hisseye kötü haber gelirse satabilir.

Her kararı **Beyin → Refleks**'te gör.

## 11. Nasıl gelişir

- **Strateji botları** binlerce strateji üretir ve aylarca gerçek fiyat üzerinde dener. Yenisi, sadece hiçbir botun
  eğitilmediği fiyatlarda, bir farkla kazanırsa ve ikinci görülmemiş dönemde de dayanırsa mevcut olanın yerine geçer.
  Her bot en iyi bulduklarını çalışmalar arasında hatırlar.
- **Sonuçlardan öğrenme**: her alım sinyali sonuna kadar izlenir; kaybettiren kurulumlar küçültülür ya da engellenir.
- **Haber hafızası**: her haber fikri bir işlem günü sonra gerçek fiyatla karşılaştırılır. İşe yarayan haber türlerine
  %30'a kadar daha çok, yaramayanlara %30'a kadar daha az güvenilir. Yapay zekâ bu kaydı görür.
- **Beyin → Hafıza** seviyeyi, sayıları ve nasıl geliştiğini gösterir.

Zaman ister: gün değil, hafta.

## 12. Hafıza ve verilerin

Her şey `%LOCALAPPDATA%\BofStudios\Money Tree AI` içinde durur:

| Öğe | Yeri |
|---|---|
| Anahtarlar (şifreli) | `data\keys.dat` |
| İşlemler ve bakiye | `data\trading.db` |
| Öğrendikleri | `data\brain\` |
| Ayarlar | `config\config.yaml`, `.env` |
| Kayıtlar | `logs\` |

Güncellemeler bu klasörü kullanır. **Yedek:** uygulamayı kapat, klasörü kopyala. **Yeni bilgisayar:** kopyala, sonra
anahtarlarını tekrar gir (tek bir Windows kullanıcısı için şifrelidirler). **Sıfırdan başla:** Beyin → Öğrenme →
Unut, ya da uygulama kapalıyken klasörü sil.

## 13. Güvenlik sınırları

| Sınır | Anlamı |
|---|---|
| İşlem başına risk | Zarar durdur dolarsa kaybedilen para, hesabın sabit küçük bir parçasıdır |
| Günlük zarar sınırı | Sınıra gelince gerçek para o gün için kapanır. Yeniden başlatmak sıfırlamaz |
| Pozisyonlar | Açık hisse sayısına ve tek hissedeki hesap payına üst sınır |
| Zarar durdur ve hedef | Her alımda var. Tam hisse alımlarında Alpaca'da durur, bilgisayar kapalıyken de çalışır |
| Molalar | Her işlemden sonra bekleme, art arda zarar durdurmadan sonra mola, büyük düşüşte mola |

`config\config.yaml` içinde düzenle. Kişisel sürümde üst sınır yoktur; küçük değerleri kendin seç.

## 14. Telefon ve Telegram

- **Telefon bağlantısı:** tepsi simgesi menüsü → **Telefon bağlantısını kopyala**. Aynı Wi-Fi. Bağlantı özel bir şifre
  taşır; paylaşma.
- **Telegram:** @BotFather ile bir bot yap, token'ı `.env` içine `TELEGRAM_BOT_TOKEN`, sohbet kimliğini
  `TELEGRAM_CHAT_IDS` olarak yaz. Alımları, onayları ve kurma hatırlatmasını alırsın; `/status`, `/stop`, `/start`
  kullanabilirsin.

## 15. İyi bir ilk hafta

1. 1. gün: kur, deneme parası, yapay zekâyı bağla. Eko ya da Normal kalsın.
2. 1–7. günler: her gün **Canlı** ve **Beyin → Refleks**'i oku. Sessizse yapay zekâya "neden işlem yok?" diye sor.
3. İki haftadan sonra karneyi aç. SPY'ın önünde mi? Kaybeden işlemleri oku.
4. Ancak o zaman gerçek parayı düşün: kaybedebileceğin bir tutarla, sonra elinle kur.

## 16. Sorunlar ve çözümler

| Sorun | Çözüm |
|---|---|
| Hiç almıyor | Ana sayfada **İşlem yapıyor mu?** kartını aç. Çoğunlukla: gerçek para kurulu değil, STOP açık, "Sadece fikir", piyasa kapalı, nakit yok |
| Alpaca anahtarları reddediyor | Paper anahtarı `PK`, canlı `AK` ile başlar. Tekrar kopyala ya da yeni çift oluştur |
| "Piyasa kapalı" | ABD hisseleri hafta içi New York saatiyle 9:30–16:00 arası işlem görür (Türkiye saatiyle genelde 16:30–23:00), tatiller hariç |
| Yapay zekâ sessiz | Ücretsiz anahtarların hız sınırı var. Bir dakika bekle ya da ikinci bir sağlayıcı ekle |
| Pencere gri ya da yavaş | Kendini yeniler. İki çökmeden sonra sonraki açılış ekran kartı olmadan çizer |
| Bilgisayar sıcak ya da gürültülü | Modlar → Hız → Eko |
| Kayıtlar | `%LOCALAPPDATA%\BofStudios\Money Tree AI\logs` (anahtarlar silinir) |

## 17. Kaynaktan derleme

```bash
pip install -r requirements.txt
python -m app.main                 # çalıştır
python -m pytest -q tests          # testler
python scripts/build_exe.py --personal   # dist/ içinde exe
```

Kaynaktan çalıştırınca veri klasörü deponun kendisidir. Başka klasör için `MONEYTREE_HOME` ayarla.
