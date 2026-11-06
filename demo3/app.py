"""
Demo 3：MyData 授權流程概念模擬（Streamlit 劇本式介面）

⚠️ 概念模擬，不是 MyData 的真實規格或介面。

需要先啟動 FastAPI 後端（見 demo3/run_demo3.ps1）：
  .venv\\Scripts\\uvicorn.exe demo3.api.main:app --port 8000
  .venv\\Scripts\\streamlit.exe run demo3/app.py
"""

import base64
import json
import os
import sys
from pathlib import Path

# 讓 `streamlit run demo3/app.py` 也能 import 專案內的模組
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from demo3.db import LAND_FIELDS  # noqa: E402

# 用 127.0.0.1 而不是 localhost：Windows 上 localhost 會先嘗試 IPv6（::1），
# 但 uvicorn 只監聽 IPv4，每次連線都要白等約 2 秒才改用 IPv4
API_URL = os.environ.get("MYDATA_API_URL", "http://127.0.0.1:8000")
CITIZEN_ID = "C001"
CITIZEN_NAME = "王小明"
BANK = {"client_id": "bank-demo", "client_secret": "bank-demo-secret"}
BANK_NAME = "示範銀行（模擬）"
PURPOSE = "房屋貸款申請之擔保品審核"
VALID_DAYS = 30

# 王小明授權給銀行的欄位（房貸審核需要的 5 項；不含地號、登記日期、登記原因）
CONSENT_SCOPES = ["building_address", "ownership_share", "building_area_m2",
                  "announced_land_value", "mortgage"]
# 情境 1 銀行實際請求的欄位
NORMAL_FIELDS = ["building_address", "ownership_share", "building_area_m2", "announced_land_value"]
# 情境 2 銀行越權請求的欄位
OVERREACH_FIELDS = ["building_address", "registration_reason"]

PROVIDER_CHECKS = ["令牌簽章有效", "令牌屬於這位民眾", "同意仍有效（重新查資料庫）",
                   "令牌未過期", "欄位在授權範圍內"]

ACTION_NAMES = {
    "consent.create": "建立同意", "consent.revoke": "撤回同意", "token.issue": "核發令牌",
    "data.access": "存取資料", "log.view": "查詢紀錄",
}

SCENARIOS = {
    1: ("情境 1：正常流程", "民眾同意 → 銀行換取令牌 → 取得授權欄位",
        "告知後同意・特定目的：民眾清楚知道「給誰、做什麼用、給哪些欄位、給多久」"),
    2: ("情境 2：越權請求", "銀行要求「登記原因」——不在授權範圍內",
        "最小必要原則：只能取得特定目的所需的欄位，越權請求一律拒絕並留下紀錄"),
    3: ("情境 3：撤回授權", "民眾撤回同意 → 銀行用同一張令牌再次請求",
        "可撤回性：撤回即時生效——機關每次存取都重新檢查同意狀態"),
    4: ("情境 4：授權過期", "同意效期 30 天 → 時間快轉 31 天 → 銀行再次請求",
        "期限限制：特定目的的利用有期限，到期自動失效"),
    5: ("情境 5：存取紀錄與完整性", "民眾查看誰拿了資料 → 竄改一筆日誌 → 系統偵測",
        "可問責性・當事人查詢權：每次存取都留下無法竄改的紀錄"),
}

COLOR_GOOD = "#0ca30c"
COLOR_CRITICAL = "#d03b3b"

st.set_page_config(page_title="Demo 3｜MyData 授權流程概念模擬", layout="wide")

