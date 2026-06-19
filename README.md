# LegoLingo

LegoLingo, Lego Boost ile etkileşimli olarak oynanabilen iki farklı eğitici/eğlenceli oyun içerir.

## Gereksinimler

Programı çalıştırmak için bilgisayarınızda **Python** yüklü olmalıdır (Python 3.8 veya üzeri önerilir).
Aşağıdaki Python kütüphanelerinin yüklü olması gerekir:

Komut satırını (Terminal veya PowerShell) açın ve şu komutu çalıştırarak gerekli kütüphaneleri yükleyin:
```bash
pip install pygame bleak numpy pylgbst
```

## Lego Hub Bağlantısı

Her iki program da otomatik olarak Lego Boost Hub'a bağlanmaya çalışır. 
- Hub'ın üzerindeki **yeşil düğmeye** basarak cihazı açtığınızdan (ışığın yanıp söndüğünden) emin olun.
- *Not:* Kod içerisinde Hub'ınızın MAC adresi `00:16:53:C1:B6:DD` olarak ayarlanmıştır. Farklı bir cihaza bağlanacaksanız `german_learning.py` veya `legomlingo.py` kodları içindeki `LEGO_MAC_ADRESI` değişkenini kendi cihazınızın MAC adresiyle güncellemeniz gerekebilir.

## Oyunları Çalıştırma

Terminal'de öncelikle bu klasöre geçiş yapmalısınız:
```bash
cd c:\Users\kirkg\Desktop\LegoLingo
```

Daha sonra oynamak istediğiniz oyunu çalıştırabilirsiniz:

### 1. Almanca Öğrenme Oyunu (German Learning)
Kiomi Robot eşliğinde Almanca kelimelerin artikellerini (Der, Die, Das) Lego renk sensörüne farklı renkler göstererek tahmin etmeye çalıştığınız oyundur.

Çalıştırmak için:
```bash
python german_learning.py
```

### 2. Lego Titanic Gitarı (Legomlingo)
Lego renk sensörüne kırmızı, mavi veya yeşil renkleri göstererek Titanic melodilerini (Verse, Chorus, Ending) çalabildiğiniz eğlenceli gitar oyunudur.

Çalıştırmak için:
```bash
python legomlingo.py
```

## Sorun Giderme
- Eğer `No module named ...` şeklinde bir hata alırsanız, yukarıdaki `pip install` komutuyla kütüphaneleri eksiksiz yüklediğinizden emin olun.
- Bluetooth bağlantısı sağlanamazsa Lego Hub'ın kapalı olmadığından ve bilgisayarınızın Bluetooth özelliğinin açık olduğundan emin olun.
- Bağlantı sırasında Windows Bluetooth cihazlarına erişim izni isterse izin verin.
