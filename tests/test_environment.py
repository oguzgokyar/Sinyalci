from usb_trader.environment import detect_environment, build_checklist


def test_detect_environment_local_windows():
    info = detect_environment(env_override="auto", is_docker=False, os_name="Windows")
    assert info["mode"] == "local"
    assert info["is_docker"] is False


def test_detect_environment_vps_docker():
    info = detect_environment(env_override="auto", is_docker=True, os_name="Linux")
    assert info["mode"] == "vps"
    assert info["is_docker"] is True


def test_detect_environment_manual_override():
    info = detect_environment(env_override="vps", is_docker=False, os_name="Windows")
    assert info["mode"] == "vps"
    info2 = detect_environment(env_override="local", is_docker=True, os_name="Linux")
    assert info2["mode"] == "local"


def test_build_checklist_differs_between_local_and_vps():
    local_checks = build_checklist(
        mode="local",
        devices=[{"status": "ready"}],
        agent_count=0,
        agent_token="secret1234567890",
        kill_switch=False,
        dry_run=True,
    )
    vps_checks = build_checklist(
        mode="vps",
        devices=[],
        agent_count=1,
        agent_token="secret1234567890",
        kill_switch=False,
        dry_run=False,
    )
    local_keys = {c["key"] for c in local_checks}
    vps_keys = {c["key"] for c in vps_checks}
    assert "adb" in local_keys
    assert "remote_agents" in vps_keys
    assert any(c["key"] == "remote_agents" and c["ok"] is True for c in vps_checks)
