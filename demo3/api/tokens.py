"""
授權令牌（JWT）：第三方用 consent_id 換取令牌，之後憑令牌向資料提供機關取資料

⚠️ 概念模擬，不是 MyData 的真實規格。

令牌內容（payload）：
  sub         第三方代碼
  consent_id  依據哪一份同意
  citizen_id  資料主體
  scopes      可存取欄位
  iat / exp   簽發時間 / 到期時間
  jti         令牌編號
令牌用 HMAC-SHA256（HS256）簽章：內容任何人都看得到，但沒有密鑰就改不了、也偽造不了。
"""

import secrets
import sqlite3
from datetime import datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from demo3.api.audit import append_log
from demo3.api.consent import consent_problem, get_consent
from demo3.api.deps import CLIENTS, get_db, iso, now, settings

router = APIRouter(tags=["令牌"])

ALGORITHM = "HS256"


class TokenRequest(BaseModel):
    client_id: str = Field(examples=["bank-demo"])
    client_secret: str = Field(examples=["bank-demo-secret"])
    consent_id: str = Field(examples=["CNS-0001"])


def issue_token(consent: dict, issued: datetime) -> tuple[str, datetime]:
    """
    簽發令牌。到期時間取「15 分鐘後」與「同意到期時間」中較早的那個：
    令牌永遠不會比同意活得更久。
    """
    expires = min(issued + settings.token_ttl, datetime.fromisoformat(consent["expires_at"]))
    payload = {
        "sub": consent["client_id"],
        "consent_id": consent["consent_id"],
        "citizen_id": consent["citizen_id"],
        "scopes": consent["scopes"],
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), expires


def decode_token(token: str) -> dict:
    """
    驗證簽章並取出內容。簽章不對（被竄改或偽造）會丟出 jwt.InvalidTokenError。
    到期時間不在這裡由 pyjwt 檢查，而是由呼叫端用 deps.now() 檢查：
    這樣整個系統只有一個時鐘，情境 4 的「時間快轉」才會對令牌也生效。
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM],
                      options={"verify_exp": False, "require": ["exp", "consent_id", "scopes"]})


@router.post("/token")
def get_token(body: TokenRequest, conn: sqlite3.Connection = Depends(get_db)):
    """第三方憑「自己的身分」＋「民眾給的同意」換取令牌。"""
    timestamp = iso(now())
    client = CLIENTS.get(body.client_id)
    if client is None or not secrets.compare_digest(client["secret"], body.client_secret):
        append_log(conn, body.client_id, "token.issue", "denied", consent_id=None,
                   detail=f"第三方身分驗證失敗（consent_id={body.consent_id}）", timestamp=timestamp)
        raise HTTPException(401, "第三方身分驗證失敗")

    consent = get_consent(conn, body.consent_id)
    if consent is None:
        raise HTTPException(404, "找不到這份同意")

    def deny(status: int, reason: str):
        append_log(conn, body.client_id, "token.issue", "denied", citizen_id=consent["citizen_id"],
                   consent_id=consent["consent_id"], detail=reason, timestamp=timestamp)
        raise HTTPException(status, reason)

    if consent["client_id"] != body.client_id:
        deny(403, "這份同意不是授權給你的")
    problem = consent_problem(consent, now())
    if problem:
        deny(403, problem)

    token, expires = issue_token(consent, now())
    append_log(conn, body.client_id, "token.issue", "allowed", citizen_id=consent["citizen_id"],
               consent_id=consent["consent_id"], requested_fields=consent["scopes"],
               detail=f"令牌到期時間 {iso(expires)}", timestamp=timestamp)
    return {"access_token": token, "token_type": "bearer", "expires_at": iso(expires),
            "scopes": consent["scopes"]}
