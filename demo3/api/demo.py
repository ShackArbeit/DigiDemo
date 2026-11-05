"""
⚠️ 僅供展示的 API（正式系統不應存在）

- POST /demo/reset          重建資料庫、時鐘歸零（錄影可以反覆重來）
- POST /demo/advance-clock  時鐘快轉 N 天（情境 4「過期」不用真的等）
- POST /demo/tamper         直接竄改某筆日誌（情境 5 示範竄改會被偵測）
"""

import sqlite3
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from demo3.api.audit import tamper_log_for_demo
from demo3.api.deps import get_db, iso, now, settings
from demo3.db import init_db

router = APIRouter(prefix="/demo", tags=["⚠️ 僅供展示"])


class AdvanceClock(BaseModel):
    days: int = Field(ge=1, le=3650, examples=[31])


class Tamper(BaseModel):
    log_id: int = Field(examples=[4])
    field: str = Field(examples=["result"])
    value: str = Field(examples=["allowed"])


@router.post("/reset")
def reset():
    settings.clock_offset = timedelta(0)
    init_db(settings.db_path)
    return {"message": "資料庫已重建，時鐘已歸零", "now": iso(now())}


@router.post("/advance-clock")
def advance_clock(body: AdvanceClock):
    settings.clock_offset += timedelta(days=body.days)
    return {"message": f"時鐘快轉 {body.days} 天", "now": iso(now())}


@router.post("/tamper")
def tamper(body: Tamper, conn: sqlite3.Connection = Depends(get_db)):
    if conn.execute("SELECT 1 FROM audit_log WHERE log_id = ?", (body.log_id,)).fetchone() is None:
        raise HTTPException(404, "找不到這筆日誌")
    try:
        tamper_log_for_demo(conn, body.log_id, body.field, body.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"message": f"已竄改第 {body.log_id} 筆的 {body.field}"}
