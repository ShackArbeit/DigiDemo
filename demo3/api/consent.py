"""
同意（Consent）API：民眾建立同意、撤回同意

⚠️ 概念模擬，不是 MyData 的真實規格。假設民眾已完成身分驗證（不在本 demo 範圍內）。
"""

import json
import sqlite3
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from demo3.api.audit import append_log
from demo3.api.deps import CLIENTS, get_db, iso, now
from demo3.db import LAND_FIELDS

router = APIRouter(tags=["同意"])


class ConsentCreate(BaseModel):
    citizen_id: str = Field(examples=["C001"])
    client_id: str = Field(examples=["bank-demo"])
    purpose: str = Field(min_length=1, examples=["房屋貸款申請之擔保品審核"])
    scopes: list[str] = Field(min_length=1, examples=[["building_address", "ownership_share"]])
    valid_days: int = Field(ge=1, le=365, examples=[30])

    @field_validator("scopes")
    @classmethod
    def scopes_must_be_land_fields(cls, scopes: list[str]) -> list[str]:
        unknown = set(scopes) - set(LAND_FIELDS)
        if unknown:
            raise ValueError(f"未知的欄位：{sorted(unknown)}")
        return list(dict.fromkeys(scopes))   # 去除重複、保留順序


class ConsentRevoke(BaseModel):
    citizen_id: str = Field(examples=["C001"])


def get_consent(conn: sqlite3.Connection, consent_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM consents WHERE consent_id = ?", (consent_id,)).fetchone()
    if row is None:
        return None
    consent = dict(row)
    consent["scopes"] = json.loads(consent["scopes"])
    return consent


def consent_problem(consent: dict, at: datetime) -> str | None:
    """
    檢查同意目前是否有效。有問題回傳原因，有效回傳 None。
    「過期」不存成狀態，而是每次都拿到期時間和現在比較 → 不會有「過期了但狀態沒更新」的空窗。
    """
    if consent["status"] == "revoked":
        return f"同意已撤回（撤回時間 {consent['revoked_at']}）"
    if at >= datetime.fromisoformat(consent["expires_at"]):
        return f"同意已過期（到期時間 {consent['expires_at']}）"
    return None


def _next_consent_id(conn: sqlite3.Connection) -> str:
    count = conn.execute("SELECT COUNT(*) FROM consents").fetchone()[0]
    return f"CNS-{count + 1:04d}"


@router.post("/consents", status_code=201)
def create_consent(body: ConsentCreate, conn: sqlite3.Connection = Depends(get_db)):
    """民眾同意：授權某個第三方，為了某個用途，在某段期間內取得指定欄位。"""
    actor = f"citizen:{body.citizen_id}"
    if conn.execute("SELECT 1 FROM citizens WHERE citizen_id = ?", (body.citizen_id,)).fetchone() is None:
        raise HTTPException(404, "找不到這位民眾")
    if body.client_id not in CLIENTS:
        raise HTTPException(404, "找不到這個第三方服務")

    created = now()
    consent = {
        "consent_id": _next_consent_id(conn),
        "citizen_id": body.citizen_id,
        "client_id": body.client_id,
        "client_name": CLIENTS[body.client_id]["name"],
        "purpose": body.purpose,
        "scopes": json.dumps(body.scopes),
        "created_at": iso(created),
        "expires_at": iso(created + timedelta(days=body.valid_days)),
        "status": "active",
        "revoked_at": None,
    }
    conn.execute("INSERT INTO consents VALUES (:consent_id, :citizen_id, :client_id, :client_name, "
                 ":purpose, :scopes, :created_at, :expires_at, :status, :revoked_at)", consent)
    append_log(conn, actor, "consent.create", "allowed", citizen_id=body.citizen_id,
               consent_id=consent["consent_id"], requested_fields=body.scopes,
               detail=f"授權 {consent['client_name']}，用途：{body.purpose}，效期 {body.valid_days} 天",
               timestamp=consent["created_at"])
    return get_consent(conn, consent["consent_id"])


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(consent_id: str, body: ConsentRevoke, conn: sqlite3.Connection = Depends(get_db)):
    """民眾撤回同意：立即生效（機關端每次存取都會重新檢查同意狀態）。"""
    actor = f"citizen:{body.citizen_id}"
    consent = get_consent(conn, consent_id)
    if consent is None:
        raise HTTPException(404, "找不到這份同意")
    if consent["citizen_id"] != body.citizen_id:
        append_log(conn, actor, "consent.revoke", "denied", citizen_id=consent["citizen_id"],
                   consent_id=consent_id, detail="非本人的同意，不能撤回", timestamp=iso(now()))
        raise HTTPException(403, "只有本人可以撤回自己的同意")
    if consent["status"] == "revoked":
        raise HTTPException(409, "這份同意已經撤回")

    revoked_at = iso(now())
    conn.execute("UPDATE consents SET status = 'revoked', revoked_at = ? WHERE consent_id = ?",
                 (revoked_at, consent_id))
    append_log(conn, actor, "consent.revoke", "allowed", citizen_id=body.citizen_id,
               consent_id=consent_id, detail=f"撤回對 {consent['client_name']} 的授權",
               timestamp=revoked_at)
    return get_consent(conn, consent_id)