# 錄影用（1920x1080）：放大字體
st.markdown(f"""
<style>
html, body, [class*="css"], .stMarkdown p, .stMarkdown li {{ font-size: 19px; }}
h1 {{ font-size: 2.3rem !important; }}
h2 {{ font-size: 1.8rem !important; }}
h3 {{ font-size: 1.45rem !important; }}
section[data-testid="stSidebar"] .stButton button {{ width: 100%; text-align: left; }}
section[data-testid="stSidebar"] .stButton button p {{ font-size: 1.15rem; font-weight: 600; }}
.stButton button p {{ font-size: 1.15rem; }}
.notice {{ background: #fff4e5; border: 2px solid #eda100; color: #6b4600; font-weight: 700;
          font-size: 1.25rem; text-align: center; padding: 10px; border-radius: 8px; margin-bottom: 8px; }}
.role {{ font-size: 1.6rem; font-weight: 800; padding: 6px 0 10px 0; border-bottom: 3px solid #e1e0d9;
         margin-bottom: 12px; }}
.check {{ font-size: 1.15rem; line-height: 1.9; }}
.check .ok {{ color: {COLOR_GOOD}; font-weight: 700; }}
.check .ng {{ color: {COLOR_CRITICAL}; font-weight: 700; }}
.check .skip {{ color: #a9a89e; }}
.principle {{ font-size: 1.35rem; font-weight: 700; padding: 14px 20px; margin-top: 16px;
              border-left: 6px solid #2a78d6; background: #eef4fc; border-radius: 6px; }}
.scope-tag {{ display: inline-block; padding: 2px 10px; margin: 3px; border-radius: 12px;
              background: #e6f4e6; color: #0b5d0b; font-size: 1.0rem; }}
.scope-tag.no {{ background: #fde2e2; color: #8a1c1c; text-decoration: line-through; }}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 呼叫後端 API
# ---------------------------------------------------------------------------

@st.cache_resource
def http_client() -> httpx.Client:
    """
    整個介面共用一條 HTTP 連線（cache_resource：只建立一次，之後重複使用）。
    每次請求都建立新連線要花數百毫秒；重複使用同一條連線只要幾毫秒。
    """
    return httpx.Client(base_url=API_URL, timeout=10)


def api(method: str, path: str, **kwargs) -> tuple[int, dict]:
    r = http_client().request(method, path, **kwargs)
    try:
        body = r.json()
    except ValueError:
        body = {"detail": r.text}
    return r.status_code, body


def api_alive() -> bool:
    try:
        return api("GET", "/", timeout=2)[0] == 200
    except httpx.HTTPError:
        return False


def create_consent() -> dict:
    status, body = api("POST", "/consents", json={
        "citizen_id": CITIZEN_ID, "client_id": BANK["client_id"], "purpose": PURPOSE,
        "scopes": CONSENT_SCOPES, "valid_days": VALID_DAYS})
    assert status == 201, body
    return body


def request_token(consent_id: str) -> tuple[int, dict]:
    return api("POST", "/token", json={**BANK, "consent_id": consent_id})


def fetch(token: str, fields: list[str]) -> tuple[int, dict]:
    return api("GET", f"/provider/land-records/{CITIZEN_ID}", params={"fields": ",".join(fields)},
               headers={"Authorization": f"Bearer {token}"})


def latest_log() -> dict:
    return api("GET", "/audit/logs")[1]["entries"][-1]


def setup_consent_and_token() -> tuple[dict, str]:
    """建立同意並換取令牌，存到 session_state，供後續情境沿用。"""
    consent = create_consent()
    _, token_body = request_token(consent["consent_id"])
    st.session_state["consent"] = consent
    st.session_state["token"] = token_body["access_token"]
    st.session_state["token_expires"] = token_body["expires_at"]
    return consent, token_body["access_token"]


def ensure_active_session() -> tuple[dict, str, bool]:
    """確保有一份有效的同意與令牌；沒有就自動建立。回傳 (同意, 令牌, 是否為自動建立)。"""
    consent = st.session_state.get("consent")
    if consent and consent["status"] == "active" and st.session_state.get("token"):
        return consent, st.session_state["token"], False
    consent, token = setup_consent_and_token()
    return consent, token, True


# ---------------------------------------------------------------------------
# 畫面元件：每個角色的面板由一串「事件」組成，情境執行時產生、渲染時依序顯示
# ---------------------------------------------------------------------------

def zh(fields: list[str]) -> str:
    return "、".join(LAND_FIELDS.get(f, f) for f in fields)


def scope_tags(allowed: list[str], highlight_denied: list[str] = ()) -> str:
    tags = [f'<span class="scope-tag">✓ {LAND_FIELDS[f]}</span>' for f in allowed]
    tags += [f'<span class="scope-tag no">✗ {LAND_FIELDS[f]}</span>' for f in highlight_denied]
    return " ".join(tags)


def failed_check(detail: str) -> int:
    """依拒絕原因推斷是五道檢查中的第幾道失敗（0 起算）。"""
    if "令牌無效" in detail or "缺少授權令牌" in detail:
        return 0
    if "不是這位民眾" in detail:
        return 1
    if "撤回" in detail or "同意已過期" in detail or "找不到令牌對應" in detail:
        return 2
    if "令牌已過期" in detail:
        return 3
    return 4


def checks_html(failed_at: int | None) -> str:
    lines = []
    for i, label in enumerate(PROVIDER_CHECKS):
        if failed_at is None or i < failed_at:
            lines.append(f'<span class="ok">✓</span> {i + 1}. {label}')
        elif i == failed_at:
            lines.append(f'<span class="ng">✗ {i + 1}. {label}</span>')
        else:
            lines.append(f'<span class="skip">－ {i + 1}. {label}（未執行）</span>')
    return '<div class="check">' + "<br>".join(lines) + "</div>"


def decode_jwt_payload(token: str) -> dict:
    """只解碼內容給畫面顯示（不驗證簽章；驗證由機關端負責）。"""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def records_table(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records).rename(columns=LAND_FIELDS)


def provider_events(fields: list[str], status: int, body: dict, consent_id: str) -> list:
    """地政機關看到的畫面：收到的請求 → 五道檢查 → 回應 → 寫入日誌。"""
    log = latest_log()
    events = [("md", f"**收到請求**　來自：{BANK_NAME}<br>同意編號：`{consent_id}`<br>"
                     f"請求欄位：{zh(fields)}")]
    if status == 200:
        events.append(("html", checks_html(None)))
        not_returned = [f for f in LAND_FIELDS if f not in fields]
        events.append(("ok", f"✓ 回傳 {len(fields)} 個授權欄位；其餘 {len(not_returned)} 個欄位不讀取、不回傳"))
    else:
        events.append(("html", checks_html(failed_check(body["detail"]))))
        events.append(("deny", f"✗ 拒絕（{status}）：{body['detail']}"))
    events.append(("caption", f"已寫入稽核日誌 #{log['log_id']}（{ACTION_NAMES[log['action']]}／"
                              f"{log['result']}）hash：{log['hash'][:16]}…"))
    return events


# ---------------------------------------------------------------------------
# 五個情境
# ---------------------------------------------------------------------------

def scenario_1() -> dict:
    consent, token = setup_consent_and_token()
    payload = decode_jwt_payload(token)
    status, body = fetch(token, NORMAL_FIELDS)

    citizen = [
        ("md", f"**{CITIZEN_NAME}** 在銀行申請房貸，同意銀行向地政機關取得資料："),
        ("md", f"- 授權對象：**{consent['client_name']}**\n- 用途：**{consent['purpose']}**\n"
               f"- 效期：**{VALID_DAYS} 天**（至 {consent['expires_at'][:10]}）"),
        ("html", "可存取欄位：<br>" + scope_tags(consent["scopes"],
                                              [f for f in LAND_FIELDS if f not in consent["scopes"]])),
        ("ok", f"✓ 已同意（同意編號 {consent['consent_id']}）"),
    ]
    bank = [
        ("md", "**① 以同意編號換取授權令牌**"),
        ("ok", f"✓ 取得令牌（{st.session_state['token_expires'][11:16]} 到期，15 分鐘有效）"),
        ("json", {"consent_id": payload["consent_id"], "scopes": [LAND_FIELDS[s] for s in payload["scopes"]],
                  "exp": st.session_state["token_expires"]}),
        ("md", f"**② 向地政機關請求 {len(NORMAL_FIELDS)} 個欄位**"),
    ]
    if status == 200:
        bank += [("ok", f"✓ 取得 {len(body['records'])} 筆不動產資料"), ("table", records_table(body["records"]))]
    else:
        bank.append(("deny", f"✗ {status}：{body['detail']}"))
    return {"citizen": citizen, "provider": provider_events(NORMAL_FIELDS, status, body, consent["consent_id"]),
            "bank": bank}


def scenario_2() -> dict:
    consent, token, auto = ensure_active_session()
    status, body = fetch(token, OVERREACH_FIELDS)
    denied = [f for f in OVERREACH_FIELDS if f not in consent["scopes"]]

    citizen = [("md", f"{CITIZEN_NAME} 只授權了這 {len(consent['scopes'])} 個欄位："),
               ("html", scope_tags(consent["scopes"], denied)),
               ("md", f"「{zh(denied)}」會透露繼承、贈與、拍賣等家庭與財務狀況，**不在授權範圍內**。")]
    if auto:
        citizen.insert(0, ("caption", "（已自動先完成情境 1 的同意與令牌）"))
    bank = [("md", f"**向地政機關請求：** {zh(OVERREACH_FIELDS)}")]
    if status == 200:
        bank.append(("ok", "✓ 取得資料"))
    else:
        bank += [("deny", f"✗ 403 拒絕：{body['detail']}"),
                 ("md", "連已授權的「房屋地址」也拿不到——**整筆請求都被拒絕**，不會只回傳一部分。")]
    return {"citizen": citizen, "provider": provider_events(OVERREACH_FIELDS, status, body, consent["consent_id"]),
            "bank": bank}


def scenario_3() -> dict:
    consent, token, auto = ensure_active_session()
    status_r, revoked = api("POST", f"/consents/{consent['consent_id']}/revoke", json={"citizen_id": CITIZEN_ID})
    st.session_state["consent"] = revoked
    status, body = fetch(token, NORMAL_FIELDS)

    citizen = [("md", f"{CITIZEN_NAME} 房貸已核貸，不想再讓銀行存取資料："),
               ("ok", f"✓ 已撤回同意 {consent['consent_id']}（{revoked['revoked_at'][11:19]}）")]
    if auto:
        citizen.insert(0, ("caption", "（已自動先完成情境 1 的同意與令牌）"))
    bank = [("md", f"**用同一張令牌再次請求**（令牌 {st.session_state['token_expires'][11:16]} 才到期）")]
    if status == 200:
        bank.append(("ok", "✓ 取得資料"))
    else:
        bank += [("deny", f"✗ {status} 拒絕：{body['detail']}"),
                 ("md", "令牌還沒過期，但**已經無法使用**——撤回即時生效。")]
    return {"citizen": citizen, "provider": provider_events(NORMAL_FIELDS, status, body, consent["consent_id"]),
            "bank": bank}


def scenario_4() -> dict:
    consent, token = setup_consent_and_token()
    status_before, _ = fetch(token, NORMAL_FIELDS)
    _, clock = api("POST", "/demo/advance-clock", json={"days": VALID_DAYS + 1})
    status, body = fetch(token, NORMAL_FIELDS)
    token_status, token_body = request_token(consent["consent_id"])

    citizen = [("md", f"{CITIZEN_NAME} 重新授權銀行，效期 **{VALID_DAYS} 天**（至 {consent['expires_at'][:10]}）。"),
               ("md", f"⏩ **時間快轉 {VALID_DAYS + 1} 天**（展示用）→ 現在是 {clock['now'][:10]}"),
               ("md", "民眾**不需要做任何事**，授權到期自動失效。")]
    bank = [("md", "**第 1 天：請求資料**"),
            ("ok", "✓ 取得資料") if status_before == 200 else ("deny", "✗ 失敗"),
            ("md", f"**第 {VALID_DAYS + 1} 天：再次請求**")]
    bank.append(("deny", f"✗ {status} 拒絕：{body['detail']}") if status != 200 else ("ok", "✓ 取得資料"))
    bank += [("md", "**想重新換一張令牌**"),
             ("deny", f"✗ {token_status} 拒絕：{token_body['detail']}") if token_status != 200
             else ("ok", "✓ 取得令牌")]
    return {"citizen": citizen, "provider": provider_events(NORMAL_FIELDS, status, body, consent["consent_id"]),
            "bank": bank}


def scenario_5() -> dict:
    _, log = api("GET", f"/citizens/{CITIZEN_ID}/access-log")
    st.session_state["access_log"] = log["entries"]
    st.session_state.pop("verify_result", None)
    st.session_state.pop("tampered_id", None)
    return {"citizen": [], "provider": [], "bank": [
        ("md", "銀行**看不到**這些紀錄。"),
        ("md", "存取紀錄屬於**民眾**（查詢權）與**稽核單位**（監督），被記錄的一方不能修改。"),
    ]}


RUNNERS = {1: scenario_1, 2: scenario_2, 3: scenario_3, 4: scenario_4, 5: scenario_5}


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def render_events(events: list) -> None:
    for kind, content in events:
        if kind == "md":
            st.markdown(content, unsafe_allow_html=True)
        elif kind == "html":
            st.markdown(content, unsafe_allow_html=True)
        elif kind == "ok":
            st.success(content)
        elif kind == "deny":
            st.error(content)
        elif kind == "caption":
            st.caption(content)
        elif kind == "json":
            st.json(content, expanded=True)
        elif kind == "table":
            st.dataframe(content, hide_index=True, width="stretch")


def access_log_table(entries: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{
        "#": e["log_id"],
        "時間": e["timestamp"][5:16].replace("T", " "),
        "對象": e.get("client_name") or ("本人" if e["actor"].startswith("citizen:") else e["actor"]),
        "動作": ACTION_NAMES.get(e["action"], e["action"]),
        "欄位": zh(e["requested_fields"]) if e["action"] == "data.access" else "",
        "結果": "✓ 允許" if e["result"] == "allowed" else "✗ 拒絕",
    } for e in entries])


def style_result(df: pd.DataFrame, broken_id: int | None = None):
    def row_style(row):
        if broken_id is not None and row["#"] == broken_id:
            return ["background-color: #fde2e2; font-weight: 700"] * len(row)
        return [""] * len(row)

    def result_color(value):
        if "允許" in str(value) or value == "allowed":
            return f"color: {COLOR_GOOD}; font-weight: 700"
        if "拒絕" in str(value) or value == "denied":
            return f"color: {COLOR_CRITICAL}; font-weight: 700"
        return ""
    return df.style.apply(row_style, axis=1).map(result_color, subset=["結果"])


def render_scenario_5() -> None:
    entries = st.session_state.get("access_log", [])
    chain = api("GET", "/audit/logs")[1]["entries"]
    verify = st.session_state.get("verify_result")
    broken = verify["log_id"] if verify and not verify["valid"] else None

    c1, c2, c3 = st.columns([1.25, 1.25, 0.7])
    with c1:
        st.markdown('<div class="role">👤 民眾：我的資料被誰拿了？</div>', unsafe_allow_html=True)
        st.dataframe(style_result(access_log_table(entries)), hide_index=True, width="stretch",
                     height=38 * (len(entries) + 1) + 4)
    with c2:
        st.markdown('<div class="role">🏛️ 稽核日誌（hash chain）</div>', unsafe_allow_html=True)
        chain_df = pd.DataFrame([{
            "#": e["log_id"], "動作": ACTION_NAMES.get(e["action"], e["action"]), "結果": e["result"],
            "prev_hash": e["prev_hash"][:10] + "…", "hash": e["hash"][:10] + "…"} for e in chain])
        st.dataframe(style_result(chain_df, broken), hide_index=True, width="stretch",
                     height=38 * (len(chain) + 1) + 4)
        st.caption("每一筆的 prev_hash = 前一筆的 hash，串成一條鏈")
    with c3:
        st.markdown('<div class="role">🏦 銀行</div>', unsafe_allow_html=True)
        render_events(st.session_state["panels"]["bank"])

    st.subheader("驗證日誌完整性")
    denied = [e for e in chain if e["action"] == "data.access" and e["result"] == "denied"]
    default = denied[0]["log_id"] if denied else (chain[-1]["log_id"] if chain else None)
    if default is None:
        st.info("目前還沒有日誌，請先執行情境 1～4。")
        return

    by_id = {e["log_id"]: e for e in chain}
    # 預設值只在第一次（或原本的選擇已不在清單中，例如重設後）寫入 session_state，
    # 之後選單只讀取這個值、不再傳 index：竄改後選擇不會跳到下一筆「拒絕」，
    # 也不會出現「同時用預設值和 Session State 設定」的警告
    if st.session_state.get("tamper_target") not in by_id:
        st.session_state["tamper_target"] = default
    a, b, c = st.columns([1.3, 1, 1])
    with a:
        target = st.selectbox("要竄改的紀錄", list(by_id), key="tamper_target",
                              format_func=lambda i: f"#{i}　{ACTION_NAMES.get(by_id[i]['action'], '')}"
                                                    f"／{by_id[i]['result']}")
    with b:
        st.write("")
        if st.button("😈 竄改：把結果改成「允許」", width="stretch"):
            api("POST", "/demo/tamper", json={"log_id": target, "field": "result", "value": "allowed"})
            st.session_state["tampered_id"] = target
            st.session_state.pop("verify_result", None)
            st.rerun()
    with c:
        st.write("")
        if st.button("🔍 驗證完整性", type="primary", width="stretch"):
            st.session_state["verify_result"] = api("GET", "/audit/verify")[1]
            st.rerun()

    if st.session_state.get("tampered_id"):
        st.warning(f"有人直接修改了資料庫：第 {st.session_state['tampered_id']} 筆的結果被改成「允許」，"
                   "想掩蓋這筆紀錄。")
    if verify:
        if verify["valid"]:
            st.success(f"✓ 日誌完整：檢查 {verify['checked']} 筆，未發現竄改")
        else:
            st.error(f"⚠️ 偵測到竄改：第 {verify['position']} 筆紀錄（#{verify['log_id']}）——{verify['reason']}")


# ---------------------------------------------------------------------------
# 版面
# ---------------------------------------------------------------------------

st.markdown('<div class="notice">⚠️ 概念模擬：非 MyData 真實規格｜所有資料皆為程式產生的合成資料</div>',
            unsafe_allow_html=True)

alive = api_alive()

with st.sidebar:
    st.header("🎬 展示情境")
    for number, (title, _, _) in SCENARIOS.items():
        if st.button(title, key=f"run{number}", disabled=not alive):
            st.session_state["panels"] = RUNNERS[number]()
            st.session_state["scenario"] = number
    st.divider()
    if st.button("🔄 重設（重建資料庫）", disabled=not alive):
        api("POST", "/demo/reset")
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    st.caption(f"後端：{API_URL}　{'🟢 連線中' if alive else '🔴 未連線'}")

st.title("🔐 Demo 3｜MyData 授權流程概念模擬")

if not alive:
    st.error(f"無法連線到後端 {API_URL}。請先啟動 FastAPI：")
    st.code(".venv\\Scripts\\uvicorn.exe demo3.api.main:app --port 8000", language="powershell")
    st.stop()

scenario = st.session_state.get("scenario")
if scenario is None:
    st.markdown("### 三個角色")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="role">👤 民眾</div>{CITIZEN_NAME}：要申請房貸，決定授權哪些資料',
                unsafe_allow_html=True)
    c2.markdown('<div class="role">🏛️ 地政機關</div>資料提供機關：持有房屋地址、持分、公告現值等資料',
                unsafe_allow_html=True)
    c3.markdown(f'<div class="role">🏦 銀行（第三方）</div>{BANK_NAME}：取得民眾授權的資料以審核房貸',
                unsafe_allow_html=True)
    st.info("👈 從左側選擇情境開始")
    st.stop()

title, subtitle, principle = SCENARIOS[scenario]
st.header(title)
st.markdown(f"**{subtitle}**")

if scenario == 5:
    render_scenario_5()
else:
    panels = st.session_state["panels"]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="role">👤 民眾</div>', unsafe_allow_html=True)
        render_events(panels["citizen"])
    with c2:
        st.markdown('<div class="role">🏛️ 地政機關</div>', unsafe_allow_html=True)
        render_events(panels["provider"])
    with c3:
        st.markdown('<div class="role">🏦 銀行（第三方）</div>', unsafe_allow_html=True)
        render_events(panels["bank"])

st.markdown(f'<div class="principle">📜 {principle}</div>', unsafe_allow_html=True)
