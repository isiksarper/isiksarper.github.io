# Bilek Küpü

Galaxy Watch Ultra'nın yön sensörüyle 3B bir hücre matrisinde (küp) gezinme prototipi.

```
[Saat: Wear OS uygulaması] --Wi-Fi/WebSocket--> [relay.js (bilgisayar)] --> [index.html (tarayıcı)]
```

## Parçalar

| Dosya | Ne yapar |
|---|---|
| `index.html` | 3B küp görselleştirici. Kaynaklar: Demo, Elle (kaydırıcı/klavye), Saat (WebSocket), Telefon (telefonun yön sensörü). |
| `relay.js` | Bağımlılığı olmayan Node WebSocket relay. Saatten gelen mesajı tarayıcıya iletir, `index.html`'i de sunar. |
| `wear/` | Wear OS uygulaması (Kotlin). Yön verisini ~50 Hz gönderir, bilekte çift darbe (çift alkış) algılayınca `wake` gönderir. |

## Çalıştırma

1. Bilgisayar ve saat **aynı Wi-Fi ağında** olmalı.
2. Relay'i başlat:
   ```
   node relay.js
   ```
   Ekrana `http://<ip>:8765` ve `ws://<ip>:8765/ws` adreslerini yazar.
3. Tarayıcıda `http://<ip>:8765` adresini aç ve **Saat** kaynağını seçip **Bağlan**'a bas.
4. `wear/` klasörünü Android Studio'da aç ve saate yükle (saatte Geliştirici seçenekleri → ADB hata ayıklama + Wi-Fi üzerinden hata ayıklama).
5. Saat uygulamasına `ws://<ip>:8765/ws` adresini yaz ve **Bağlan**'a bas.
6. Bileğini rahat bir pozisyonda tut ve **Sıfırla**'ya bas. Bu duruş küpün merkezi olur.

## Mesaj biçimi (saat → tarayıcı)

```json
{"t":"ori","q":[w,x,y,z]}     // Android rotation vector quaternion'u
{"t":"wake"}                  // çift darbe algılandı
{"t":"calibrate"}             // nötr duruşu sıfırla
{"t":"gesture","name":"..."}  // ileride eklenecek hareketler için
```

## Hareket modları

- **Yönelme → konum:** Bileği sağa/sola çevirmek X'i, öne/arkaya eğmek Y'yi, yana yatırmak Z'yi belirler. Açı aralığı (varsayılan ±45°) küpün kenarına denk gelir. Kayma (drift) olmaz, en kararlı mod budur.
- **Eğerek sür:** Bilek joystick gibi davranır. Eğim yönünde kayar, düz tutunca durur.

Konum ivmeölçerden çift integral alınarak hesaplanmıyor. Bu yöntem birkaç saniyede metrelerce kayar. Bu yüzden konum yönelmeden türetiliyor.

## Notlar

- `GAME_ROTATION_VECTOR` manyetometre kullanmaz. İç mekânda daha az titrer ama yaw zamanla biraz kayabilir; **Sıfırla** ile düzelir.
- Çift darbe eşiği `MainActivity.kt` içinde `HIT_THRESHOLD` (14 m/s²). Sert bilek hareketleri de tetikleyebilir. Bir sonraki adım mikrofonla doğrulamak.
- Wear OS projesi bu ortamda derlenmedi (Android SDK yok). Android Studio'da ilk senkronizasyonda Gradle wrapper oluşturulur.
