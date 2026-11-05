"""
假資料產生器（所有 demo 共用）

⚠️ 本檔只產生「程式合成」的假資料，不含任何真實個人資料。
   合成的身分證字號仍可能碰巧與真人相同，因此輸出檔一律放在 data/（已排除於 git）。
"""

import random
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# ---------------------------------------------------------------------------
# 台灣身分證字號
# ---------------------------------------------------------------------------

# 英文字母 → 兩位數代碼（注意：I、O、W 等並非依字母順序排列，這是歷史因素）
LETTER_CODES = {
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14, "F": 15, "G": 16, "H": 17,
    "I": 34, "J": 18, "K": 19, "L": 20, "M": 21, "N": 22, "O": 35, "P": 23,
    "Q": 24, "R": 25, "S": 26, "T": 27, "U": 28, "V": 29, "W": 32, "X": 30,
    "Y": 31, "Z": 33,
}

# 9 個數字的權重：前 8 碼依序乘 8~1，最後一碼（檢查碼）乘 1
DIGIT_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 1, 1]

# 格式：1 個大寫英文字母 + 第 2 碼為 1 或 2 + 8 個數字
TW_ID_PATTERN = re.compile(r"^[A-Z][12]\d{8}$")


def _weighted_sum(letter: str, digits: str) -> int:
    """計算加權總和。digits 可以是 8 碼（尚無檢查碼）或 9 碼（完整號碼）。"""
    code = LETTER_CODES[letter]
    total = (code // 10) * 1 + (code % 10) * 9
    for digit, weight in zip(digits, DIGIT_WEIGHTS):
        total += int(digit) * weight
    return total


def is_valid_tw_id(id_number: str) -> bool:
    """驗證台灣身分證字號：先檢查格式，再檢查「加權總和 % 10 == 0」。"""
    if not isinstance(id_number, str) or not TW_ID_PATTERN.match(id_number):
        return False
    return _weighted_sum(id_number[0], id_number[1:]) % 10 == 0


def generate_tw_id(rng: random.Random, gender: str | None = None,
                   letter: str | None = None) -> str:
    """
    產生一個通過檢查碼驗證的假身分證字號。

    rng    : 傳入固定 seed 的 random.Random，確保每次結果相同（錄影可重現）
    gender : "M"（男，第 2 碼 = 1）、"F"（女，第 2 碼 = 2）；None 則隨機
    letter : 指定開頭字母（例如 "A"）；None 則隨機
    """
    if letter is None:
        letter = rng.choice(list(LETTER_CODES))
    if gender is None:
        gender = rng.choice(["M", "F"])
    gender_digit = "1" if gender == "M" else "2"

    # 第 2 碼（性別）+ 隨機 7 碼 = 前 8 碼
    first_eight = gender_digit + "".join(str(rng.randint(0, 9)) for _ in range(7))

    # 檢查碼權重為 1，所以要補上「讓總和變成 10 的倍數」的那個數字
    check_digit = (10 - _weighted_sum(letter, first_eight) % 10) % 10
    return letter + first_eight + str(check_digit)


# ---------------------------------------------------------------------------
# Demo 1：社福補助申請名冊
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 固定的「今天」，用來計算年齡；不用 date.today()，否則隔天重跑年齡會變
REFERENCE_DATE = date(2026, 11, 1)

CITY = "臺北市"

# 地址集中在 5 個區，且權重不平均 → 人少的區比較容易出現 k-匿名不足的小群組
DISTRICT_WEIGHTS = {"大安區": 30, "文山區": 25, "萬華區": 20, "中正區": 15, "信義區": 10}

# 各區的道路名稱（道路是公開地理資訊，不是個資）
DISTRICT_ROADS = {
    "大安區": ["復興南路一段", "和平東路二段", "敦化南路二段", "新生南路三段", "辛亥路二段"],
    "文山區": ["木柵路三段", "興隆路二段", "羅斯福路六段", "景興路", "萬芳路"],
    "萬華區": ["西園路一段", "康定路", "環河南路二段", "萬大路", "西藏路"],
    "中正區": ["重慶南路一段", "羅斯福路一段", "汀州路三段", "南昌路二段", "延平南路"],
    "信義區": ["松仁路", "基隆路一段", "忠孝東路五段", "吳興街", "永吉路"],
}

# 申請項目：(名稱, 申請人年齡範圍, 補助金額範圍)
SUBSIDY_ITEMS = [
    ("中低收入老人生活津貼", (65, 95), (4000, 8500)),
    ("身心障礙者生活補助", (18, 85), (3800, 9000)),
    ("低收入戶生活扶助", (20, 80), (6000, 15000)),
    ("育兒津貼", (22, 45), (5000, 7000)),
    ("急難救助", (20, 85), (5000, 30000)),
]


def _random_mobile(rng: random.Random, with_dash: bool = False) -> str:
    """手機：09 開頭共 10 碼；可選 0912-345-678 格式（測試偵測器能否處理不同寫法）。"""
    digits = "09" + "".join(str(rng.randint(0, 9)) for _ in range(8))
    if with_dash:
        return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
    return digits


def _random_landline(rng: random.Random) -> str:
    """臺北市話：(02)XXXX-XXXX。"""
    return f"(02){rng.randint(2000, 2999)}-{rng.randint(0, 9999):04d}"


def _random_birthday(rng: random.Random, min_age: int, max_age: int) -> date:
    """依年齡範圍產生生日（以 REFERENCE_DATE 為基準）。"""
    # 先取「剛好滿 age 歲」的那天，再往前推 0～364 天 → 在基準日時恰好 age 歲
    age = rng.randint(min_age, max_age)
    exact_birthday = REFERENCE_DATE.replace(year=REFERENCE_DATE.year - age)
    return exact_birthday - timedelta(days=rng.randint(0, 364))


def _random_address(rng: random.Random) -> tuple[str, str]:
    """回傳 (完整地址, 區)。"""
    district = rng.choices(list(DISTRICT_WEIGHTS), weights=DISTRICT_WEIGHTS.values())[0]
    road = rng.choice(DISTRICT_ROADS[district])
    address = f"{CITY}{district}{road}{rng.randint(1, 300)}號"
    if rng.random() < 0.7:
        address += f"{rng.randint(2, 15)}樓"
    return address, district


def _invalid_id_like(rng: random.Random) -> str:
    """產生「格式像身分證、但檢查碼錯誤」的字串，用來測試偵測器會不會誤判。"""
    valid = generate_tw_id(rng)
    wrong_check = (int(valid[-1]) + rng.randint(1, 9)) % 10
    return valid[:-1] + str(wrong_check)


def _random_note(rng: random.Random, fake: Faker) -> str:
    """
    備註欄（自由文字）。約 60% 空白，其餘混入不同類型的個資，
    讓偵測器必須在非結構化文字裡找出個資。
    """
    if rng.random() < 0.6:
        return ""
    templates = [
        lambda: f"聯絡家屬{fake.name()} {_random_mobile(rng)}",
        lambda: f"申請人白天不便接聽，請改撥家屬手機 {_random_mobile(rng, with_dash=True)}",
        lambda: f"申請人行動不便，請改撥市話 {_random_landline(rng)}",
        lambda: f"代理人{fake.name()}，身分證 {generate_tw_id(rng, letter='A')}",
        lambda: f"補件資料請寄 {fake.email()}",
        lambda: f"案件編號 {_invalid_id_like(rng)}，已轉社工追蹤",   # 干擾項：檢查碼錯誤
        lambda: "已電訪，資料齊全",                                  # 不含個資
        lambda: "需補附診斷證明",                                    # 不含個資
    ]
    return rng.choice(templates)()


def generate_applicants(n: int = 500, seed: int = 2026) -> pd.DataFrame:
    """產生 n 筆假的「社福補助申請名冊」。同一個 seed 一定得到同一份資料。"""
    rng = random.Random(seed)
    fake = Faker("zh_TW")
    fake.seed_instance(seed)

    rows = []
    used_ids = set()
    for _ in range(n):
        gender = rng.choice(["M", "F"])

        # 身分證字號：大多是臺北市（A），少數由外縣市遷入；確保不重複
        letter = "A" if rng.random() < 0.85 else rng.choice(list(LETTER_CODES))
        id_number = generate_tw_id(rng, gender=gender, letter=letter)
        while id_number in used_ids:
            id_number = generate_tw_id(rng, gender=gender, letter=letter)
        used_ids.add(id_number)

        item, (min_age, max_age), (min_amount, max_amount) = rng.choice(SUBSIDY_ITEMS)
        address, _district = _random_address(rng)

        rows.append({
            "姓名": fake.name_male() if gender == "M" else fake.name_female(),
            "身分證字號": id_number,
            "性別": "男" if gender == "M" else "女",
            "生日": _random_birthday(rng, min_age, max_age).isoformat(),
            "手機": _random_mobile(rng),
            "Email": fake.email(),
            "地址": address,
            "申請項目": item,
            "補助金額": rng.randint(min_amount // 100, max_amount // 100) * 100,
            "備註": _random_note(rng, fake),
        })
    return pd.DataFrame(rows)


def save_applicants_csv(path: Path | None = None, n: int = 500, seed: int = 2026) -> Path:
    """產生名冊並存成 CSV。用 utf-8-sig 編碼，Excel 直接開啟中文才不會亂碼。"""
    path = path or DATA_DIR / "applicants.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    generate_applicants(n=n, seed=seed).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_applicants(path: Path | None = None) -> pd.DataFrame:
    """
    讀取名冊。所有欄位都當文字讀入：
    否則 pandas 會把手機 0912345678 當成數字，開頭的 0 就不見了。
    """
    path = path or DATA_DIR / "applicants.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# Demo 2：某市居民年收入
# ---------------------------------------------------------------------------

# 虛構城市的各區：(居民人數, 收入中位數)。區名刻意用虛構的，避免被誤解成真實地區的收入統計。
# 人數差距大 → 小區（山腳區 100 人）加入差分隱私後誤差會明顯較大，適合在取捨曲線中展示。
INCOME_DISTRICTS = {
    "中區": (1200, 600_000),
    "東區": (1000, 650_000),
    "西區": (900, 520_000),
    "北區": (700, 550_000),
    "南區": (550, 480_000),
    "新城區": (350, 580_000),
    "港區": (200, 450_000),
    "山腳區": (100, 400_000),
}

# 對數常態分布的離散程度：0.65 會產生明顯右偏（少數高所得者拉高平均）
INCOME_SIGMA = 0.65


def generate_incomes(seed: int = 2026) -> pd.DataFrame:
    """
    產生 5,000 筆假的居民年收入（欄位：id、區、年收入）。
    收入 = exp(常態分布)，即對數常態分布：大多數人集中在中低收入，少數人收入很高，
    和真實收入分布一樣「平均數 > 中位數」。
    """
    rng = np.random.default_rng(seed)
    frames = []
    for district, (count, median) in INCOME_DISTRICTS.items():
        # 對數常態的中位數 = exp(mu)，所以 mu = ln(中位數)
        incomes = rng.lognormal(mean=np.log(median), sigma=INCOME_SIGMA, size=count)
        frames.append(pd.DataFrame({"區": district, "年收入": (incomes / 1000).round() * 1000}))

    df = pd.concat(frames, ignore_index=True)
    # 打亂順序後重新編號，讓 id 和區沒有關聯
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    df["年收入"] = df["年收入"].astype(int)
    df.insert(0, "id", range(1, len(df) + 1))
    return df


def save_incomes_csv(path: Path | None = None, seed: int = 2026) -> Path:
    path = path or DATA_DIR / "incomes.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    generate_incomes(seed=seed).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_incomes(path: Path | None = None) -> pd.DataFrame:
    path = path or DATA_DIR / "incomes.csv"
    return pd.read_csv(path, encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# Demo 3：MyData 概念模擬的民眾與地政資料
# ---------------------------------------------------------------------------

# 主角：固定的基本資料，錄影時每次都一樣（身分證字號仍由產生器產生，保證檢查碼正確）
PROTAGONIST = {"name": "王小明", "gender": "M", "birthday": "1985-03-15"}

LAND_SECTIONS = ["仁愛", "和平", "興安", "福德", "長春", "成功", "中興", "永安"]
REGISTRATION_REASONS = ["買賣", "買賣", "買賣", "繼承", "贈與", "拍賣"]


def _random_land_record(rng: random.Random, share: str | None = None) -> dict:
    """一筆地政資料：地號、房屋地址、持分、建物面積、公告土地現值、登記日期、登記原因、他項權利。"""
    address, district = _random_address(rng)
    section = rng.choice(["一", "二", "三", "四"])
    year = rng.randint(1995, 2025)
    has_mortgage = rng.random() < 0.6
    return {
        "land_number": f"{district}{rng.choice(LAND_SECTIONS)}段{section}小段 "
                       f"{rng.randint(1, 999):04d}-0000 地號",
        "building_address": address,
        "ownership_share": share or rng.choice(["1/1", "1/1", "1/1", "1/2", "1/3", "1/4"]),
        "building_area_m2": round(rng.uniform(40, 180), 2),
        "announced_land_value": rng.randint(15, 120) * 10_000,   # 元/平方公尺
        "registration_date": date(year, rng.randint(1, 12), rng.randint(1, 28)).isoformat(),
        "registration_reason": rng.choice(REGISTRATION_REASONS),
        "mortgage": (f"最高限額抵押權，設定金額 {rng.randint(3, 30) * 120} 萬元"
                     if has_mortgage else "無"),
    }


def generate_citizens(n_others: int = 20, seed: int = 2026) -> tuple[list[dict], list[dict]]:
    """
    產生 Demo 3 的民眾與地政資料：主角王小明 + n_others 位其他民眾。
    回傳 (citizens, land_records)，citizen_id 依序為 C001、C002……（C001 一定是王小明）。
    """
    rng = random.Random(seed)
    fake = Faker("zh_TW")
    fake.seed_instance(seed)

    citizens, land_records = [], []
    used_ids = set()

    def new_id(gender: str) -> str:
        id_number = generate_tw_id(rng, gender=gender, letter="A")
        while id_number in used_ids:
            id_number = generate_tw_id(rng, gender=gender, letter="A")
        used_ids.add(id_number)
        return id_number

    # 主角王小明：兩筆不動產（一筆單獨所有、一筆與配偶各持分 1/2）
    citizens.append({
        "citizen_id": "C001",
        "national_id": new_id(PROTAGONIST["gender"]),
        "name": PROTAGONIST["name"],
        "gender": "男",
        "birthday": PROTAGONIST["birthday"],
        "phone": _random_mobile(rng),
    })
    land_records.append({"citizen_id": "C001", **_random_land_record(rng, share="1/1")})
    land_records.append({"citizen_id": "C001", **_random_land_record(rng, share="1/2")})

    # 其他民眾：每人 0～2 筆不動產
    for i in range(2, n_others + 2):
        gender = rng.choice(["M", "F"])
        citizen_id = f"C{i:03d}"
        citizens.append({
            "citizen_id": citizen_id,
            "national_id": new_id(gender),
            "name": fake.name_male() if gender == "M" else fake.name_female(),
            "gender": "男" if gender == "M" else "女",
            "birthday": _random_birthday(rng, 25, 80).isoformat(),
            "phone": _random_mobile(rng),
        })
        for _ in range(rng.choice([0, 1, 1, 2])):
            land_records.append({"citizen_id": citizen_id, **_random_land_record(rng)})

    return citizens, land_records


if __name__ == "__main__":
    for output in (save_applicants_csv(), save_incomes_csv()):
        print(f"已產生 {output}")
