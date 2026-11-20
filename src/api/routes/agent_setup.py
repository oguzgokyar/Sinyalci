"""HTTP endpoints for Termux phone agent installation, script distribution, and one-liner setup."""

from __future__ import annotations

import pathlib
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/agent", tags=["agent-setup"])

AGENT_FILE_PATH = pathlib.Path(__file__).resolve().parents[3] / "agent" / "phone_agent.py"


@router.get("/phone_agent.py")
async def get_agent_script():
    """Download the latest phone_agent.py script."""
    if not AGENT_FILE_PATH.exists():
        raise HTTPException(status_code=404, detail="phone_agent.py bulunamadı.")
    return FileResponse(
        str(AGENT_FILE_PATH),
        media_type="text/x-python",
        filename="phone_agent.py",
    )


@router.get("/install.sh")
async def get_install_script(
    request: Request,
    device: str = "galaxy_a11",
    model: str = "Galaxy-A11",
):
    """Dynamic bash script for one-liner Termux setup.
    
    Usage:
        curl -sSL https://YOUR_DOMAIN/api/agent/install.sh | bash
    """
    db = request.app.state.db
    token = db.get_setting("agent_token", "")
    vps_url = db.get_setting("vps_public_url", "").strip()

    # Determine base HTTP and WS urls
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    
    if vps_url:
        # User defined an explicit VPS public URL in settings
        clean_vps = vps_url.rstrip("/")
        ws_scheme = "wss" if clean_vps.startswith("https") or clean_vps.startswith("wss") else "ws"
        clean_vps_host = clean_vps.replace("https://", "").replace("http://", "").replace("wss://", "").replace("ws://", "")
        ws_url = f"{ws_scheme}://{clean_vps_host}/ws/agent/{device}"
        http_url = f"{proto}://{clean_vps_host}"
    else:
        ws_scheme = "wss" if proto == "https" else "ws"
        ws_url = f"{ws_scheme}://{host}/ws/agent/{device}"
        http_url = f"{proto}://{host}"

    script = f"""#!/usr/bin/env bash
# ==============================================================================
# Sinyalci 4.5G Android Telefon Ajanı — Otomatik Kurulum ve Başlatıcı
# Cihaz: {device} ({model})
# ==============================================================================
set -e

BOLD='\\033[1m'
GREEN='\\033[0;32m'
CYAN='\\033[0;36m'
YELLOW='\\033[1;33m'
RED='\\033[0;31m'
NC='\\033[0m'

echo -e "${{BOLD}}${{CYAN}}======================================================${{NC}}"
echo -e "${{BOLD}}${{CYAN}}       🚀 Sinyalci 4.5G Telefon Ajanı Kurulumu       ${{NC}}"
echo -e "${{BOLD}}${{CYAN}}======================================================${{NC}}"

# 1. Termux Wake-Lock (Arka planda uyumayı engeller)
if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock
    echo -e "${{GREEN}}✓ Termux Wake-Lock aktif (Arka plan koruması devrede).${{NC}}"
fi

# 2. Gerekli sistem paketlerinin tespiti ve tam kütüphane uyumu
echo -e "\\n${{YELLOW}}[1/4] Paketler ve kütüphane uyumu güncelleniyor (pkg upgrade)...${{NC}}"
pkg update -y -q || true
pkg upgrade -y -q -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" || true

NEEDED_PKGS=()
for pkg in python android-tools curl; do
    if ! command -v "$pkg" >/dev/null 2>&1; then
        NEEDED_PKGS+=("$pkg")
    fi
done

if [ ${{#NEEDED_PKGS[@]}} -gt 0 ]; then
    echo -e "${{CYAN}}Eksik paketler kuruluyor: ${{NEEDED_PKGS[*]}} ...${{NC}}"
    pkg install -y "${{NEEDED_PKGS[@]}}"
fi
echo -e "${{GREEN}}✓ python, android-tools (ADB) ve curl hazır.${{NC}}"

# 3. Python websockets kütüphanesi
echo -e "\\n${{YELLOW}}[2/4] Python websockets kütüphanesi kontrol ediliyor...${{NC}}"
if ! python -c "import websockets" >/dev/null 2>&1; then
    echo -e "${{CYAN}}pip install websockets yapılıyor...${{NC}}"
    pip install --quiet websockets
fi
echo -e "${{GREEN}}✓ websockets kütüphanesi hazır.${{NC}}"

# 4. phone_agent.py dosyasını sunucudan çek
echo -e "\\n${{YELLOW}}[3/4] En güncel phone_agent.py sunucudan indiriliyor...${{NC}}"
AGENT_DIR="$HOME/sinyalci_agent"
mkdir -p "$AGENT_DIR"
cd "$AGENT_DIR"

curl -sSL "{http_url}/api/agent/phone_agent.py" -o phone_agent.py
chmod +x phone_agent.py
echo -e "${{GREEN}}✓ phone_agent.py güncellendi ($AGENT_DIR/phone_agent.py).${{NC}}"

# 5. Başlatıcı komut dosyasını oluştur (Tekrar başlatmayı kolaylaştırmak için)
cat << 'EOF' > start.sh
#!/usr/bin/env bash
cd "$HOME/sinyalci_agent"
if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock
fi
# Otomatik yerel ADB sunucusunu başlat ve 5555 portuna bağlan
adb start-server >/dev/null 2>&1 || true
adb connect 127.0.0.1:5555 >/dev/null 2>&1 || true

python phone_agent.py \\
    --server "{ws_url}" \\
    --token "{token}" \\
    --model "{model}" \\
    "$@"
EOF
chmod +x start.sh

# 6. ADB Loopback Bağlantı Kontrolü
echo -e "\\n${{YELLOW}}[4/4] Yerel ADB bağlantısı test ediliyor...${{NC}}"
adb start-server >/dev/null 2>&1 || true

ADB_DEVS=$(adb devices | grep -v "List of" | grep "device" || true)
if [ -z "$ADB_DEVS" ]; then
    echo -e "${{CYAN}}Yerel ADB aranıyor (127.0.0.1:5555)...${{NC}}"
    adb connect 127.0.0.1:5555 >/dev/null 2>&1 || true
    sleep 1
    ADB_DEVS=$(adb devices | grep -v "List of" | grep "device" || true)
fi

if [ -n "$ADB_DEVS" ]; then
    echo -e "${{GREEN}}✓ Yerel ADB cihazı algılandı:${{NC}}"
    echo "$ADB_DEVS"
else
    echo -e "${{YELLOW}}⚠️ Uyarı: Yerel ADB henüz bağlı değil.${{NC}}"
    echo -e "   Android Geliştirici Seçenekleri -> 'Kablosuz Hata Ayıklama' (Wireless Debugging) açın."
    echo -e "   Eğer port 5555 dışında ise: adb connect 127.0.0.1:PORT komutunu verin."
fi

echo -e "\\n${{BOLD}}${{GREEN}}======================================================${{NC}}"
echo -e "${{BOLD}}${{GREEN}}       ✨ Kurulum Tamamlandı! Ajan Başlatılıyor...    ${{NC}}"
echo -e "${{BOLD}}${{GREEN}}======================================================${{NC}}"
echo -e "${{CYAN}}İleride ajanı tekrar başlatmak için:${{NC}}"
echo -e "${{BOLD}}cd ~/sinyalci_agent && ./start.sh${{NC}}\\n"

# Ajanı doğrudan başlat
exec ./start.sh
"""
    return Response(content=script, media_type="text/plain; charset=utf-8")
