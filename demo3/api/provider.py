"""
資料提供機關（模擬地政機關）API

⚠️ 概念模擬，不是 MyData 的真實規格。

每一次請求都依序檢查：
  1. 令牌簽章是否有效（沒被竄改、不是偽造）
  2. 令牌是否屬於這位民眾
  3. 重新查資料庫：同意是否仍有效（未撤回、未過期）← 撤回才能「即時」生效
  4. 令牌是否過期
  5. 請求的欄位是否都在授權範圍內（最小必要）
全部通過才回傳資料，而且只回傳請求的授權欄位。不論成功或失敗都寫入稽核日誌。
"""

import json
import sqlite3
from datetime import datetime

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from demo3.api.audit import append_log
from demo3.api.consent import consent_problem, get_consent
from demo3.api.deps import get_db, iso, now
from demo3.api.tokens import decode_token
from demo3.db import LAND_FIELDS

router = APIRouter(prefix="/provider", tags=["資料提供機關"])


@router.get("/land-records/{citizen_id}")
def get_land_records(citizen_id: str,
                     fields: str | None = Query(None, description="以逗號分隔的欄位，不填則回傳全部授權欄位",
                                                examples=["building_address,ownership_share"]),
                     authorization: str | None = Header(None),
                     conn: sqlite3.Connection = Depends(get_db)):
    current = now()
    timestamp = iso(current)
    requested = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

    def deny(status: int, reason: str, actor: str = "unknown", consent_id: str | None = None):
        append_log(conn, actor, "data.access", "denied", citizen_id=citizen_id, consent_id=consent_id,
                   requested_fields=requested, detail=reason, timestamp=timestamp)
        raise HTTPException(status, reason)

    # 1. 驗證令牌簽章
    if not authorization or not authorization.lower().startswith("bearer "):
        deny(401, "缺少授權令牌")
    # 依實際原因回報，避免把所有錯誤都說成「簽章錯誤」而誤導排查
    try:
        claims = decode_token(authorization.split(" ", 1)[1])
    except jwt.InvalidSignatureError:
        deny(401, "授權令牌無效：簽章錯誤（令牌被竄改或偽造）")
    except jwt.DecodeError:
        deny(401, "授權令牌無效：格式不符")
    except jwt.InvalidTokenError as e:
        deny(401, f"授權令牌無效：{e}")

    actor, consent_id = claims["sub"], claims["consent_id"]

    # 令牌的簽發時間不能在未來（用系統唯一的時鐘判斷；容許 60 秒誤差）
    if claims["iat"] > current.timestamp() + 60:
        deny(401, "授權令牌無效：簽發時間在未來", actor, consent_id)

    # 2. 令牌是否屬於這位民眾
    if claims.get("citizen_id") != citizen_id:
        deny(403, "令牌不是這位民眾授權的", actor, consent_id)

    # 3. 重新查資料庫確認同意狀態（不能只相信令牌：令牌簽發後，民眾可能已經撤回）
    consent = get_consent(conn, consent_id)
    if consent is None:
        deny(403, "找不到令牌對應的同意", actor, consent_id)
    problem = consent_problem(consent, current)
    if problem:
        deny(403, problem, actor, consent_id)

    # 4. 令牌是否過期
    if current >= datetime.fromtimestamp(claims["exp"], tz=current.tzinfo):
        deny(401, "授權令牌已過期，請重新申請", actor, consent_id)

    # 5. 欄位最小化：請求的欄位必須是授權範圍（以資料庫中的同意為準）的子集
    allowed = consent["scopes"]
    if requested is None:
        requested = allowed
    unknown = [f for f in requested if f not in LAND_FIELDS]
    if unknown:
        deny(400, f"沒有這些欄位：{', '.join(unknown)}", actor, consent_id)
    not_allowed = [f for f in requested if f not in allowed]
    if not_allowed:
        names = "、".join(LAND_FIELDS[f] for f in not_allowed)
        deny(403, f"請求未授權的欄位：{names}", actor, consent_id)

    # 通過：只查詢、只回傳請求的欄位（其他欄位連讀都不讀）
    columns = ", ".join(requested)        # 欄位名稱都已確認在 LAND_FIELDS 白名單中
    rows = conn.execute(f"SELECT {columns} FROM land_records WHERE citizen_id = ? ORDER BY record_id",
                        (citizen_id,)).fetchall()
    append_log(conn, actor, "data.access", "allowed", citizen_id=citizen_id, consent_id=consent_id,
               requested_fields=requested, detail=f"回傳 {len(rows)} 筆不動產資料", timestamp=timestamp)
    return {
        "citizen_id": citizen_id,
        "consent_id": consent_id,
        "purpose": consent["purpose"],
        "fields": requested,
        "records": [dict(r) for r in rows],
    }
