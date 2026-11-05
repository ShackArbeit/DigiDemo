"""
稽核 API：民眾查詢自己的資料被誰存取、驗證日誌完整性

⚠️ 概念模擬，不是 MyData 的真實規格。
（hash chain 的核心邏輯在 audit.py；這裡只負責對外提供 API。）
"""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from demo3.api.audit import append_log, verify_chain
from demo3.api.deps import get_db, iso, now

router = APIRouter(tags=["稽核"])


@router.get("/citizens/{citizen_id}/access-log")
def access_log(citizen_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """民眾查詢：誰、在什麼時候、為了什麼目的，拿了（或想拿）我的哪些資料。"""
    if conn.execute("SELECT 1 FROM citizens WHERE citizen_id = ?", (citizen_id,)).fetchone() is None:
        raise HTTPException(404, "找不到這位民眾")

    rows = conn.execute("""
        SELECT a.log_id, a.timestamp, a.actor, a.action, a.consent_id, a.requested_fields,
               a.result, a.detail, c.client_name, c.purpose
        FROM audit_log a LEFT JOIN consents c ON a.consent_id = c.consent_id
        WHERE a.citizen_id = ?
        ORDER BY a.log_id
    """, (citizen_id,)).fetchall()

    entries = []
    for row in rows:
        entry = dict(row)
        entry["requested_fields"] = json.loads(entry["requested_fields"]) if entry["requested_fields"] else []
        entries.append(entry)

    # 查詢日誌本身也是一次存取，同樣要記錄（查詢後才寫入，所以下次查詢才看得到這筆）
    append_log(conn, f"citizen:{citizen_id}", "log.view", "allowed", citizen_id=citizen_id,
               detail="民眾查詢自己的存取紀錄", timestamp=iso(now()))
    return {"citizen_id": citizen_id, "entries": entries}


@router.get("/audit/logs")
def all_logs(conn: sqlite3.Connection = Depends(get_db)):
    """
    稽核單位檢視整條日誌（含 prev_hash / hash），用於展示 hash chain。
    概念模擬：正式環境應限制只有稽核人員可以呼叫。本 API 唯讀，不另外寫入日誌，
    以免展示畫面每重新整理一次就多一筆紀錄。
    """
    rows = conn.execute("SELECT * FROM audit_log ORDER BY log_id").fetchall()
    entries = []
    for row in rows:
        entry = dict(row)
        entry["requested_fields"] = json.loads(entry["requested_fields"]) if entry["requested_fields"] else []
        entries.append(entry)
    return {"entries": entries}


@router.get("/audit/verify")
def audit_verify(conn: sqlite3.Connection = Depends(get_db)):
    """驗證整條稽核日誌是否完整；若被竄改，回傳第幾筆出問題。"""
    return verify_chain(conn)
