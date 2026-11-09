from fastapi.testclient import TestClient


def test_api_lists_workloads_and_queues_a_release(tmp_path, monkeypatch):
    import paved.api as api

    monkeypatch.setattr(api, "EVENTS", tmp_path / "e.sqlite")
    c = TestClient(api.app)
    assert c.get("/healthz").json() == {"ok": True}
    names = {w["name"] for w in c.get("/workloads").json()}
    assert {"pricing-conversion", "cs-email-agent", "damage-cost"} <= names
    r = c.post("/releases", json={"workload": "pricing-conversion", "commit": "abcdef1234567890"})
    assert r.status_code == 202 and r.json()["release"] == "pricing-conversion-abcdef123456"
    assert c.get(f"/releases/{r.json()['release']}").json()[0]["step"] == "requested"
    assert c.post("/releases", json={"workload": "nope", "commit": "x"}).status_code == 404
    assert c.get("/reports/secrets").status_code == 404
