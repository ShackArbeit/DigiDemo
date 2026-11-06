"""
Demo 3 API 測試：CLAUDE.md 列出的 5 個展示情境 + 其他安全檢查
"""

from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from demo3.api.deps import settings
from demo3.api.main import app
from demo3.db import init_db

# 銀行辦房貸需要的欄位（不含「登記原因」「地號」「登記日期」）
MORTGAGE_SCOPES = ["building_address", "ownership_share", "building_area_m2",
                   "announced_land_value", "mortgage"]
BANK = {"client_id": "bank-demo", "client_secret": "bank-demo-secret"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "api.db"))
    monkeypatch.setattr(settings, "clock_offset", timedelta(0))
    init_db(settings.db_path)
    with TestClient(app) as c:
        yield c


def create_consent(client, scopes=MORTGAGE_SCOPES, valid_days=30, citizen_id="C001"):
    r = client.post("/consents", json={
        "citizen_id": citizen_id, "client_id": "bank-demo",
        "purpose": "房屋貸款申請之擔保品審核", "scopes": scopes, "valid_days": valid_days,
    })
    assert r.status_code == 201, r.text
    return r.json()


def get_token(client, consent_id):
    r = client.post("/token", json={**BANK, "consent_id": consent_id})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def fetch(client, token, fields=None, citizen_id="C001"):
    params = {"fields": ",".join(fields)} if fields else {}
    return client.get(f"/provider/land-records/{citizen_id}", params=params,
                      headers={"Authorization": f"Bearer {token}"})


def last_log(client):
    return client.get("/citizens/C001/access-log").json()["entries"][-1]


# =============================================================================
# 情境 1：正常流程
# =============================================================================

def test_scenario1_normal_flow(client):
    consent = create_consent(client)
    assert consent["status"] == "active"
    token = get_token(client, consent["consent_id"])

    r = fetch(client, token, ["building_address", "ownership_share"])
    assert r.status_code == 200
    records = r.json()["records"]
    assert len(records) == 2                                      # 王小明有兩筆不動產
    assert all(set(rec) == {"building_address", "ownership_share"} for rec in records)

    log = last_log(client)
    assert (log["action"], log["result"]) == ("data.access", "allowed")
    assert log["client_name"] == "示範銀行（模擬）"
    assert log["purpose"] == "房屋貸款申請之擔保品審核"


def test_scenario1_without_fields_returns_only_authorized(client):
    token = get_token(client, create_consent(client)["consent_id"])
    records = fetch(client, token).json()["records"]
    assert set(records[0]) == set(MORTGAGE_SCOPES)
    assert "registration_reason" not in records[0]                # 未授權欄位一律不回傳


def test_token_contains_consent_and_scopes(client):
    consent = create_consent(client)
    claims = jwt.decode(get_token(client, consent["consent_id"]), options={"verify_signature": False})
    assert claims["consent_id"] == consent["consent_id"]
    assert claims["scopes"] == MORTGAGE_SCOPES
    assert "exp" in claims


# =============================================================================
# 情境 2：越權請求
# =============================================================================

def test_scenario2_overreach_denied_and_logged(client):
    token = get_token(client, create_consent(client)["consent_id"])
    r = fetch(client, token, ["building_address", "registration_reason"])
    assert r.status_code == 403
    assert "登記原因" in r.json()["detail"]

    log = last_log(client)
    assert (log["action"], log["result"]) == ("data.access", "denied")
    assert log["requested_fields"] == ["building_address", "registration_reason"]


# =============================================================================
# 情境 3：撤回授權
# =============================================================================

def test_scenario3_revoke_takes_effect_immediately(client):
    consent = create_consent(client)
    token = get_token(client, consent["consent_id"])
    assert fetch(client, token).status_code == 200

    r = client.post(f"/consents/{consent['consent_id']}/revoke", json={"citizen_id": "C001"})
    assert r.status_code == 200 and r.json()["status"] == "revoked"

    # 令牌本身還沒過期，但機關端重新查資料庫 → 立即拒絕
    r = fetch(client, token)
    assert r.status_code == 403
    assert "撤回" in r.json()["detail"]

    # 也無法再換新令牌
    r = client.post("/token", json={**BANK, "consent_id": consent["consent_id"]})
    assert r.status_code == 403


def test_only_owner_can_revoke(client):
    consent = create_consent(client)
    r = client.post(f"/consents/{consent['consent_id']}/revoke", json={"citizen_id": "C002"})
    assert r.status_code == 403


# =============================================================================
# 情境 4：過期
# =============================================================================

def test_scenario4_expired_consent_denied(client):
    consent = create_consent(client, valid_days=30)
    token = get_token(client, consent["consent_id"])

    client.post("/demo/advance-clock", json={"days": 31})        # 時鐘快轉 31 天
    r = fetch(client, token)
    assert r.status_code == 403
    assert "過期" in r.json()["detail"]

    r = client.post("/token", json={**BANK, "consent_id": consent["consent_id"]})
    assert r.status_code == 403
    assert "過期" in r.json()["detail"]


