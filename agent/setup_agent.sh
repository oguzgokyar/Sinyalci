#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# Sinyalci (TREADER) — Galaxy A11 Termux Kurulum ve Baslatma Scripti
# ==============================================================================

set -e

SERVER_URL="${1:-https://sinyalci.43.131.47.253.sslip.io}"
TOKEN="${2:-ca10b060c4732f375531d205cf08f14397d36ede}"
DEVICE_ID="${3:-galaxy_a11}"
MODEL="${4:-Galaxy-A11}"

# WebSocket URL'ini hesapla (https -> wss, http -> ws)
WS_SERVER=$(echo "$SERVER_URL" | sed 's/^http:/ws:/' | sed 's/^https:/wss:/')

echo "======================================================"
echo "🚀 TREADER Galaxy A11 Ajan Kurulumu Baslatiliyor..."
echo "Sunucu: $SERVER_URL"
echo "Ajan ID: $DEVICE_ID"
echo "======================================================"

# 1. Termux WakeLock al (telefon kilitlense bile servis uyumasin)
if command -v termux-wake-lock &> /dev/null; then
    echo "⚡ WakeLock aliniyor (uyku engelleme)..."
    termux-wake-lock
fi

# 2. Paket guncelleme ve bagimliliklar
echo "📦 Temel paketler yukleniyor (python, android-tools, curl)..."
pkg update -y
pkg install -y python android-tools curl

# 3. Python kutuphaneleri
echo "📦 Python kutuphaneleri yukleniyor (websockets)..."
pip install --upgrade pip websockets

# 4. phone_agent.py indir / guncelle
echo "📥 phone_agent.py indiriliyor..."
curl -sSL "$SERVER_URL/agent/phone_agent.py" -o phone_agent.py || {
    echo "⚠️ Sunucudan indirilemedi, eger mevcut dosya varsa o kullanilacak."
}

# 5. Yerel ADB Baglantisi Testi
echo "🔍 Yerel ADB baglantisi kontrol ediliyor (127.0.0.1:5555)..."
adb connect 127.0.0.1:5555 || true
sleep 1
adb devices

# 6. Baslatma scripti olustur (start.sh)
cat << 'EOF' > start.sh
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock 2>/dev/null || true
adb connect 127.0.0.1:5555 2>/dev/null || true

WS_URL="wss://sinyalci.43.131.47.253.sslip.io/ws/agent/galaxy_a11"
TOKEN="ca10b060c4732f375531d205cf08f14397d36ede"

echo "================================================="
echo "⚡ Sinyalci Ajan Baslatiliyor..."
echo "Sunucu: $WS_URL"
echo "Durdurmak icin: CTRL+C"
echo "Arka plana atmak icin: nohup ./start.sh > agent.log 2>&1 &"
echo "================================================="

python phone_agent.py --server "$WS_URL" --token "$TOKEN" --model "Galaxy-A11"
EOF
chmod +x start.sh

echo "======================================================"
echo "✅ Kurulum tamamlandi!"
echo "Ajan simdi calistirilabilir:"
echo "  ./start.sh"
echo "veya arka planda calistirmak icin:"
echo "  nohup ./start.sh > agent.log 2>&1 &"
echo "======================================================"

# Baslat
./start.sh
