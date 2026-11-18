# Sinyalci

Fiziksel Android cihazlar üzerinden resmi **MetaTrader 5** uygulaması aracılığıyla organik mobil işlem (`ORDER_REASON_MOBILE: 1`, `Magic: 0`) gerçekleştiren, **Lokal PC** ve **VPS Bulut (4.5G Ters Tünel)** destekli işlem yürütme paneli.

## Özellikler

- **Akıllı Ortam Tespiti:** Çalıştığı ortamı (`LOKAL (PC)` / `VPS (BULUT)`) otomatik algılar ve köprü sağlık kontrol listesi (Checklist) sunar.
- **Sıfır Yazılım İzi:** Root, emülatör veya Erişilebilirlik servisi gerektirmez. İşlemler telefonun kendi 4.5G SIM hattından broker sunucusuna çıkar.
- **Kapalı Çevrim Görsel Doğrulama:** OpenCV şablon eşleme + RapidOCR (ONNX) ile işlem öncesi lot büyüklüğü ve ekran durumu teyit edilir.
- **Humanizer:** Gaussian piksel sapması (`±10–18 px`), rastgele temas süresi (`75–150 ms`) ve kübik Bézier kaydırma eğrileri.
- **GitHub Hızlı Güncelleme:** Web panelindeki **Ayarlar** sayfasından tek tıkla sürüm kontrolü ve `git pull`.
- **Master Kill-Switch & Dry-Run:** Acil durdurma ve simülasyon modu.

## Kurulum (Lokal PC)

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -e ".[dev,ocr]"
cd web && npm install && npm run build && cd ..
.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## Kurulum (VPS / Docker)

```bash
git clone https://github.com/<KULLANICI>/<REPO>.git sinyalci
cd sinyalci
docker compose up -d --build
```

## 4.5G Telefon Ajanı (Termux)

```bash
pkg install python android-tools
pip install websockets
adb connect 127.0.0.1:5555
python phone_agent.py --server wss://<VPS_ADRESINIZ>/ws/agent/galaxy_a11 --token <AGENT_TOKEN>
```
