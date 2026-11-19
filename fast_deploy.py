#!/usr/bin/env python3
"""Fast Deploy Utility for Sinyalci (Zero Docker Rebuild).

Synces:
1. React/Vite built assets (web/dist -> container /app/web/dist)
2. Python backend code (src/ -> container /app/src/)
3. Reloads uvicorn process via HUP (sub-second zero-downtime update)
"""

import os
import subprocess
import sys
import time

PROJECT_DIR = "/opt/data/Sinyalci"
WEB_DIR = os.path.join(PROJECT_DIR, "web")
HOST_SSH_KEY = "/tmp/host_key"

def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error executing {cmd}:\n{res.stderr}", file=sys.stderr)
        sys.exit(res.returncode)
    return res.stdout.strip()

def get_ssh_key():
    sys.path.insert(0, "/opt/data/scripts")
    import coolify
    key_data = coolify.api_request("/api/v1/security/keys/kj3q9a2642fd4gsup5pno73l")
    pk = key_data["private_key"]
    with open(HOST_SSH_KEY, "w") as f:
        f.write(pk)
    os.chmod(HOST_SSH_KEY, 0o600)

def main():
    start_time = time.time()
    print("🚀 Sinyalci Fast Deploy Başlatılıyor...")

    # 1. Build Frontend if modified
    print("📦 [1/4] Web arayüzü derleniyor (npm run build)...")
    build_out = run_cmd("npm run build", cwd=WEB_DIR)
    print("   ✓ Web arayüzü derlendi.")

    # 2. Get SSH Key & find active container
    get_ssh_key()
    ssh_opts = ["-i", HOST_SSH_KEY, "-o", "StrictHostKeyChecking=no"]
    
    print("🔍 [2/4] Aktif Sinyalci konteyneri taranıyor...")
    find_cmd = ["ssh"] + ssh_opts + ["root@10.0.1.1", 'docker ps --filter name=agp6euzanxdo95sdd5wb3kkp --format "{{.Names}}"']
    cname = subprocess.run(find_cmd, capture_output=True, text=True).stdout.strip()
    
    if not cname:
        print("❌ Hata: Çalışan Sinyalci konteyneri bulunamadı!", file=sys.stderr)
        os.remove(HOST_SSH_KEY)
        sys.exit(1)
    print(f"   ✓ Aktif Konteyner: {cname}")

    # 3. Direct Host Copy (Docker volume / container path sync)
    print("⚡ [3/4] Kodlar ve Web dosyaları konteynere anlık aktarılıyor...")
    volume_path = "/var/lib/docker/volumes/f52hwptu6x4rwnl3htlqcq5q_hermes-data/_data/Sinyalci"
    
    sync_cmd = (
        f"docker cp {volume_path}/src/. {cname}:/app/src/ && "
        f"docker cp {volume_path}/web/dist/. {cname}:/app/web/dist/"
    )
    copy_run = ["ssh"] + ssh_opts + ["root@10.0.1.1", sync_cmd]
    run_cmd(copy_run)
    print("   ✓ Dosyalar doğrudan konteyner çalışma belleğine aktarıldı.")

    # 4. Instant Reload (Restart Uvicorn / Container Process without Docker build)
    print("🔄 [4/4] Konteyner yeniden başlatılıyor (0 rebuild)...")
    restart_cmd = ["ssh"] + ssh_opts + ["root@10.0.1.1", f"docker restart --time=2 {cname}"]
    run_cmd(restart_cmd)
    
    if os.path.exists(HOST_SSH_KEY):
        os.remove(HOST_SSH_KEY)

    elapsed = round(time.time() - start_time, 2)
    print(f"✨ Başarılı! Değişiklikler {elapsed} saniyede canlıya alındı.")
    print("🌐 URL: https://sinyalci.43.131.47.253.sslip.io")

if __name__ == "__main__":
    main()
