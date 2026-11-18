"""GitHub live update checker and git pull updater."""

from __future__ import annotations

import pathlib
import re
import subprocess
from typing import Any, Callable, Optional
import urllib.request
import json

_GH_HTTPS_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", re.IGNORECASE)
_GH_SSH_RE = re.compile(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", re.IGNORECASE)


def parse_github_repo(url: str) -> tuple[str, str]:
    clean = url.strip()
    m = _GH_HTTPS_RE.match(clean) or _GH_SSH_RE.match(clean)
    if not m:
        raise ValueError(f"Geçerli bir GitHub depo adresi değil: {url!r}")
    return m.group(1), m.group(2)


def get_local_git_info(repo_dir: pathlib.Path, run_cmd: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    def _git(*args: str) -> str:
        res = run_cmd(
            ["git", *args],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.stdout.strip() if res.returncode == 0 else ""

    sha = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    msg = _git("log", "-1", "--pretty=%s")
    date = _git("log", "-1", "--pretty=%cI")
    remote = _git("remote", "get-url", "origin")
    return {
        "commit_sha": sha,
        "short_sha": sha[:7] if sha else "",
        "branch": branch or "master",
        "commit_message": msg,
        "commit_date": date,
        "remote_url": remote,
    }


def _default_http_get(url: str, headers: dict[str, str], timeout: int = 10) -> Any:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = resp.status
        body = resp.read().decode("utf-8", errors="replace")

        class _SimpleResp:
            status_code = status

            def json(self) -> Any:
                return json.loads(body)

        return _SimpleResp()


def check_github_updates(
    repo_url: str,
    branch: str = "master",
    repo_dir: pathlib.Path = pathlib.Path("."),
    github_token: str = "",
    local_sha_override: Optional[str] = None,
    http_get: Callable[..., Any] = _default_http_get,
) -> dict[str, Any]:
    owner, repo = parse_github_repo(repo_url)
    local_info = get_local_git_info(repo_dir) if local_sha_override is None else {"commit_sha": local_sha_override}
    local_sha = local_info.get("commit_sha", "")

    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "TREADER-Updater/0.1",
    }
    if github_token.strip():
        headers["Authorization"] = f"Bearer {github_token.strip()}"

    try:
        resp = http_get(api_url, headers=headers, timeout=10)
        if getattr(resp, "status_code", 500) != 200:
            return {
                "ok": False,
                "has_update": False,
                "error": f"GitHub API HTTP {getattr(resp, 'status_code', 'err')}",
                "local_sha": local_sha,
            }
        data = resp.json()
        remote_sha = data.get("sha", "")
        commit_obj = data.get("commit", {})
        remote_msg = (commit_obj.get("message") or "").splitlines()[0]
        remote_author = (commit_obj.get("author") or {}).get("name", "")
        remote_date = (commit_obj.get("author") or {}).get("date", "")
        has_update = bool(remote_sha and local_sha and remote_sha != local_sha)
        return {
            "ok": True,
            "has_update": has_update,
            "local_sha": local_sha,
            "local_short_sha": local_sha[:7],
            "remote_sha": remote_sha,
            "remote_short_sha": remote_sha[:7],
            "remote_message": remote_msg,
            "remote_author": remote_author,
            "remote_date": remote_date,
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "has_update": False,
            "local_sha": local_sha,
            "error": str(exc),
        }


def apply_github_update(
    repo_url: str,
    branch: str = "master",
    repo_dir: pathlib.Path = pathlib.Path("."),
    github_token: str = "",
    run_cmd: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    owner, repo = parse_github_repo(repo_url)

    def _run(cmd: list[str]) -> Any:
        return run_cmd(cmd, cwd=str(repo_dir), capture_output=True, text=True, timeout=60)

    prev = _run(["git", "rev-parse", "--short", "HEAD"])
    prev_sha = prev.stdout.strip() if prev.returncode == 0 else ""

    auth_url = (
        f"https://x-access-token:{github_token.strip()}@github.com/{owner}/{repo}.git"
        if github_token.strip()
        else f"https://github.com/{owner}/{repo}.git"
    )

    pull_res = _run(["git", "pull", "--ff-only", auth_url, branch])
    if pull_res.returncode != 0:
        safe_err = (pull_res.stderr or pull_res.stdout or "git pull failed").replace(
            github_token.strip(), "***"
        ) if github_token.strip() else (pull_res.stderr or pull_res.stdout)
        return {
            "updated": False,
            "previous_sha": prev_sha,
            "current_sha": prev_sha,
            "output": safe_err.strip(),
            "restart_required": False,
        }

    curr = _run(["git", "rev-parse", "--short", "HEAD"])
    curr_sha = curr.stdout.strip() if curr.returncode == 0 else prev_sha
    changed = bool(curr_sha and curr_sha != prev_sha)
    return {
        "updated": changed,
        "previous_sha": prev_sha,
        "current_sha": curr_sha,
        "output": (pull_res.stdout or "Already up to date.").strip(),
        "restart_required": changed,
    }
