import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "chord_engine" in data


def test_health_fields_present():
    response = client.get("/health")
    data = response.json()
    required = {"status", "version", "app", "environment", "chord_engine", "whisper_model"}
    assert required.issubset(data.keys())
