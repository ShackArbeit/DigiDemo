import pytest

from demo3.api.audit import (GENESIS_HASH, append_log, compute_hash, tamper_log_for_demo,
                             verify_chain)
from demo3.db import get_connection, init_db


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(init_db(tmp_path / "audit.db"))
    yield connection
    connection.close()


@pytest.fixture
def chain(conn):
    """建立 5 筆紀錄的日誌（模擬 Demo 3 情境）。"""
    entries = [
        ("citizen:C001", "consent.create", "allowed", None),
        ("bank-demo", "token.issue", "allowed", None),
        ("bank-demo", "data.access", "allowed", ["building_address", "ownership_share"]),
        ("bank-demo", "data.access", "denied", ["registration_reason"]),
        ("citizen:C001", "consent.revoke", "allowed", None),
    ]
    for i, (actor, action, result, fields) in enumerate(entries):
        append_log(conn, actor, action, result, citizen_id="C001", requested_fields=fields,
                   timestamp=f"2026-11-10T10:00:0{i}+08:00")
    return conn


# --- 建立鏈 -------------------------------------------------------------------

def test_first_record_links_to_genesis(conn):
    record = append_log(conn, "citizen:C001", "consent.create", "allowed")
    assert record["prev_hash"] == GENESIS_HASH
    assert len(record["hash"]) == 64


def test_each_record_links_to_previous(chain):
    rows = chain.execute("SELECT prev_hash, hash FROM audit_log ORDER BY log_id").fetchall()
    for prev, current in zip(rows, rows[1:]):
        assert current["prev_hash"] == prev["hash"]


def test_hash_is_deterministic_and_sensitive():
    record = {"log_id": 1, "actor": "bank-demo", "result": "denied"}
    assert compute_hash(GENESIS_HASH, record) == compute_hash(GENESIS_HASH, dict(record))
    # 只改一個字，hash 就完全不同
    assert compute_hash(GENESIS_HASH, record) != compute_hash(GENESIS_HASH, {**record, "result": "Denied"})


# --- 驗證 ---------------------------------------------------------------------

def test_empty_chain_is_valid(conn):
    assert verify_chain(conn)["valid"]


def test_intact_chain_is_valid(chain):
    result = verify_chain(chain)
    assert result["valid"]
    assert result["checked"] == 5


def test_tampered_middle_record_detected(chain):
    # 把第 4 筆「越權被拒」改成「允許」，想掩蓋越權紀錄
    tamper_log_for_demo(chain, 4, "result", "allowed")
    result = verify_chain(chain)
    assert not result["valid"]
    assert result["position"] == 4
    assert "內容" in result["reason"]


def test_tampering_with_recomputed_hash_still_detected(chain):
    # 聰明的攻擊者：改了第 3 筆，連第 3 筆的 hash 也重新算 → 第 4 筆的 prev_hash 對不上
    row = dict(chain.execute("SELECT * FROM audit_log WHERE log_id = 3").fetchone())
    row["requested_fields"] = '["building_address"]'
    new_hash = compute_hash(row["prev_hash"], row)
    chain.execute("UPDATE audit_log SET requested_fields = ?, hash = ? WHERE log_id = 3",
                  (row["requested_fields"], new_hash))
    result = verify_chain(chain)
    assert not result["valid"]
    assert result["position"] == 4
    assert "prev_hash" in result["reason"]


def test_deleted_record_detected(chain):
    chain.execute("DELETE FROM audit_log WHERE log_id = 2")
    result = verify_chain(chain)
    assert not result["valid"]
    assert result["log_id"] == 3          # 第 3 筆找不到它原本的「前一筆」


def test_new_records_after_verification_keep_chain_valid(chain):
    append_log(chain, "citizen:C001", "log.view", "allowed", citizen_id="C001")
    assert verify_chain(chain)["valid"]


def test_tamper_helper_rejects_unknown_field(chain):
    with pytest.raises(ValueError):
        tamper_log_for_demo(chain, 1, "hash", "x")
