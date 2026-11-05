# Demo 3：MyData 授權流程概念模擬

> ## ⚠️ 免責聲明
> - **這是「概念模擬」，不是 MyData 的真實規格、介面或實作方式。** 資料表、API、流程都是為了說明資料治理與隱私法遵原則而簡化設計的，與數位發展部 MyData 平台的實際運作無關。
> - **所有資料都是程式產生的合成資料**，不含任何真實個人資料。「王小明」、「示範銀行（模擬）」皆為虛構。合成的身分證字號仍可能碰巧與真人相同，因此資料庫檔案（`data/mydata.db`）不納入版本控制、不對外散布。
> - 本專案為面試展示用途，未經資安檢測，**不可用於正式環境**。

## 這是什麼

民眾（王小明）申請房貸時，授權銀行向地政機關取得自己的不動產資料。這個 demo 模擬三方之間的授權流程，展示五個法遵原則如何落實在系統設計中：

| 情境 | 展示內容 | 對應原則 |
|---|---|---|
| 1 正常流程 | 民眾同意 → 銀行換取令牌 → 取得授權欄位 | 告知後同意、特定目的 |
| 2 越權請求 | 銀行要求未授權的「登記原因」→ 403 拒絕並記錄 | 最小必要 |
| 3 撤回授權 | 民眾撤回 → 銀行用同一張令牌再次請求 → 立即失效 | 可撤回性 |
| 4 授權過期 | 效期 30 天，時間快轉 31 天 → 拒絕 | 期限限制 |
| 5 存取紀錄 | 民眾查看誰拿了資料；竄改一筆日誌 → 系統偵測出第幾筆 | 可問責性、當事人查詢權 |

核心機制：同意紀錄（consent）、JWT 授權令牌、機關端**每次存取都重新檢查同意狀態**、欄位最小化、hash chain 稽核日誌。

## 如何執行

需求：Python 3.11 以上，並已在專案根目錄安裝套件（`pip install -r requirements.txt`）。

**一鍵啟動**（在專案根目錄）：
```powershell
powershell -ExecutionPolicy Bypass -File demo3\run_demo3.ps1
```
- FastAPI 後端：http://localhost:8000（API 文件：http://localhost:8000/docs）
- Streamlit 介面：http://localhost:8501
- 按 `Ctrl + C` 關閉兩者。

**或分別啟動**（兩個終端機）：
```powershell
$env:MYDATA_JWT_SECRET = "請換成一串夠長的隨機字串"
.venv\Scripts\uvicorn.exe demo3.api.main:app --port 8000

.venv\Scripts\streamlit.exe run demo3/app.py
```

**重建資料庫**（回到初始狀態；介面上的「🔄 重設」按鈕效果相同）：
```powershell
.venv\Scripts\python.exe -m demo3.db
```

**執行測試**：
```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py tests/test_audit.py tests/test_api.py -q
```

## 檔案結構

```
demo3/
├── README.md
├── run_demo3.ps1        一鍵啟動腳本
├── db.py                SQLite 資料表：citizens、land_records、consents、audit_log
├── app.py               Streamlit 劇本式介面（三欄：民眾｜地政機關｜銀行）
└── api/
    ├── main.py          FastAPI 進入點
    ├── deps.py          共用設定：資料庫連線、JWT 密鑰、時鐘
    ├── consent.py       建立／撤回同意
    ├── tokens.py        簽發／驗證 JWT
    ├── provider.py      資料提供機關：五道檢查、只回傳授權欄位
    ├── audit.py         hash chain 核心邏輯
    ├── audit_routes.py  存取紀錄查詢、日誌完整性驗證
    └── demo.py          ⚠️ 僅供展示：重設、時鐘快轉、竄改日誌
```

詳細的設計說明與限制，見 `notes/demo3.md`。
