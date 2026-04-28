def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_meta_exposes_non_sensitive_runtime_flags(client):
    resp = client.get("/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert "llm_mock_mode" in body
    assert "ollama_base_url" in body
    assert "ollama_model" in body
    assert "database_dialect" in body
