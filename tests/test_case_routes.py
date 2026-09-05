"""
API endpoint tests for Investigation Case Management (/cases).
Tests listing, filtering, detail retrieval, assigning, investigating,
escalating, and resolving cases through the REST API.
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from api.app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("RAZORBRAIN_API_KEY", raising=False)
    with TestClient(app) as c:
        yield c


def test_create_and_get_case(client):
    uid = uuid.uuid4().hex[:8]
    create_payload = {
        "transaction_id": f"txn_route_{uid}",
        "assessment_id": f"asmt_route_{uid}",
        "final_decision": "REVIEW",
        "decision_reason": "High velocity detected",
        "priority": "HIGH",
        "assigned_to": "analyst.sam",
        "decision_snapshot": {"decision": "REVIEW"},
        "risk_snapshot": {"fraud_probability": 0.22},
        "rule_snapshot": {"rules": ["SUSPICIOUS_VELOCITY"]},
    }
    res = client.post("/cases", json=create_payload)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["success"] is True
    case_data = body["case"]
    case_id = case_data["case_id"]
    assert case_data["status"] == "OPEN"
    assert case_data["priority"] == "MEDIUM"
    assert case_data["assigned_to"] == "analyst.sam"
    assert case_data["version"] == 1

    # Fetch detail
    get_res = client.get(f"/cases/{case_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["success"] is True
    assert detail["case"]["case_id"] == case_id
    assert len(detail["events"]) >= 1


def test_get_case_not_found(client):
    res = client.get("/cases/non_existent_case_id_xyz")
    assert res.status_code == 404
    err_body = res.json()
    err_msg = err_body.get("error", {}).get("message") or err_body.get("detail", "")
    assert "not found" in err_msg.lower()


def test_case_lifecycle_endpoints(client):
    uid = uuid.uuid4().hex[:8]
    # 1. Create case
    create_payload = {
        "transaction_id": f"txn_lifecycle_{uid}",
        "assessment_id": f"asmt_lifecycle_{uid}",
        "final_decision": "STEP_UP",
        "decision_reason": "Extreme high value",
        "priority": "CRITICAL",
    }
    c_res = client.post("/cases", json=create_payload)
    assert c_res.status_code == 201
    case_id = c_res.json()["case"]["case_id"]

    # 2. Investigate
    inv_res = client.post(
        f"/cases/{case_id}/investigate",
        json={"expected_version": 1, "notes": "Starting review", "actor": "analyst_a"},
    )
    assert inv_res.status_code == 200
    assert inv_res.json()["case"]["status"] == "INVESTIGATING"
    assert inv_res.json()["case"]["version"] == 2

    # 3. Escalate
    esc_res = client.post(
        f"/cases/{case_id}/escalate",
        json={"expected_version": 2, "escalation_reason": "High fraud risk", "actor": "analyst_a"},
    )
    assert esc_res.status_code == 200
    assert esc_res.json()["case"]["status"] == "ESCALATED"
    assert esc_res.json()["case"]["version"] == 3

    # 4. Concurrency conflict on stale version
    stale_res = client.post(
        f"/cases/{case_id}/resolve",
        json={"expected_version": 2, "resolution_type": "CONFIRMED_FRAUD"},
    )
    assert stale_res.status_code == 409
    stale_err = stale_res.json().get("error", {}).get("message") or stale_res.json().get("detail", "")
    assert "conflict" in stale_err.lower() or "version" in stale_err.lower()

    # 5. Resolve with valid version
    res_res = client.post(
        f"/cases/{case_id}/resolve",
        json={
            "expected_version": 3,
            "resolution_type": "CONFIRMED_FRAUD",
            "resolution_notes": "Fraud verified by issuer",
            "actor": "lead_b",
        },
    )
    assert res_res.status_code == 200
    assert res_res.json()["case"]["status"] == "RESOLVED"
    assert res_res.json()["case"]["resolution_type"] == "CONFIRMED_FRAUD"


def test_list_cases_endpoint(client):
    res = client.get("/cases?page=1&page_size=5")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "items" in data
    assert "pagination" in data
    assert "stats" in data
    assert isinstance(data["items"], list)
