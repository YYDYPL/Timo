"""Integration tests for LLM source configuration (settings page API)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from backend import db as backend_db

_TMP_DIR = tempfile.mkdtemp(prefix="timo_llm_")
_DB_FILE = os.path.join(_TMP_DIR, "llm.db")

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


@pytest.fixture()
def client():
    backend_db.DB_PATH = Path(_DB_FILE)
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(_DB_FILE + suffix)
        except FileNotFoundError:
            pass
    with TestClient(app) as test_client:
        yield test_client


def _payload(**overrides) -> dict:
    payload = {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "api_key": "sk-test-1234567890",
        "model": "deepseek-chat",
        "timeout": 60,
        "active": False,
    }
    payload.update(overrides)
    return payload


def test_empty_configs_report_env_source(client):
    data = client.get("/api/llm/configs").json()
    assert data["configs"] == []
    assert data["active_id"] is None
    assert data["source"] == "env"
    assert isinstance(data["is_configured"], bool)


def test_create_first_config_auto_activates(client):
    created = client.post("/api/llm/configs", json=_payload()).json()
    assert created["name"] == "DeepSeek"
    assert created["has_api_key"] is True
    assert "sk-test-1234567890" not in json.dumps(created, ensure_ascii=False)  # 不回传原始 Key
    data = client.get("/api/llm/configs").json()
    assert data["active_id"] == created["id"]
    assert data["source"] == "saved"


def test_second_config_not_auto_active_and_activate_switches(client):
    first = client.post("/api/llm/configs", json=_payload(name="A", api_key="sk-a")).json()
    second = client.post("/api/llm/configs", json=_payload(name="B", api_key="sk-b")).json()
    data = client.get("/api/llm/configs").json()
    assert data["active_id"] == first["id"]  # 第二条不自动激活

    resp = client.post(f"/api/llm/configs/{second['id']}/activate").json()
    assert resp["active_id"] == second["id"]
    assert resp["source"] == "saved"

    data = client.get("/api/llm/configs").json()
    assert data["active_id"] == second["id"]
    status = client.get("/api/ai/status").json()
    assert status["source"] == "saved"
    assert status["active_name"] == "B"


def test_update_keeps_api_key_when_omitted_or_blank(client):
    created = client.post("/api/llm/configs", json=_payload(api_key="sk-original")).json()
    # 只改名字
    updated = client.put(f"/api/llm/configs/{created['id']}", json={"name": "Renamed"}).json()
    assert updated["name"] == "Renamed"
    assert updated["has_api_key"] is True
    assert updated["api_key_masked"].endswith("inal")
    # 显式传空 api_key 也应保留原 Key
    updated = client.put(
        f"/api/llm/configs/{created['id']}",
        json={"name": "Renamed", "api_key": "", "base_url": "https://x.example/v1"},
    ).json()
    assert updated["has_api_key"] is True
    assert updated["api_key_masked"].endswith("inal")


def test_update_can_change_api_key(client):
    created = client.post("/api/llm/configs", json=_payload(api_key="sk-old")).json()
    updated = client.put(f"/api/llm/configs/{created['id']}", json={"api_key": "sk-new-9999"}).json()
    assert updated["api_key_masked"] == "sk-****9999"


def test_delete_active_config_falls_back_to_env(client):
    created = client.post("/api/llm/configs", json=_payload()).json()
    assert client.get("/api/llm/configs").json()["source"] == "saved"
    resp = client.delete(f"/api/llm/configs/{created['id']}")
    assert resp.status_code == 204
    data = client.get("/api/llm/configs").json()
    assert data["active_id"] is None
    assert data["source"] == "env"


def test_activate_env_deactivates_but_keeps_configs(client):
    created = client.post("/api/llm/configs", json=_payload()).json()
    resp = client.post("/api/llm/activate-env").json()
    assert resp["active_id"] is None
    assert resp["source"] == "env"
    data = client.get("/api/llm/configs").json()
    assert data["active_id"] is None
    assert [c["id"] for c in data["configs"]] == [created["id"]]  # 配置仍在，只是未激活


def test_requires_name(client):
    resp = client.post("/api/llm/configs", json=_payload(name="   "))
    assert resp.status_code == 422


def test_update_missing_config_returns_404(client):
    resp = client.put("/api/llm/configs/999", json={"name": "X"})
    assert resp.status_code == 404
