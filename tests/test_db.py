import sqlite3

import pytest

from demo3.db import LAND_FIELDS, TABLES, get_connection, init_db
from shared.fake_data import generate_citizens, is_valid_tw_id


@pytest.fixture
def conn(tmp_path):
    path = init_db(tmp_path / "test.db")
    connection = get_connection(path)
    yield connection
    connection.close()


def count(conn, table, where="1=1", params=()):
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]


def test_four_tables_exist(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLES) <= names


def test_land_records_have_at_least_six_fields(conn):
    columns = [r["name"] for r in conn.execute("PRAGMA table_info(land_records)")]
    assert len(LAND_FIELDS) >= 6
    assert set(LAND_FIELDS) <= set(columns)


def test_audit_log_has_hash_chain_columns(conn):
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(audit_log)")}
    assert {"timestamp", "actor", "action", "consent_id", "requested_fields",
            "result", "prev_hash", "hash"} <= columns


def test_seeded_citizens(conn):
    assert count(conn, "citizens") == 21
    wang = conn.execute("SELECT * FROM citizens WHERE citizen_id = 'C001'").fetchone()
    assert wang["name"] == "王小明"
    assert wang["national_id"][1] == "1"          # 男性
    ids = [r["national_id"] for r in conn.execute("SELECT national_id FROM citizens")]
    assert all(is_valid_tw_id(i) for i in ids)


def test_protagonist_has_two_properties(conn):
    shares = [r["ownership_share"] for r in conn.execute(
        "SELECT ownership_share FROM land_records WHERE citizen_id = 'C001' ORDER BY record_id")]
    assert shares == ["1/1", "1/2"]


def test_consents_and_audit_start_empty(conn):
    assert count(conn, "consents") == 0
    assert count(conn, "audit_log") == 0


def test_foreign_key_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO land_records (citizen_id, land_number, building_address, "
                     "ownership_share, building_area_m2, announced_land_value, registration_date, "
                     "registration_reason, mortgage) VALUES ('C999', '', '', '', 0, 0, '', '', '')")


def test_consent_status_check(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO consents VALUES ('CNS-X', 'C001', 'bank', '銀行', '房貸', '[]', "
                     "'2026-11-10', '2026-12-10', 'paused', NULL)")


def test_init_db_resets_everything(tmp_path):
    path = tmp_path / "reset.db"
    init_db(path)
    with get_connection(path) as conn:
        conn.execute("INSERT INTO consents VALUES ('CNS-0001', 'C001', 'bank', '銀行', '房貸', '[]', "
                     "'2026-11-10', '2026-12-10', 'active', NULL)")
    conn.close()

    init_db(path)                                    # 重建
    conn = get_connection(path)
    assert count(conn, "consents") == 0
    assert count(conn, "citizens") == 21
    conn.close()


def test_generate_citizens_reproducible():
    assert generate_citizens(seed=5) == generate_citizens(seed=5)
