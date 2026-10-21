"""スマートパン屋農家 ダッシュボードの計算部品（Streamlit から切り離した純粋関数）

    経営       : 売上・粗利・人時売上（1時間あたり売上）
    マーケティング: 客数・客単価・新規会員・認知経路
    プロダクト   : 商品別の製造・販売・廃棄、自家原料比率

講義との対応
    第1回 DSとは／必要なスキル     → SKILLS
    第2回 DSプロセス（6フェイズ）   → PHASES, report_markdown()
    第3回 DS設計（現状→問題→課題、逆算、ロジックモデル）、オープンデータ、個人情報
                                 → DESIGN_ITEMS, DESIGN_EXAMPLES, design_markdown(), k_anonymity()
発展
    ベイズ（Beta-二項）・新聞売り子問題（製造数）・交絡を意識した回帰（SNS投稿の効果）
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
DOMAINS = ["経営", "マーケティング", "プロダクト"]
DOMAIN_ICON = {"経営": "💴", "マーケティング": "📣", "プロダクト": "🥐"}
WEEKDAYS = list("月火水木金土日")

DAILY_COLS = ["日付", "天気", "最高気温", "客数", "労働時間", "SNS投稿", "イベント", "メモ"]
SALES_COLS = ["日付", "商品", "製造数", "販売数", "廃棄数"]
PRODUCT_COLS = ["商品", "区分", "単価", "原価", "自家原料比率", "販売開始"]
MEMBER_COLS = ["会員ID", "年代", "性別", "地区", "認知経路", "初回来店", "来店回数", "最終来店"]

# ---------------------------------------------------------------- 商品マスタ（架空）
PRODUCTS = pd.DataFrame([
    ["自家製小麦の食パン", "食事パン", 420, 150, 0.80, "2026-04-01"],
    ["季節野菜のフォカッチャ", "食事パン", 380, 140, 0.60, "2026-04-01"],
    ["米粉パン", "食事パン", 300, 110, 0.70, "2026-04-01"],
    ["クロワッサン", "ヴィエノワズリー", 280, 120, 0.30, "2026-04-01"],
    ["あんバター", "菓子パン", 260, 100, 0.20, "2026-04-01"],
    ["柿とクリームチーズのデニッシュ", "菓子パン", 320, 130, 0.50, "2026-09-02"],
], columns=PRODUCT_COLS)


# ================================================================ 架空サンプルの生成
def generate_sample(start: str = "2026-04-01", end: str = "2026-10-21", seed: int = 7):
    """架空の日報・販売・会員データ（水〜日営業）。

    わざと仕込んだ構造（発展ページで「見抜けるか」を試す）:
      - SNS投稿の真の効果は客数 +8%。ただし投稿は週末に多い（交絡）→ 単純比較は効果を過大に見せる
      - 製造数は「同じ曜日の販売の移動平均×1.12」のルール → 雨の日や平日に廃棄が増える
      - 売切れの日の販売数は需要より小さい（打ち切り）
    """
    rng = np.random.default_rng(seed)
    share = {"自家製小麦の食パン": 0.30, "季節野菜のフォカッチャ": 0.17, "米粉パン": 0.14,
             "クロワッサン": 0.25, "あんバター": 0.19, "柿とクリームチーズのデニッシュ": 0.16}
    daily, sales = [], []
    last_sold: dict = {}
    for d in pd.date_range(start, end):
        wd = d.weekday()
        if wd in (0, 1):                                   # 月・火は定休日（畑の日）
            continue
        month = d.month
        weather = rng.choice(["晴", "曇", "雨"], p=[0.5, 0.3, 0.2])
        temp = round(float(14 + 14 * np.sin((d.dayofyear - 105) / 365 * 2 * np.pi) + rng.normal(0, 2.5)), 1)
        weekend = wd >= 5
        sns = int(rng.random() < (0.7 if weekend else 0.2))
        event = "マルシェ出店" if (wd == 6 and d.day <= 7) else ""
        lam = 58 * (1.45 if weekend else 1.0) * {"晴": 1.0, "曇": 0.93, "雨": 0.72}[weather]
        lam *= (1.08 if sns else 1.0) * (1.25 if event else 1.0) * (1 + 0.025 * (month - 4))
        cust = int(rng.poisson(lam))
        labor = round(float(26 + (6 if weekend else 0) + (4 if event else 0) + rng.normal(0, 1.5)), 1)
        memo = ""
        if weather == "雨" and rng.random() < 0.5:
            memo = "雨で午後の客足が鈍い。"
        elif sns and rng.random() < 0.3:
            memo = "インスタの新作投稿を見たというお客さんがいた。"
        daily.append([d.date().isoformat(), weather, temp, cust, labor, sns, event, memo])
        for p, sh in share.items():
            if pd.Timestamp(PRODUCTS.set_index("商品").loc[p, "販売開始"]) > d:
                continue
            demand = int(rng.poisson(max(1.0, cust * sh * 2.1)))
            key = (p, wd)
            est = last_sold.get(key, lam * sh * 2.1)
            made = max(6, int(round(est * 1.12 / 2) * 2))
            sold = min(demand, made)
            sales.append([d.date().isoformat(), p, made, sold, made - sold])
            # 作り手は「売れた数」しか見えない（売切れの日は少し上乗せして覚える）
            last_sold[key] = 0.5 * est + 0.5 * (sold * 1.1 if sold == made else sold)
    daily_df = pd.DataFrame(daily, columns=DAILY_COLS)
    sales_df = pd.DataFrame(sales, columns=SALES_COLS)

    # 会員（架空）。地区×年代×性別には、わざと少人数の組合せを混ぜる
    areas = ["西条町", "八本松町", "高屋町", "志和町", "黒瀬町", "福富町"]
    area_p = [0.38, 0.22, 0.18, 0.10, 0.09, 0.03]
    ages = ["20代", "30代", "40代", "50代", "60代", "70代以上"]
    age_p = [0.12, 0.26, 0.24, 0.17, 0.14, 0.07]
    routes = ["インスタグラム", "口コミ", "通りがかり", "マルシェ", "チラシ"]
    members = []
    open_days = pd.to_datetime(daily_df["日付"])
    for i in range(160):
        first = open_days.iloc[int(rng.integers(0, len(open_days)))]
        age = rng.choice(ages, p=age_p)
        route_p = [0.45, 0.2, 0.15, 0.12, 0.08] if age in ("20代", "30代") else [0.15, 0.3, 0.2, 0.15, 0.2]
        span = (pd.Timestamp(end) - first).days
        visits = 1 + int(rng.poisson(span / 30 * (0.9 if rng.random() < 0.55 else 0.15)))
        last = first + pd.Timedelta(days=int(rng.integers(0, span + 1))) if visits > 1 else first
        members.append([f"M{i+1:03d}", age, rng.choice(["女性", "男性"], p=[0.68, 0.32]),
                        rng.choice(areas, p=area_p), rng.choice(routes, p=route_p),
                        first.date().isoformat(), visits, min(last, pd.Timestamp(end)).date().isoformat()])
    members_df = pd.DataFrame(members, columns=MEMBER_COLS).sort_values("初回来店").reset_index(drop=True)
    members_df["会員ID"] = [f"M{i+1:03d}" for i in range(len(members_df))]
    return daily_df, sales_df, members_df


def write_sample(dir_: Path = DATA_DIR):
    dir_.mkdir(parents=True, exist_ok=True)
    d, s, m = generate_sample()
    d.to_csv(dir_ / "sample_daily.csv", index=False, encoding="utf-8-sig")
    s.to_csv(dir_ / "sample_sales.csv", index=False, encoding="utf-8-sig")
    m.to_csv(dir_ / "sample_members.csv", index=False, encoding="utf-8-sig")
    PRODUCTS.to_csv(dir_ / "sample_products.csv", index=False, encoding="utf-8-sig")


def load_sample(dir_: Path = DATA_DIR):
    if not (dir_ / "sample_daily.csv").exists():
        write_sample(dir_)
    rd = lambda n: pd.read_csv(dir_ / n, encoding="utf-8-sig", keep_default_na=False)  # noqa: E731
    return (clean_daily(rd("sample_daily.csv")), clean_sales(rd("sample_sales.csv")),
            clean_members(rd("sample_members.csv")), clean_products(rd("sample_products.csv")))


# ================================================================ データ準備（型・欠損）
def _num(s, kind=float):
    return pd.to_numeric(s, errors="coerce").astype("Float64" if kind is float else "Int64")


def clean_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=DAILY_COLS).copy()
    df["日付"] = pd.to_datetime(df["日付"], errors="coerce").dt.date.astype(str)
    df["最高気温"] = _num(df["最高気温"])
    df["客数"] = _num(df["客数"], int)
    df["労働時間"] = _num(df["労働時間"])
    df["SNS投稿"] = _num(df["SNS投稿"], int).fillna(0)
    for c in ("天気", "イベント", "メモ"):
        df[c] = df[c].fillna("").astype(str)
    return df[df["日付"] != "NaT"].drop_duplicates("日付", keep="last").sort_values("日付").reset_index(drop=True)


def clean_sales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=SALES_COLS).copy()
    df["日付"] = pd.to_datetime(df["日付"], errors="coerce").dt.date.astype(str)
    for c in ("製造数", "販売数", "廃棄数"):
        df[c] = _num(df[c], int)
    miss = df["廃棄数"].isna() & df["製造数"].notna() & df["販売数"].notna()
    df.loc[miss, "廃棄数"] = df.loc[miss, "製造数"] - df.loc[miss, "販売数"]
    df["商品"] = df["商品"].fillna("").astype(str)
    df = df[(df["日付"] != "NaT") & (df["商品"] != "")]
    return df.drop_duplicates(["日付", "商品"], keep="last").sort_values(["日付", "商品"]).reset_index(drop=True)


def clean_members(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=MEMBER_COLS).copy()
    df["来店回数"] = _num(df["来店回数"], int)
    for c in ("年代", "性別", "地区", "認知経路", "会員ID"):
        df[c] = df[c].fillna("").astype(str)
    return df


def clean_products(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=PRODUCT_COLS).copy()
    for c in ("単価", "原価", "自家原料比率"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ================================================================ KPI（経営・マーケ・プロダクト）
def sales_detail(sales: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """販売明細に金額を付ける（売上＝販売数×単価、原価＝製造数×原価：作った分は売れなくても原価がかかる）"""
    s = sales.merge(products[["商品", "単価", "原価", "自家原料比率"]], on="商品", how="left")
    s["売上"] = (s["販売数"].astype(float) * s["単価"]).astype(float)
    s["材料原価"] = (s["製造数"].astype(float) * s["原価"]).astype(float)
    s["廃棄金額"] = (s["廃棄数"].astype(float) * s["原価"]).astype(float)
    s["売切れ"] = (s["廃棄数"] == 0) & (s["製造数"] > 0)
    s["自家原料売上"] = s["売上"] * s["自家原料比率"].fillna(0)
    return s


def daily_kpi(daily: pd.DataFrame, sales: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """1日1行のKPI表（3領域をまとめて持つ）"""
    s = sales_detail(sales, products)
    agg = s.groupby("日付").agg(売上=("売上", "sum"), 材料原価=("材料原価", "sum"), 廃棄金額=("廃棄金額", "sum"),
                              製造数=("製造数", "sum"), 販売数=("販売数", "sum"), 廃棄数=("廃棄数", "sum"),
                              売切れ品数=("売切れ", "sum"), 自家原料売上=("自家原料売上", "sum")).reset_index()
    k = daily.merge(agg, on="日付", how="left")
    for c in ("売上", "材料原価", "廃棄金額", "製造数", "販売数", "廃棄数", "売切れ品数", "自家原料売上"):
        k[c] = pd.to_numeric(k[c], errors="coerce").fillna(0).astype(float)
    k["粗利"] = k["売上"] - k["材料原価"]
    k["粗利率"] = _safe_div(k["粗利"], k["売上"])
    k["廃棄率"] = _safe_div(k["廃棄数"], k["製造数"])
    k["客単価"] = _safe_div(k["売上"], k["客数"].astype(float))
    k["人時売上"] = _safe_div(k["売上"], k["労働時間"].astype(float))
    k["自家原料比率"] = _safe_div(k["自家原料売上"], k["売上"])
    return add_period_cols(k)


def _safe_div(a, b) -> pd.Series:
    a = pd.to_numeric(pd.Series(a), errors="coerce").astype(float)
    b = pd.to_numeric(pd.Series(b), errors="coerce").astype(float)
    out = a / b.where(b != 0)
    return out.astype(float)


def add_period_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    d = pd.to_datetime(df["日付"], errors="coerce")
    df["曜日"] = d.dt.weekday.map(lambda i: WEEKDAYS[int(i)] if pd.notna(i) else "")
    df["週"] = (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.date.astype(str)
    df["月"] = d.dt.strftime("%Y-%m")
    return df


def period_kpi(k: pd.DataFrame, by: str) -> pd.DataFrame:
    """週・月ごとのKPI（比率は合計から計算し直す：日ごとの率の平均にしない）"""
    if k.empty:
        return pd.DataFrame()
    g = k.groupby(by).agg(営業日=("日付", "count"), 売上=("売上", "sum"), 粗利=("粗利", "sum"),
                          材料原価=("材料原価", "sum"), 廃棄金額=("廃棄金額", "sum"), 客数=("客数", "sum"),
                          労働時間=("労働時間", "sum"), 製造数=("製造数", "sum"), 廃棄数=("廃棄数", "sum"),
                          SNS投稿=("SNS投稿", "sum"), 自家原料売上=("自家原料売上", "sum")).reset_index()
    g["客数"] = g["客数"].astype(float)
    g["粗利率"] = _safe_div(g["粗利"], g["売上"])
    g["廃棄率"] = _safe_div(g["廃棄数"], g["製造数"])
    g["客単価"] = _safe_div(g["売上"], g["客数"])
    g["人時売上"] = _safe_div(g["売上"], g["労働時間"])
    g["1日あたり客数"] = _safe_div(g["客数"], g["営業日"])
    g["自家原料比率"] = _safe_div(g["自家原料売上"], g["売上"])
    return g


def product_kpi(sales: pd.DataFrame, products: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    s = add_period_cols(sales_detail(sales, products))
    keys = ["商品"] + ([by] if by else [])
    g = s.groupby(keys).agg(製造数=("製造数", "sum"), 販売数=("販売数", "sum"), 廃棄数=("廃棄数", "sum"),
                            売上=("売上", "sum"), 材料原価=("材料原価", "sum"), 廃棄金額=("廃棄金額", "sum"),
                            売切れ日=("売切れ", "sum"), 日数=("日付", "count")).reset_index()
    for c in ("製造数", "販売数", "廃棄数"):
        g[c] = g[c].astype(float)
    g["廃棄率"] = _safe_div(g["廃棄数"], g["製造数"])
    g["粗利"] = g["売上"] - g["材料原価"]
    g["売切れ率"] = _safe_div(g["売切れ日"], g["日数"])
    return g


# ================================================================ 毎日：機械の「気づき」提案
@dataclass
class Metric:
    key: str
    label: str
    domain: str
    higher_is_better: bool
    fmt: str            # "yen" / "pct" / "int" / "num"


METRICS = [
    Metric("売上", "売上", "経営", True, "yen"),
    Metric("粗利率", "粗利率", "経営", True, "pct"),
    Metric("人時売上", "人時売上（円/時間）", "経営", True, "yen"),
    Metric("客数", "客数", "マーケティング", True, "int"),
    Metric("客単価", "客単価", "マーケティング", True, "yen"),
    Metric("廃棄率", "廃棄率", "プロダクト", False, "pct"),
    Metric("売切れ品数", "売切れ品数（機会損失の可能性）", "プロダクト", False, "int"),
]
M = {m.key: m for m in METRICS}

FLAG_WATCH = "要確認"
FLAG_GOOD = "よい変化"
FLAG_NORMAL = "いつも通り"
CONFIRM_OK = "OK"
CONFIRM_FIX_WATCH = "直し→要確認にする"
CONFIRM_FIX_NORMAL = "直し→問題なし"
CONFIRM_OPTS = [CONFIRM_OK, CONFIRM_FIX_WATCH, CONFIRM_FIX_NORMAL]
CHECK_COLS = ["日付", "領域", "指標", "今日", "基準", "機械の提案", "人の確認", "確定", "ひとこと", "記録日時"]


def fmt_value(v, fmt: str) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v):
        return "—"
    if fmt == "yen":
        return f"¥{v:,.0f}"
    if fmt == "pct":
        return f"{v*100:.1f}%"
    if fmt == "int":
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def baseline(k: pd.DataFrame, day: str, metric: str, n: int = 4) -> float | None:
    """基準＝直近 n 回の同じ曜日の中央値（曜日の波を消すため。平均より外れ値に強い）"""
    d = pd.Timestamp(day)
    past = k[(pd.to_datetime(k["日付"]) < d) & (pd.to_datetime(k["日付"]).dt.weekday == d.weekday())]
    vals = pd.to_numeric(past.sort_values("日付")[metric], errors="coerce").dropna().tail(n)
    if len(vals) < 2:
        return None
    return float(vals.median())


def propose_flags(k: pd.DataFrame, day: str, tol: float = 0.15, waste_cap: float = 0.15) -> pd.DataFrame:
    """1日分の指標を基準と比べ、機械が「要確認／よい変化／いつも通り」を提案する。

    - 比率の指標は差（ポイント）、それ以外は比（%）で判定
    - 廃棄率は基準と関係なく上限（waste_cap）を超えたら要確認
    機械がやるのは「いつもと違う」まで。なぜ違うか・問題かどうかは人が決める。
    """
    row = k[k["日付"] == day]
    rows = []
    if row.empty:
        return pd.DataFrame(columns=["領域", "指標", "今日", "基準", "差", "機械の提案"])
    row = row.iloc[0]
    for m in METRICS:
        v = row.get(m.key)
        v = None if pd.isna(v) else float(v)
        b = baseline(k, day, m.key)
        prop, diff = FLAG_NORMAL, None
        if v is not None and b is not None:
            if m.fmt == "pct":
                diff = v - b
                big = abs(diff) >= tol / 2
            elif m.key == "売切れ品数":
                diff = v - b
                big = abs(diff) >= 2
            else:
                diff = (v - b) / b if b else None
                big = diff is not None and abs(diff) >= tol
            if big:
                better = (diff > 0) == m.higher_is_better
                prop = FLAG_GOOD if better else FLAG_WATCH
        if m.key == "廃棄率" and v is not None and v > waste_cap:
            prop = FLAG_WATCH
        rows.append({"領域": m.domain, "指標": m.label, "key": m.key,
                     "今日": fmt_value(v, m.fmt), "基準": fmt_value(b, m.fmt),
                     "差": ("—" if diff is None else (f"{diff*100:+.1f}pt" if m.fmt == "pct"
                                                     else f"{diff:+.0f}" if m.key == "売切れ品数" else f"{diff*100:+.0f}%")),
                     "機械の提案": prop})
    return pd.DataFrame(rows)


def confirmed(proposal: str, confirm: str) -> str:
    if confirm == CONFIRM_FIX_WATCH:
        return FLAG_WATCH
    if confirm == CONFIRM_FIX_NORMAL:
        return FLAG_NORMAL
    return proposal


def product_flags(sales: pd.DataFrame, day: str, waste_cap: float = 0.2) -> pd.DataFrame:
    """商品別：廃棄が多い／売切れ（需要はもっとあったかも）"""
    s = sales[sales["日付"] == day].copy()
    if s.empty:
        return pd.DataFrame(columns=["商品", "製造数", "販売数", "廃棄数", "廃棄率", "気づき"])
    s["廃棄率"] = _safe_div(s["廃棄数"], s["製造数"]).values
    s["気づき"] = np.where(s["廃棄数"] == 0, "売切れ：需要はもっとあった可能性",
                         np.where(s["廃棄率"] > waste_cap, "廃棄が多い", ""))
    return s[["商品", "製造数", "販売数", "廃棄数", "廃棄率", "気づき"]]


def streak(days: set, ref: date) -> int:
    """連続して日報を書いた営業日数（定休日の月・火は飛ばす）"""
    n, d = 0, ref
    if d.isoformat() not in days:
        d -= timedelta(days=1)
    while True:
        if d.weekday() in (0, 1):
            d -= timedelta(days=1)
            continue
        if d.isoformat() in days:
            n += 1
            d -= timedelta(days=1)
        else:
            return n


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ================================================================ 毎週：現状→あるべき姿→問題
@dataclass
class Target:
    sales_month: float = 1_250_000
    gross_margin: float = 0.58
    waste_rate: float = 0.10
    unit_price: float = 780
    new_members_month: float = 25
    labor_sales: float = 2_000

    def rows(self, open_days_in_month: int = 22):
        return [
            ("経営", "売上（1営業日あたり）", "売上_日", self.sales_month / max(1, open_days_in_month), True, "yen"),
            ("経営", "粗利率", "粗利率", self.gross_margin, True, "pct"),
            ("経営", "人時売上", "人時売上", self.labor_sales, True, "yen"),
            ("マーケティング", "客単価", "客単価", self.unit_price, True, "yen"),
            ("マーケティング", "新規会員（30日換算）", "新規会員_30日", self.new_members_month, True, "num"),
            ("プロダクト", "廃棄率", "廃棄率", self.waste_rate, False, "pct"),
        ]


def gap_table(period_row: pd.Series, new_members_30: float, target: Target) -> pd.DataFrame:
    """第3回：現状（As Is）とあるべき姿の差＝問題（Issue）を表にする"""
    vals = dict(period_row)
    vals["売上_日"] = _f(vals.get("売上")) / max(1, int(vals.get("営業日", 1) or 1))
    vals["新規会員_30日"] = new_members_30
    rows = []
    for dom, label, key, goal, hib, fmt in target.rows():
        v = _f(vals.get(key))
        if v is None or np.isnan(v):
            gap, ok = None, None
        else:
            gap = v - goal
            ok = gap >= 0 if hib else gap <= 0
        rows.append({"領域": dom, "指標": label, "現状（As Is）": fmt_value(v, fmt),
                     "あるべき姿": fmt_value(goal, fmt),
                     "差": ("—" if gap is None else (f"{gap*100:+.1f}pt" if fmt == "pct" else
                                                     f"{gap:+,.0f}" if fmt in ("yen", "int") else f"{gap:+.1f}")),
                     "問題（Issue）": "—" if ok is None else ("なし" if ok else "あり"),
                     "_rel": None if gap is None else (abs(gap) / goal if goal else 0) * (0 if ok else 1)})
    return pd.DataFrame(rows)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def new_members(members: pd.DataFrame, start: str, end: str) -> int:
    d = pd.to_datetime(members["初回来店"], errors="coerce")
    return int(((d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end))).sum())


def repeat_rate(members: pd.DataFrame, ref: date, min_days: int = 30) -> tuple[float, int]:
    """初回から min_days 日以上たった会員のうち、2回以上来た割合"""
    d = pd.to_datetime(members["初回来店"], errors="coerce")
    old = members[d <= pd.Timestamp(ref) - pd.Timedelta(days=min_days)]
    if old.empty:
        return float("nan"), 0
    return float((old["来店回数"].astype(float) >= 2).mean()), len(old)


# ================================================================ 毎月：ベイズで割合を推定し、順番の目安を出す
def beta_post(k: int, n: int, a: float = 1.0, b: float = 1.0):
    """Beta(a,b) 事前 × 二項（n回中k回）→ 事後の平均と90%区間"""
    rng = np.random.default_rng(0)
    s = rng.beta(a + k, b + n - k, 20000)
    return float((a + k) / (a + b + n)), float(np.quantile(s, 0.05)), float(np.quantile(s, 0.95))


def prob_greater(k1: int, n1: int, k0: int, n0: int, a: float = 1.0, b: float = 1.0, draws: int = 20000) -> float:
    """P(今月の割合 > 前月の割合)（Beta事後どうしをサンプリングで比べる）"""
    rng = np.random.default_rng(1)
    x1 = rng.beta(a + k1, b + n1 - k1, draws)
    x0 = rng.beta(a + k0, b + n0 - k0, draws)
    return float((x1 > x0).mean())


READY = {0: "0 手がない", 1: "1 担当（役割）は決まっている", 2: "2 手順が書いてある", 3: "3 試して効いた"}
MONTH_COLS = ["月", "商品", "準備度", "機械の順位", "人が決めた順位", "打つ手", "担当（役割）", "期限", "入れ替えた理由", "記録日時"]
LOGIC_COLS = ["月", "領域", "投入", "活動", "アウトプット", "アウトカム", "成果指標", "記録日時"]
WEEK_COLS = ["週", "領域", "指標", "現状", "あるべき姿", "問題", "課題（Action）", "記録日時"]


def monthly_waste_table(sales: pd.DataFrame, products: pd.DataFrame, month: str) -> pd.DataFrame:
    """商品×月の廃棄率をベイズ推定し、前月より悪化した確率と「損失の目安」を出す"""
    pk = product_kpi(sales, products, by="月")
    months = sorted(pk["月"].unique())
    prev = months[months.index(month) - 1] if month in months and months.index(month) > 0 else None
    rows = []
    for p in pk["商品"].unique():
        cur = pk[(pk["商品"] == p) & (pk["月"] == month)]
        if cur.empty:
            continue
        c = cur.iloc[0]
        kk, nn = int(c["廃棄数"]), int(c["製造数"])
        mean, lo, hi = beta_post(kk, nn)
        p_up = None
        if prev is not None:
            pv = pk[(pk["商品"] == p) & (pk["月"] == prev)]
            if not pv.empty:
                p_up = prob_greater(kk, nn, int(pv.iloc[0]["廃棄数"]), int(pv.iloc[0]["製造数"]))
        rows.append({"商品": p, "製造数": nn, "廃棄数": kk, "廃棄率（推定）": mean, "90%区間_下": lo, "90%区間_上": hi,
                     "P(前月より悪化)": p_up, "廃棄金額": float(c["廃棄金額"]), "売切れ日": int(c["売切れ日"])})
    return pd.DataFrame(rows)


def priority(loss: float, ready: int, p_up: float | None, w: float = 1.0) -> float:
    """優先度の目安 = 損失の目安 × (1 − 準備度/3) × (1 + w × max(0, P(悪化) − 0.5))

    機械が出すのは「提案順」まで。順番を決めるのは人（入れ替えた理由を残す）。
    """
    pu = 0.5 if p_up is None or np.isnan(p_up) else p_up
    return float(loss * (1 - ready / 3) * (1 + w * max(0.0, pu - 0.5)))


# ================================================================ 発展①：製造数を決める（新聞売り子問題）
def newsvendor(demand: np.ndarray, price: float, cost: float, q_grid=None) -> pd.DataFrame:
    """作りすぎ（廃棄＝原価の損）と作り足りない（売り逃し＝粗利の損）の釣り合い。

    最適な製造数は需要分布の「臨界比 (単価−原価)/単価」分位点。
    demand は過去の販売数（売切れ日は需要より小さい＝打ち切りがある点に注意）。
    """
    demand = np.asarray(demand, dtype=float)
    if q_grid is None:
        q_grid = np.arange(max(0, int(demand.min()) - 5), int(demand.max()) + 15)
    rows = []
    for q in q_grid:
        sold = np.minimum(demand, q)
        profit = sold * price - q * cost
        rows.append({"製造数": int(q), "期待粗利": float(profit.mean()), "期待廃棄": float((q - sold).mean()),
                     "売切れ確率": float((demand >= q).mean())})
    return pd.DataFrame(rows)


def critical_ratio(price: float, cost: float) -> float:
    return (price - cost) / price


# ================================================================ 発展②：SNS投稿の効果（交絡を意識する）
def ols(y: np.ndarray, X: np.ndarray, names: list[str]) -> pd.DataFrame:
    """最小二乗法（切片付き）。係数・標準誤差・95%区間"""
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    dof = max(1, len(y) - X1.shape[1])
    sigma2 = resid @ resid / dof
    cov = sigma2 * np.linalg.pinv(X1.T @ X1)
    se = np.sqrt(np.diag(cov))
    r2 = 1 - (resid @ resid) / (((y - y.mean()) ** 2).sum())
    out = pd.DataFrame({"変数": ["切片"] + names, "係数": beta, "標準誤差": se,
                        "95%下": beta - 1.96 * se, "95%上": beta + 1.96 * se})
    out.attrs["R2"] = float(r2)
    out.attrs["n"] = int(len(y))
    return out


def sns_effect(k: pd.DataFrame) -> dict:
    """SNS投稿日の客数は何%多いか：単純比較 vs 曜日・天気・気温・イベントを揃えた比較（log客数の回帰）"""
    d = k.dropna(subset=["客数"]).copy()
    d = d[d["客数"] > 0]
    y = np.log(d["客数"].astype(float).to_numpy())
    sns = d["SNS投稿"].astype(float).to_numpy()
    naive = float(np.exp(y[sns == 1].mean() - y[sns == 0].mean()) - 1) if sns.sum() and (1 - sns).sum() else float("nan")
    wd = pd.to_datetime(d["日付"]).dt.weekday
    X = np.column_stack([
        sns,
        (wd >= 5).astype(float),
        (d["天気"] == "雨").astype(float),
        (d["天気"] == "曇").astype(float),
        d["最高気温"].astype(float).fillna(d["最高気温"].astype(float).mean()),
        (d["イベント"] != "").astype(float),
        pd.to_datetime(d["日付"]).dt.dayofyear.astype(float) / 30,
    ])
    names = ["SNS投稿", "週末", "雨", "曇", "最高気温", "イベント", "経過（月）"]
    tab = ols(y, X, names)
    r = tab.set_index("変数").loc["SNS投稿"]
    share_weekend_sns = float(((wd >= 5) & (sns == 1)).sum() / max(1, sns.sum()))
    share_weekend_nosns = float(((wd >= 5) & (sns == 0)).sum() / max(1, (1 - sns).sum()))
    return {"naive": naive, "adjusted": float(np.exp(r["係数"]) - 1),
            "lo": float(np.exp(r["95%下"]) - 1), "hi": float(np.exp(r["95%上"]) - 1),
            "table": tab, "weekend_sns": share_weekend_sns, "weekend_nosns": share_weekend_nosns}


# ================================================================ 第1回：DSとは／必要なスキル
SKILLS = {
    "ビジネス力": "課題の背景を理解し、ビジネス課題を整理・解決する力（例：廃棄を減らすと粗利がいくら増えるか言える）",
    "データサイエンス力": "統計・情報処理・AIなどの知恵を理解し、使う力（例：曜日の波を除いて比べる、区間で語る）",
    "データエンジニアリング力": "データを意味のある形で使えるようにし、実装・運用する力（例：日報を毎日同じ形式で溜める）",
}
SOFT_SKILLS = ["課題を言葉にする（業務理解）", "論理的に考察する", "チームで伝える（コミュニケーション）",
               "場を進める（ファシリテーション）", "データを丁寧に扱う（倫理・個人情報）"]

DX_TERMS = pd.DataFrame([
    ["デジタイゼーション", "紙の日報・手書きの製造メモをデータにする", "日報CSV・販売表"],
    ["デジタライゼーション", "データで個々の業務を変える（製造数の決め方を変える）", "製造数の目安・廃棄アラート"],
    ["DX（デジタルトランスフォーメーション）", "畑→パン→お客さまの流れ全体と、稼ぎ方を変える", "自家原料の価値をデータで語るブランド・会員づくり"],
    ["データサイエンス", "データから課題解決に役立つ知見を引き出す一連のプロセス", "このダッシュボードの日→週→月"],
], columns=["用語", "スマートパン屋農家では", "このダッシュボードでの例"])

# ================================================================ 第2回：DSプロセス
PHASES = pd.DataFrame([
    ["業務理解", "課題の背景・ゴール・評価指標を整理", "第3〜4回", 10],
    ["データ理解", "データの棚卸し・品質調査・可視化", "第5回", 15],
    ["データ準備", "クレンジング・統合・数量化", "第6〜7回", 50],
    ["モデリング", "検定・回帰・判別・主成分・クラスター", "第8回", 10],
    ["評価", "指標で評価、仮説と照らして解釈", "第9回", 10],
    ["展開", "提言としてまとめ発表", "第13〜14回", 5],
], columns=["フェイズ", "演習Ⅰで行うこと", "主な回", "所要時間の目安(%)"])
PHASE_STATUS = ["未着手", "進行中", "済み"]

# ================================================================ 第3回：DS設計シート（第一段階）
DESIGN_ITEMS = [
    ("対象業務", "対象業務（誰の、どんな業務か）"),
    ("ゴール", "ゴール（その業務をどう良くしたいか）"),
    ("現状", "現状（As Is：今起きている事実）"),
    ("問題", "問題（Issue：あるべき姿との差）"),
    ("課題", "課題（Action：問題を解決するために取り組むこと）"),
    ("ほしい分析結果", "ほしい分析結果（推定／予測／要因／分類／比較…）"),
    ("分析手法", "分析手法（候補でよい：集計・可視化／検定／回帰／判別／クラスター…）"),
    ("使うデータ", "使うデータ（手持ち／オープンデータ、入手先）"),
    ("目的変数", "目的変数（説明したい・予測したいもの）"),
    ("説明変数の候補", "説明変数の候補"),
    ("データ処理", "データ処理（結合・数量化・欠損処理など、必要そうなもの）"),
    ("評価指標①", "評価指標①（分析の性能：精度・誤差・有意差など）"),
    ("評価指標②", "評価指標②（業務面の効果：何がどれだけ良くなれば成功か）"),
]
# 右から左へ（逆算）の順番
BACKWARD = ["ゴール", "ほしい分析結果", "分析手法", "データ処理", "使うデータ"]

DESIGN_EXAMPLES = {
    "経営": {
        "対象業務": "スマートパン屋農家（農業法人）の日々の製造計画と労務配置",
        "ゴール": "粗利を確保しながら、人時売上（1時間あたり売上）を上げる",
        "現状": "平日の人時売上が週末より低く、雨の日は売上が3割近く落ちる",
        "問題": "人時売上が目標（2,000円/時間）に届かない営業日が多い",
        "課題": "売上が落ちる日の条件を特定し、その日の人員と製造量を前日に調整する",
        "ほしい分析結果": "予測（翌営業日の客数）と要因（曜日・天気・イベントの影響の大きさ）",
        "分析手法": "集計・可視化 → 重回帰（log客数）",
        "使うデータ": "日報（手持ち）、気象庁の過去の気象データ（オープンデータ）",
        "目的変数": "客数（または売上）",
        "説明変数の候補": "曜日、天気、最高気温、イベント、SNS投稿",
        "データ処理": "日報と販売表を日付で結合、天気をダミー変数化、欠損日の扱いを決める",
        "評価指標①": "予測誤差（MAE）、係数の95%区間",
        "評価指標②": "人時売上が目標を下回る営業日を月5日以下にする",
    },
    "マーケティング": {
        "対象業務": "店頭とSNSでの集客、会員づくり",
        "ゴール": "地域の20〜30代のリピーターを増やす",
        "現状": "新規会員は月20人前後。初回から30日以上たった会員の再来店は半分程度",
        "問題": "目標（新規25人/月・再来店6割）より少ない",
        "課題": "再来店する会員の特徴と、SNS投稿が客数に与える効果を明らかにする",
        "ほしい分析結果": "要因（再来店に効く特徴）と比較（SNS投稿の有無で客数はどれだけ違うか）",
        "分析手法": "クロス集計 → ロジスティック回帰／交絡を揃えた回帰",
        "使うデータ": "会員台帳（匿名化済み）、日報、RESASの人口データ",
        "目的変数": "再来店（2回以上来店したか）、客数",
        "説明変数の候補": "年代、地区、認知経路、初回来店の曜日、SNS投稿",
        "データ処理": "会員IDで照合、地区を大きな区分にまとめる（少人数の組合せをなくす）",
        "評価指標①": "係数の有意性、AUC",
        "評価指標②": "翌々月の再来店率を5ポイント上げる",
    },
    "プロダクト": {
        "対象業務": "パンの品ぞろえと日々の製造数の決定",
        "ゴール": "廃棄を減らし、自家原料の看板商品の売り逃しもなくす",
        "現状": "製造数は「同じ曜日の販売の移動平均×1.12」で決めており、雨の平日に廃棄が増える",
        "問題": "廃棄率が目標（10%）を超える商品がある",
        "課題": "商品・曜日ごとの需要の幅を推定し、廃棄と売り逃しの釣り合う製造数を決める",
        "ほしい分析結果": "推定（商品別の需要分布）と予測（翌営業日の適正製造数）",
        "分析手法": "集計・可視化 → ベイズ推定（廃棄率）→ 新聞売り子モデル",
        "使うデータ": "販売表（製造・販売・廃棄）、商品マスタ（単価・原価）",
        "目的変数": "販売数（＝需要。ただし売切れ日は打ち切り）",
        "説明変数の候補": "商品、曜日、天気、季節、新商品の有無",
        "データ処理": "売切れ日のフラグ付け（打ち切りの扱い）、販売開始前の日を除く",
        "評価指標①": "廃棄率の90%区間、製造数の目安と実績の差",
        "評価指標②": "全体の廃棄率を10%以下にし、看板商品の売切れ率を2割以下に保つ",
    },
}

LOGIC_EXAMPLES = {
    "経営": ["日報データ・2人×30分/週", "雨予報の日は前日に製造量と人員を見直す", "見直しを月8回実施", "人時売上が目標を下回る日が月5日以下"],
    "マーケティング": ["スマホ・写真・会員台帳", "新作の投稿を週3回、初回来店者に次回特典", "投稿12本・特典配布60枚", "再来店率が5ポイント上がる"],
    "プロダクト": ["販売表・商品マスタ", "商品×曜日ごとに製造数の目安を出し、朝に確認", "目安どおりに作った日が8割", "廃棄率10%以下・売り逃し2割以下"],
}

OPEN_DATA = pd.DataFrame([
    ["e-Stat（政府統計の総合窓口）", "家計調査：品目別「パン」支出額（都市別・月別）", "地域のパン需要の季節変動と比べる", "経営・マーケティング"],
    ["気象庁「過去の気象データ」", "日別の天気・気温・降水量（東広島）", "雨・気温の影響を揃えて比べる", "経営・プロダクト"],
    ["RESAS（地域経済分析システム）", "人口構成・人の流れ", "商圏の年代構成とターゲットを比べる", "マーケティング"],
    ["農林水産省 統計", "小麦の作付・収穫量", "自家製小麦の位置づけを語る", "プロダクト"],
    ["自治体のオープンデータ", "東広島市の人口・施設一覧など", "出店先（マルシェ等）の候補を探す", "マーケティング"],
], columns=["入手先", "中身の例", "このダッシュボードでの使い道", "領域"])
OPEN_DATA_CHECKS = ["利用条件（出典を書けば使ってよいか：CC BY など）", "定義（「世帯」「パン」などの言葉の意味）",
                    "単位・時点・粒度（千円単位か、何年か、市町村別か）", "出典をレポートに書いた"]


def design_markdown(domain: str, sheet: dict, title: str = "") -> str:
    """設計シートを、Colab ノートブックの「課題C」セルにそのまま貼れる Markdown にする"""
    lines = [f"### テーマ候補", "", f"- 分野：自身の研究課題（スマートパン屋農家・{domain}）",
             f"- 仮タイトル：{title or '（記入）'}", "", "### 第一段階：DSプロセスに沿った設計", "",
             "| 項目 | 内容 |", "|:---|:---|"]
    for key, label in DESIGN_ITEMS:
        v = str(sheet.get(key, "") or "（記入）").replace("|", "／").replace("\n", " ")
        lines.append(f"| {label} | {v} |")
    return "\n".join(lines) + "\n"


def logic_markdown(domain: str, row: list[str]) -> str:
    return ("| 投入 | → 活動 | → 結果（アウトプット） | → 成果（アウトカム） |\n|---|---|---|---|\n"
            f"| {' | '.join(x.replace('|', '／') for x in row)} |\n")


def report_markdown(title: str, kpi_row: pd.Series, gap: pd.DataFrame, note: str = "") -> str:
    """第2回：Markdown で報告書の形にする（見出し・箇条書き・表）"""
    lines = [f"## {title}", "", "### 何のために", "- スマートパン屋農家の経営・マーケティング・プロダクトを、データで毎週見直すため", "",
             "### 何をして", f"- 営業日 {int(kpi_row.get('営業日', 0))} 日分の日報と販売表を集計した", "",
             "### 何が分かったか", "", "| 領域 | 指標 | 現状 | あるべき姿 | 差 | 問題 |", "|:---|:---|---:|---:|---:|:---:|"]
    for _, r in gap.iterrows():
        lines.append(f"| {r['領域']} | {r['指標']} | {r['現状（As Is）']} | {r['あるべき姿']} | {r['差']} | {r['問題（Issue）']} |")
    if note:
        lines += ["", "### 次にやること（課題）", f"- {note}"]
    return "\n".join(lines) + "\n"


# ================================================================ 第3回：匿名化の限界（k-匿名性）
def k_anonymity(df: pd.DataFrame, quasi: list[str], k: int = 3) -> tuple[int, pd.DataFrame]:
    """準識別子の組合せごとの人数。k 人未満の組合せは「名前がなくても誰か分かる」おそれ"""
    if not quasi:
        return len(df), pd.DataFrame()
    g = df.groupby(quasi, dropna=False).size().reset_index(name="人数").sort_values("人数")
    return int(g["人数"].min()) if len(g) else 0, g[g["人数"] < k]


def generalize(df: pd.DataFrame, col: str, mapping: dict) -> pd.DataFrame:
    out = df.copy()
    out[col] = out[col].map(lambda x: mapping.get(x, x))
    return out


AREA_COARSE = {"西条町": "西条", "八本松町": "西条周辺", "高屋町": "西条周辺", "志和町": "郊外",
               "黒瀬町": "郊外", "福富町": "郊外"}
AGE_COARSE = {"20代": "20〜30代", "30代": "20〜30代", "40代": "40〜50代", "50代": "40〜50代",
              "60代": "60代以上", "70代以上": "60代以上"}
