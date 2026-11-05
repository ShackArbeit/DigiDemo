"""
稽核日誌：hash chain（雜湊鏈）

⚠️ 概念模擬，不是 MyData 的真實規格。

原理：每一筆紀錄的 hash = SHA-256(前一筆的 hash + 本筆內容)
→ 每一筆都「蓋上」前一筆的指紋，串成一條鏈。
→ 任何一筆被修改，它的 hash 就對不上；就算連 hash 一起改，下一筆的 prev_hash 也會對不上。
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

GENESIS_HASH = "0" * 64          # 第一筆紀錄的 prev_hash（鏈的起點）
TW_TIMEZONE = timezone(timedelta(hours=8))

# 參與 hash 計算的欄位（順序固定）。prev_hash 另外串接在最前面，hash 本身當然不算
HASHED_FIELDS = ["log_id", "timestamp", "actor", "action", "citizen_id", "consent_id",
                 "requested_fields", "result", "detail"]


def now_iso() -> str:
    """目前時間（臺灣時區），ISO 格式到秒。"""
    return datetime.now(TW_TIMEZONE).isoformat(timespec="seconds")


def compute_hash(prev_hash: str, record: dict) -> str:
    """
    hash = SHA-256(prev_hash + 本筆內容)
    本筆內容先轉成「固定格式」的 JSON（欄位順序固定、中文不轉碼），
    確保同樣的內容永遠算出同樣的 hash。
    """
    content = json.dumps({f: record.get(f) for f in HASHED_FIELDS},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + content).encode("utf-8")).hexdigest()


def append_log(conn: sqlite3.Connection, actor: str, action: str, result: str,
               citizen_id: str | None = None, consent_id: str | None = None,
               requested_fields: list[str] | None = None, detail: str | None = None,
               timestamp: str | None = None) -> dict:
    """
    新增一筆稽核紀錄，並接到鏈的尾端。回傳寫入的紀錄（含 hash）。
    日誌只能「新增」，本模組不提供修改或刪除的函式。
    """
    last = conn.execute("SELECT log_id, hash FROM audit_log ORDER BY log_id DESC LIMIT 1").fetchone()
    prev_hash = last["hash"] if last else GENESIS_HASH
    next_id = (last["log_id"] + 1) if last else 1

    record = {
        "log_id": next_id,
        "timestamp": timestamp or now_iso(),
        "actor": actor,
        "action": action,
        "citizen_id": citizen_id,
        "consent_id": consent_id,
        # 存成 JSON 文字；計算 hash 時也用同一份文字，避免格式差異
        "requested_fields": json.dumps(requested_fields, ensure_ascii=False)
                            if requested_fields is not None else None,
        "result": result,
        "detail": detail,
    }
    record["prev_hash"] = prev_hash
    record["hash"] = compute_hash(prev_hash, record)

    columns = HASHED_FIELDS + ["prev_hash", "hash"]
    conn.execute(f"INSERT INTO audit_log ({', '.join(columns)}) "
                 f"VALUES ({', '.join(':' + c for c in columns)})", record)
    conn.commit()
    return record


def verify_chain(conn: sqlite3.Connection) -> dict:
    """
    從第一筆開始逐筆檢查：
      1. prev_hash 是否等於前一筆的 hash（偵測刪除、插入、重排、連 hash 一起改）
      2. 重新計算的 hash 是否等於儲存的 hash（偵測內容被修改）
    回傳：
      valid      是否完整
      checked    檢查了幾筆
      position   第幾筆出問題（從 1 開始；完整則為 None）
      log_id     出問題那筆的 log_id
      reason     原因說明
    """
    rows = conn.execute("SELECT * FROM audit_log ORDER BY log_id").fetchall()
    expected_prev = GENESIS_HASH
    for position, row in enumerate(rows, start=1):
        record = dict(row)
        if record["prev_hash"] != expected_prev:
            return {"valid": False, "checked": position, "position": position,
                    "log_id": record["log_id"],
                    "reason": "prev_hash 與前一筆的 hash 不一致（前一筆被修改、刪除，或順序被調動）"}
        if compute_hash(record["prev_hash"], record) != record["hash"]:
            return {"valid": False, "checked": position, "position": position,
                    "log_id": record["log_id"],
                    "reason": "內容與 hash 不符（本筆內容被修改）"}
        expected_prev = record["hash"]
    return {"valid": True, "checked": len(rows), "position": None, "log_id": None,
            "reason": "日誌完整，未發現竄改"}


def tamper_log_for_demo(conn: sqlite3.Connection, log_id: int, field: str, value) -> None:
    """
    ⚠️ 僅供展示：模擬「有人直接改了資料庫」——繞過 append_log，直接修改某筆內容，
    用來示範 verify_chain 能偵測出竄改。正式系統不應存在這種函式。
    """
    if field not in HASHED_FIELDS or field == "log_id":
        raise ValueError(f"不能竄改欄位 {field}")
    conn.execute(f"UPDATE audit_log SET {field} = ? WHERE log_id = ?", (value, log_id))
    conn.commit()
