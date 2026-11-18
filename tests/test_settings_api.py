import pytest
from httpx import ASGITransport, AsyncClient
from api.main import create_app


@pytest.mark.anyio
async def test_settings_environment_and_github_endpoints(tmp_path):
    app = create_app(db_path=tmp_path / "test.db")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_sys = await client.get("/api/system")
        assert r_sys.status_code == 200
        sys_data = r_sys.json()
        assert sys_data["env_mode"] in ("local", "vps")
        assert sys_data["connected_agents"] == 0

        r_env = await client.get("/api/system/environment")
        assert r_env.status_code == 200
        env_data = r_env.json()
        assert "checklist" in env_data
        assert len(env_data["checklist"]) >= 4
        assert len(env_data["agent_token"]) >= 20

        r_upd = await client.post(
            "/api/system/settings",
            json={
                "env_mode_override": "vps",
                "github_repo_url": "https://github.com/oguzhoca/treader",
                "github_branch": "main",
                "vps_public_url": "wss://vps.example.com",
            },
        )
        assert r_upd.status_code == 200
        assert r_upd.json()["state"]["env_mode"] == "vps"

        r_gh = await client.get("/api/system/github")
        assert r_gh.status_code == 200
        gh = r_gh.json()
        assert gh["repo_url"] == "https://github.com/oguzhoca/treader"
        assert gh["branch"] == "main"
        assert "local_git" in gh
