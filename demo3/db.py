"""
Demo 3 資料層：SQLite（單檔，免安裝）

⚠️ 概念模擬：本資料庫結構為面試展示用，不是 MyData 的真實規格或介面。

四張表：
- citizens      民眾
- land_records  地政機關持有的資料（資料提供機關）
- consents      同意紀錄：誰、授權給誰、用途、可存取欄位（scopes）、效期、狀態
- audit_log     稽核日誌：每次操作都記錄，prev_hash / hash 形成 hash chain（3-B 實作）

重建資料庫：.venv\\Scripts\\python.exe -m demo3.db
"""

import sqlite3
from pathlib import Path

from shared.fake_data import DATA_DIR, generate_citizens

DB_PATH = DATA_DIR / "mydata.db"

# 地政資料中「可被授權」的欄位（= scopes 的可選值），以及介面顯示用的中文名稱
LAND_FIELDS = {
    "land_number": "地號",
    "building_address": "房屋地址",
    "ownership_share": "權利範圍（持分）",
    "building_area_m2": "建物面積（㎡）",
    "announced_land_value": "公告土地現值（元/㎡）",
    "registration_date": "登記日期",
    "registration_reason": "登記原因",
    "mortgage": "他項權利（抵押權）",
}

SCHEMA = """
CREATE TABLE citizens (
    citizen_id   TEXT PRIMARY KEY,          -- 系統內部編號（不直接用身分證字號當主鍵）
    national_id  TEXT NOT NULL UNIQUE,      -- 身分證字號
    name         TEXT NOT NULL,
    gender       TEXT NOT NULL,
    birthday     TEXT NOT NULL,             -- ISO 日期 YYYY-MM-DD
    phone        TEXT NOT NULL
);

CREATE TABLE land_records (
    record_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    citizen_id            TEXT NOT NULL REFERENCES citizens(citizen_id),
    land_number           TEXT NOT NULL,    -- 地號
    building_address      TEXT NOT NULL,    -- 房屋地址
    ownership_share       TEXT NOT NULL,    -- 權利範圍（持分），例如 1/2
    building_area_m2      REAL NOT NULL,    -- 建物面積
    announced_land_value  INTEGER NOT NULL, -- 公告土地現值（元/平方公尺）
    registration_date     TEXT NOT NULL,    -- 登記日期
    registration_reason   TEXT NOT NULL,    -- 登記原因：買賣、繼承、贈與、拍賣
    mortgage              TEXT NOT NULL     -- 他項權利（抵押權設定）
);

CREATE TABLE consents (
    consent_id   TEXT PRIMARY KEY,          -- 例如 CNS-0001
    citizen_id   TEXT NOT NULL REFERENCES citizens(citizen_id),  -- 誰同意
    client_id    TEXT NOT NULL,             -- 授權給誰（第三方代碼）
    client_name  TEXT NOT NULL,             -- 第三方名稱（顯示用）
    purpose      TEXT NOT NULL,             -- 用途（特定目的）
    scopes       TEXT NOT NULL,             -- 可存取欄位，JSON 陣列，例如 ["building_address"]
    created_at   TEXT NOT NULL,             -- ISO 時間
    expires_at   TEXT NOT NULL,             -- 到期時間
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'revoked')),
    revoked_at   TEXT                       -- 撤回時間（未撤回為 NULL）
);

CREATE TABLE audit_log (
    log_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT NOT NULL,        -- ISO 時間
    actor             TEXT NOT NULL,        -- 誰做的：例如 bank-demo、citizen:C001
    action            TEXT NOT NULL,        -- 做了什麼：consent.create、data.access……
    citizen_id        TEXT REFERENCES citizens(citizen_id),  -- 資料主體（讓民眾查詢自己的紀錄）
    consent_id        TEXT REFERENCES consents(consent_id),  -- 依據哪一份同意（可為空）
    requested_fields  TEXT,                 -- 請求的欄位，JSON 陣列
    result            TEXT NOT NULL,        -- allowed / denied
    detail            TEXT,                 -- 補充說明，例如拒絕原因
    prev_hash         TEXT NOT NULL,        -- 前一筆的 hash（第一筆為 64 個 0）
    hash              TEXT NOT NULL         -- 本筆的 hash = SHA-256(prev_hash + 本筆內容)
);

CREATE INDEX idx_land_citizen ON land_records(citizen_id);
CREATE INDEX idx_consent_citizen ON consents(citizen_id);
CREATE INDEX idx_audit_citizen ON audit_log(citizen_id);
"""

TABLES = ["citizens", "land_records", "consents", "audit_log"]


def get_connection(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """
    開啟連線：啟用外鍵檢查，查詢結果可以用欄位名稱取值（row["name"]）。
    check_same_thread=False：FastAPI 會在不同執行緒建立與使用連線；
    每個請求各自開一條連線、用完就關，所以這樣是安全的。
    """
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """先刪除舊表再重建（順序：先刪有外鍵參照的表）。"""
    for table in reversed(TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.executescript(SCHEMA)


def seed_data(conn: sqlite3.Connection, seed: int = 2026) -> None:
    """寫入假資料：王小明 + 20 位民眾，以及他們的地政資料。consents、audit_log 保持空白。"""
    citizens, land_records = generate_citizens(seed=seed)
    conn.executemany(
        "INSERT INTO citizens VALUES "
        "(:citizen_id, :national_id, :name, :gender, :birthday, :phone)", citizens)
    conn.executemany(
        f"INSERT INTO land_records (citizen_id, {', '.join(LAND_FIELDS)}) "
        f"VALUES (:citizen_id, {', '.join(':' + f for f in LAND_FIELDS)})", land_records)


def init_db(path: Path | str = DB_PATH, seed: int = 2026) -> Path:
    """重建資料庫：清空所有資料表並重新寫入假資料（錄影前、測試時使用）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(path) as conn:
        create_schema(conn)
        seed_data(conn, seed)
    conn.close()
    return path


if __name__ == "__main__":
    output = init_db()
    with get_connection(output) as conn:
        for table in TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table}: {count} 筆")
    conn.close()
    print(f"已重建 {output}")
