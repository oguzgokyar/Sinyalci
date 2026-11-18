from pathlib import Path
from unittest.mock import MagicMock
import pytest
from usb_trader.updater import parse_github_repo, check_github_updates, apply_github_update


def test_parse_github_repo_variants():
    assert parse_github_repo("https://github.com/oguzhoca/treader") == ("oguzhoca", "treader")
    assert parse_github_repo("https://github.com/oguzhoca/treader.git") == ("oguzhoca", "treader")
    assert parse_github_repo("git@github.com:oguzhoca/treader.git") == ("oguzhoca", "treader")


def test_parse_github_repo_rejects_non_github():
    with pytest.raises(ValueError):
        parse_github_repo("https://example.com/foo/bar")


def test_check_github_updates_detects_new_commit():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "sha": "abcdef1234567890abcdef1234567890abcdef12",
        "commit": {
            "message": "feat: add new UI button\nextra line",
            "author": {"name": "OguzHoca", "date": "2026-11-18T19:00:00Z"},
        },
    }

    res = check_github_updates(
        repo_url="https://github.com/oguzhoca/treader",
        branch="master",
        repo_dir=Path("."),
        local_sha_override="1111111111111111111111111111111111111111",
        http_get=lambda *a, **kw: fake_resp,
    )
    assert res["has_update"] is True
    assert res["remote_short_sha"] == "abcdef1"
    assert res["remote_message"] == "feat: add new UI button"


def test_apply_github_update_runs_fetch_and_pull():
    calls = []

    def fake_run(cmd, cwd=None, **kw):
        calls.append(cmd)
        if "rev-parse" in cmd:
            sha = "1111111" if len(calls) == 1 else "2222222"
            return MagicMock(returncode=0, stdout=sha + "\n", stderr="")
        return MagicMock(returncode=0, stdout="Updating 1111111..2222222\nFast-forward\n", stderr="")

    res = apply_github_update(
        repo_url="https://github.com/oguzhoca/treader",
        branch="master",
        repo_dir=Path("."),
        run_cmd=fake_run,
    )
    assert res["updated"] is True
    assert res["previous_sha"] == "1111111"
    assert res["current_sha"] == "2222222"
    assert any("pull" in c for c in calls)
