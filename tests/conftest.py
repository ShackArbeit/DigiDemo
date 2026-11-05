import os

# 測試用的 JWT 密鑰（必須在 import demo3.api 之前設定）。正式密鑰絕不能寫在程式碼裡。
os.environ.setdefault("MYDATA_JWT_SECRET", "test-only-secret-not-for-production-0123456789")