def test_short_lived_token_expires_before_consent(client):
    token = get_token(client, create_consent(client, valid_days=30)["consent_id"])
    client.post("/demo/advance-clock", json={"days": 1})         # 同意仍有效，但令牌（15 分鐘）已過期
    r = fetch(client, token)
    assert r.status_code == 401
    assert "令牌已過期" in r.json()["detail"]


# =============================================================================
# 情境 5：民眾查看存取紀錄 + 驗證日誌完整性
# =============================================================================

def test_scenario5_access_log_and_tamper_detection(client):
    consent = create_consent(client)
    token = get_token(client, consent["consent_id"])
    fetch(client, token, ["building_address"])                   # 成功
    fetch(client, token, ["registration_reason"])                # 越權
    client.post(f"/consents/{consent['consent_id']}/revoke", json={"citizen_id": "C001"})
    fetch(client, token)                                         # 撤回後被拒

    entries = client.get("/citizens/C001/access-log").json()["entries"]
    actions = [(e["action"], e["result"]) for e in entries]
    assert actions == [
        ("consent.create", "allowed"),
        ("token.issue", "allowed"),
        ("data.access", "allowed"),
        ("data.access", "denied"),
        ("consent.revoke", "allowed"),
        ("data.access", "denied"),
    ]

    assert client.get("/audit/verify").json()["valid"]

    # 有人想把「越權被拒」（第 4 筆）改成「允許」
    r = client.post("/demo/tamper", json={"log_id": 4, "field": "result", "value": "allowed"})
    assert r.status_code == 200
    result = client.get("/audit/verify").json()
    assert not result["valid"]
    assert result["position"] == 4


def test_viewing_log_is_itself_logged(client):
    client.get("/citizens/C001/access-log")
    entries = client.get("/citizens/C001/access-log").json()["entries"]
    assert entries[-1]["action"] == "log.view"


# =============================================================================
# 其他安全檢查
# =============================================================================

def test_wrong_client_secret_rejected(client):
    consent = create_consent(client)
    r = client.post("/token", json={"client_id": "bank-demo", "client_secret": "wrong",
                                    "consent_id": consent["consent_id"]})
    assert r.status_code == 401


def test_other_client_cannot_use_consent(client):
    consent = create_consent(client)
    r = client.post("/token", json={"client_id": "insurer-demo", "client_secret": "insurer-demo-secret",
                                    "consent_id": consent["consent_id"]})
    assert r.status_code == 403


def test_missing_or_forged_token_rejected(client):
    assert fetch(client, "").status_code == 401
    forged = jwt.encode({"sub": "bank-demo", "consent_id": "CNS-0001", "citizen_id": "C001",
                         "scopes": ["registration_reason"], "exp": 9999999999},
                        "attacker-guessed-secret-0123456789abcdef")
    assert fetch(client, forged).status_code == 401


def test_token_cannot_be_used_for_other_citizen(client):
    token = get_token(client, create_consent(client)["consent_id"])
    assert fetch(client, token, citizen_id="C002").status_code == 403


def test_invalid_scope_rejected_on_create(client):
    r = client.post("/consents", json={"citizen_id": "C001", "client_id": "bank-demo",
                                       "purpose": "x", "scopes": ["password"], "valid_days": 30})
    assert r.status_code == 422


def test_whole_chain_valid_after_all_scenarios(client):
    consent = create_consent(client)
    token = get_token(client, consent["consent_id"])
    fetch(client, token)
    fetch(client, token, ["registration_reason"])
    fetch(client, "bad-token")
    client.post(f"/consents/{consent['consent_id']}/revoke", json={"citizen_id": "C001"})
    assert client.get("/audit/verify").json() == {
        "valid": True, "checked": 6, "position": None, "log_id": None, "reason": "日誌完整，未發現竄改"}


def test_demo_reset(client):
    create_consent(client)
    client.post("/demo/advance-clock", json={"days": 10})
    client.post("/demo/reset")
    assert client.get("/citizens/C001/access-log").json()["entries"] == []
    assert settings.clock_offset == timedelta(0)


def test_audit_logs_is_read_only_and_shows_chain(client):
    create_consent(client)
    first = client.get("/audit/logs").json()["entries"]
    second = client.get("/audit/logs").json()["entries"]
    assert len(first) == len(second) == 1                      # 查看不會新增紀錄
    assert first[0]["prev_hash"] == "0" * 64 and len(first[0]["hash"]) == 64


def test_normal_flow_still_works_after_clock_advance(client):
    """回歸測試：情境 4 快轉時鐘後，不重設就再跑情境 1，仍要成功。
    （曾因 pyjwt 用電腦真實時間檢查 iat，誤判令牌「尚未生效」而回 401。）"""
    client.post("/demo/advance-clock", json={"days": 31})
    token = get_token(client, create_consent(client)["consent_id"])
    r = fetch(client, token, ["building_address"])
    assert r.status_code == 200, r.json()


def test_token_error_messages_are_specific(client):
    token = get_token(client, create_consent(client)["consent_id"])
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}AAAA"            # 改掉簽章
    assert "簽章錯誤" in fetch(client, tampered).json()["detail"]
    assert "格式不符" in fetch(client, "not-a-jwt").json()["detail"]
