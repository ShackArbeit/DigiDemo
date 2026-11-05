"""
共用設定與相依物件：資料庫連線、JWT 密鑰、時鐘。

⚠️ 概念模擬，不是 MyData 的真實規格。
"""

import os
import secrets
import warnings
from datetime import datetime, timedelta

from demo3.api.audit import TW_TIMEZONE
from demo3.db import DB_PATH, get_connection


class Settings:
    def __init__(self):
        self.db_path = os.environ.get("MYDATA_DB_PATH", str(DB_PATH))

        # JWT 密鑰從環境變數讀取，絕不寫死在程式碼裡（程式碼會進版本控制）。
        # demo：沒設定時每次啟動隨機產生一把，重新啟動後舊的令牌全部失效。
        # 正式環境應該：
        #   1. 把密鑰放在金鑰管理服務（例如雲端 KMS、HashiCorp Vault、HSM），由系統啟動時注入
        #   2. 定期輪替密鑰，並保留舊密鑰一段時間以驗證尚未過期的令牌
        #   3. 改用非對稱簽章（RS256 / ES256）：只有授權伺服器持有私鑰負責簽發，
        #      資料提供機關只拿公鑰驗證——機關就算被入侵，攻擊者也無法偽造令牌
        self.jwt_secret = os.environ.get("MYDATA_JWT_SECRET")
        if not self.jwt_secret:
            warnings.warn("未設定 MYDATA_JWT_SECRET，使用隨機產生的臨時密鑰（僅適用 demo）")
            self.jwt_secret = secrets.token_hex(32)

        # 令牌有效時間刻意很短：令牌被偷，能被濫用的時間也很短
        self.token_ttl = timedelta(minutes=15)

        # 展示用的時鐘偏移：讓情境 4「過期」不用真的等 30 天（見 demo.py）
        self.clock_offset = timedelta(0)


settings = Settings()


def now() -> datetime:
    """系統目前時間（臺灣時區）＋展示用的時鐘偏移。所有時間判斷都只用這個函式。"""
    return datetime.now(TW_TIMEZONE) + settings.clock_offset


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def get_db():
    """每個請求開一條資料庫連線，結束時關閉。"""
    conn = get_connection(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


# 已註冊的第三方（概念模擬：實務上第三方要先申請、審核、簽約才能介接）
CLIENTS = {
    "bank-demo": {"name": "示範銀行（模擬）", "secret": "bank-demo-secret"},
    "insurer-demo": {"name": "示範保險公司（模擬）", "secret": "insurer-demo-secret"},
}
