"""Smart environment detection (LOCAL PC vs VPS Cloud) and health checklist."""

from __future__ import annotations

import os
import pathlib
import platform
import sys
from typing import Any, Literal


def is_running_in_docker() -> bool:
    if pathlib.Path("/.dockerenv").exists():
        return True
    cgroup = pathlib.Path("/proc/1/cgroup")
    if cgroup.exists():
        try:
            return "docker" in cgroup.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    return False


def detect_environment(
    env_override: str = "auto",
    is_docker: bool | None = None,
    os_name: str | None = None,
) -> dict[str, Any]:
    effective_docker = is_running_in_docker() if is_docker is None else is_docker
    current_os = platform.system() if os_name is None else os_name

    override = env_override.strip().lower()
    if override in ("local", "vps"):
        mode: Literal["local", "vps"] = override  # type: ignore
    elif effective_docker or os.getenv("TRADER_ENV", "").lower() == "vps":
        mode = "vps"
    elif current_os == "Windows":
        mode = "local"
    else:
        mode = "vps"

    return {
        "mode": mode,
        "is_docker": effective_docker,
        "os": current_os,
        "python_version": sys.version.split()[0],
        "hostname": platform.node(),
    }


def build_checklist(
    mode: str,
    devices: list[dict[str, Any]],
    agent_count: int = 0,
    agent_token: str = "",
    kill_switch: bool = False,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # 1. OCR Availability
    try:
        import rapidocr_onnxruntime  # noqa: F401

        checks.append({
            "key": "ocr",
            "title": "RapidOCR Motoru",
            "ok": True,
            "message": "ONNX OCR modeli yüklü ve kullanıma hazır.",
        })
    except ImportError:
        checks.append({
            "key": "ocr",
            "title": "RapidOCR Motoru",
            "ok": False,
            "message": "RapidOCR kurulu değil; ekrandan lot okuma devre dışı.",
        })

    # 2. MT5 Coordinate Profile
    prof_path = pathlib.Path("profiles/galaxy_a11_mt5.json")
    if prof_path.exists():
        checks.append({
            "key": "profile",
            "title": "MT5 Koordinat Profili",
            "ok": True,
            "message": "Galaxy A11 kalibrasyon profili mevcut ve geçerli.",
        })
    else:
        checks.append({
            "key": "profile",
            "title": "MT5 Koordinat Profili",
            "ok": False,
            "message": "profiles/galaxy_a11_mt5.json dosyası bulunamadı.",
        })

    # 3. Environment-specific checks
    if mode == "local":
        ready_devs = [d for d in devices if d.get("status") == "ready"]
        checks.append({
            "key": "adb",
            "title": "Fiziksel Cihaz Köprüsü",
            "ok": len(ready_devs) > 0,
            "message": (
                f"{len(ready_devs)} hazır cihaz bağlı."
                if ready_devs
                else "Bağlı hazır cihaz yok (Type-C ve USB Debugging kontrol edin)."
            ),
        })
    else:  # vps
        checks.append({
            "key": "remote_agents",
            "title": "4.5G Telefon Ajanları (WebSocket)",
            "ok": agent_count > 0,
            "message": (
                f"{agent_count} telefon ajanı sunucuya bağlı."
                if agent_count > 0
                else "Bağlı telefon ajanı yok. Telefonda phone_agent.py başlatılmalıdır."
            ),
        })
        token_ok = len(agent_token.strip()) >= 16
        checks.append({
            "key": "agent_auth",
            "title": "Ajan Güvenlik Anahtarı",
            "ok": token_ok,
            "message": (
                "Güçlü güvenlik token'ı tanımlı."
                if token_ok
                else "Güvenlik token'ı çok kısa veya tanımlanmamış (en az 16 karakter önerilir)."
            ),
        })

    # 4. Master Kill-Switch
    checks.append({
        "key": "kill_switch",
        "title": "Master Devre Kesici (Kill-Switch)",
        "ok": not kill_switch,
        "message": (
            "Sistem aktif (Devre kesici serbest)."
            if not kill_switch
            else "DEVRE KESİCİ KİLİTLİ! Yeni emir gönderilemez."
        ),
    })

    # 5. Dry-Run Flag
    checks.append({
        "key": "dry_run",
        "title": "Çalışma Modu",
        "ok": True,
        "message": (
            "DRY-RUN (Simülasyon): Emirlere fiziksel dokunulmaz."
            if dry_run
            else "CANLI İCRA: Emirler fiziksel olarak telefona gönderilir."
        ),
    })

    return checks
