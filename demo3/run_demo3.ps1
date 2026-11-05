# Demo 3 一鍵啟動：FastAPI 後端（背景）+ Streamlit 介面
# 用法（在專案根目錄）：  powershell -ExecutionPolicy Bypass -File demo3\run_demo3.ps1
# 關閉：在這個視窗按 Ctrl + C，後端會一併關閉

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# JWT 密鑰：沒設定就產生一把臨時的（僅供 demo；正式環境請用金鑰管理服務）
if (-not $env:MYDATA_JWT_SECRET) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $env:MYDATA_JWT_SECRET = [Convert]::ToBase64String($bytes)
}

Write-Host "啟動 FastAPI 後端：http://localhost:8000  （API 文件：/docs）"
$api = Start-Process -FilePath ".\.venv\Scripts\uvicorn.exe" `
    -ArgumentList "demo3.api.main:app", "--port", "8000" -PassThru -NoNewWindow

try {
    Start-Sleep -Seconds 3
    Write-Host "啟動 Streamlit 介面：http://localhost:8501"
    & ".\.venv\Scripts\streamlit.exe" run demo3/app.py
}
finally {
    Write-Host "關閉 FastAPI 後端"
    Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
}
