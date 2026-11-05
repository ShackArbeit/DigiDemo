"""
Demo 3 後端：MyData 授權流程概念模擬（FastAPI）

⚠️ 概念模擬，不是 MyData 的真實規格或介面。

啟動：.venv\\Scripts\\uvicorn.exe demo3.api.main:app --port 8000
API 文件：http://localhost:8000/docs
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from demo3.api import audit_routes, consent, demo, provider, tokens
from demo3.api.deps import settings
from demo3.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時：資料庫不存在就自動建立
    if not Path(settings.db_path).exists():
        init_db(settings.db_path)
    yield


app = FastAPI(
    title="MyData 授權流程概念模擬",
    description="⚠️ 這是「概念模擬」，不是 MyData 的真實規格或介面。所有資料皆為程式產生的合成資料。",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(consent.router)
app.include_router(tokens.router)
app.include_router(provider.router)
app.include_router(audit_routes.router)
app.include_router(demo.router)


@app.get("/", tags=["系統"])
def root():
    return {"name": "MyData 授權流程概念模擬", "notice": "概念模擬，非 MyData 真實規格", "docs": "/docs"}
