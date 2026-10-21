"""スマートパン屋農家 スマート化ダッシュボード — 経営・マーケティング・プロダクトを日→週→月で進化させる

    毎日（3分） /nippo   日報と販売数を書く → 機械の「いつもと違う」提案に OK／直し
    毎週（10分）/shuukei 現状とあるべき姿の差（問題）を見て、今週の課題（Action）を決める
    毎月（30分）/tsuki   ベイズ推定で順番の目安 → 準備度を答え、打つ手とロジックモデルを決める

講義「多分野データ解析実践演習Ⅰ」第1〜3回（DSとは／DSプロセス／DS設計）を「学ぶ」ページに、
因果・ベイズ・最適化の発展を「深掘り」ページに置いている。

起動:  streamlit run app.py   → http://localhost:8501/nippo のように、ページを URL で直接開ける
データ: 既定は架空サンプル（2026年4〜10月）。実データは手元（data/raw/、.gitignore 済み）でのみ扱う（README参照）。
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

import bakery_core as C
import store as S
from views import deep, learn, routine
from views.common import Ctx

st.set_page_config(page_title="スマートパン屋農家 ダッシュボード", page_icon="🥖", layout="wide")

SRC_SAMPLE = "架空サンプル（2026年4〜10月）"
SRC_FILE = "手元のファイル（data/raw/）"
SRC_UP = "CSV をアップロード（一時）"


# ============================================================ サイドバー：設定
def sidebar():
    sb = st.sidebar
    sb.markdown("### 🥖 スマートパン屋農家")
    sb.caption("畑 → パン → お客さま を、データで毎日少しずつ良くする")
    with sb.expander("⚙️ データ", expanded=False):
        src = st.radio("読み込むデータ", [SRC_SAMPLE, SRC_FILE, SRC_UP], key="src",
                       help="毎日書き足すなら「手元のファイル」。記録は data/raw/ に保存され、リポジトリには入りません。")
        ups = {}
        if src == SRC_UP:
            for kind, label in (("daily", "日報 daily.csv"), ("sales", "販売表 sales.csv"),
                                ("members", "会員台帳 members.csv（任意）"), ("products", "商品マスタ products.csv（任意）")):
                ups[kind] = st.file_uploader(label, type=["csv"], key=f"up_{kind}")
            st.caption("⚠️ 公開サーバー上のアプリに実データを上げない。実データは手元で `streamlit run` して使う。")
        if src != SRC_FILE:
            st.caption("この画面で足した日報・決定は**このセッション内だけ**に残ります（各ページからCSVで保存できます）。")
        ref = st.date_input("基準日（今日）", date.today(), help="毎日・毎週・毎月の「今」をどこに置くか")
    with sb.expander("🎯 あるべき姿（目標）", expanded=False):
        t = C.Target(
            sales_month=st.number_input("月の売上目標（円）", 0, 10_000_000, 1_250_000, 50_000),
            gross_margin=st.slider("粗利率の目標", 0.30, 0.80, 0.58, 0.01),
            waste_rate=st.slider("廃棄率の上限", 0.02, 0.30, 0.10, 0.01),
            unit_price=st.number_input("客単価の目標（円）", 0, 5_000, 780, 10),
            new_members_month=st.number_input("新規会員の目標（人/30日）", 0, 500, 25, 1),
            labor_sales=st.number_input("人時売上の目標（円/時間）", 0, 20_000, 2_000, 100),
        )
    with sb.expander("⚙️ 機械の提案の感度", expanded=False):
        tol = st.slider("「いつもと違う」とみなす変化（売上・客数など）", 0.05, 0.40, 0.15, 0.01,
                        help="基準（直近4回の同じ曜日の中央値）からの変化率。比率の指標はこの半分（ポイント）")
        cap = st.slider("1日の廃棄率がこれを超えたら要確認", 0.05, 0.40, 0.15, 0.01)
    return src, ups, ref, t, tol, cap


src, ups, ref, target, tol, cap = sidebar()

# ============================================================ データ準備
store = S.Store(persist=(src == SRC_FILE))
sd, ss, sm, sp = C.load_sample()
if src == SRC_FILE:
    daily, sales, members, products = S.read_local()
    is_sample, sig = False, ("file",)
elif src == SRC_UP and ups.get("daily") is not None and ups.get("sales") is not None:
    rd = lambda f: pd.read_csv(f, dtype=str, keep_default_na=False, encoding="utf-8-sig")  # noqa: E731
    daily, sales = C.clean_daily(rd(ups["daily"])), C.clean_sales(rd(ups["sales"]))
    members = C.clean_members(rd(ups["members"])) if ups.get("members") is not None else sm.iloc[0:0]
    products = C.clean_products(rd(ups["products"])) if ups.get("products") is not None else sp
    is_sample, sig = False, ("upload", ups["daily"].name, ups["daily"].size, ups["sales"].name, ups["sales"].size)
else:
    if src == SRC_UP:
        st.sidebar.info("日報と販売表の両方が選ばれるまで、サンプルを表示しています。")
    daily, sales, members, products = sd, ss, sm, sp
    is_sample, sig = True, ("sample",)

if st.session_state.get("data_sig") != sig:          # データの出どころが変わったら記録を入れ替える
    st.session_state.data_sig = sig
    for key in ("_store", "_added"):
        st.session_state.pop(key, None)
    store = S.Store(persist=(src == SRC_FILE))

if not store.persist:                                 # セッション内で足した日報を後ろにつなぐ
    ad, as_ = store.added("daily"), store.added("sales")
    if len(ad):
        daily = C.clean_daily(pd.concat([daily[~daily["日付"].isin(ad["日付"])], ad], ignore_index=True))
        sales = C.clean_sales(pd.concat([sales[~sales["日付"].isin(ad["日付"])], as_], ignore_index=True))

if products.empty:
    products = sp
k = C.daily_kpi(daily, sales, products) if len(daily) else C.add_period_cols(pd.DataFrame(columns=["日付"]))

pages: dict = {}
ctx = Ctx(daily=daily, sales=sales, members=members, products=products, k=k, ref=ref, target=target,
          store=store, is_sample=is_sample, tol=tol, waste_cap=cap, pages=pages)


# ============================================================ ページ（日→週→月を軸に）
def _p(fn, title, url, icon, default=False):
    def run():
        fn(ctx)
    run.__name__ = url or "home"
    page = st.Page(run, title=title, url_path=url or None, icon=icon, default=default)
    pages[url or "home"] = page
    return page


nav = st.navigation({
    "ルーティン（日→週→月）": [
        _p(routine.page_home, "今日のルーティン", "", "🗓️", default=True),
        _p(routine.page_nippo, "毎日 /nippo（3分）", "nippo", "✍️"),
        _p(routine.page_shuukei, "毎週 /shuukei（10分）", "shuukei", "🔍"),
        _p(routine.page_tsuki, "毎月 /tsuki（30分）", "tsuki", "🧭"),
    ],
    "学ぶ（講義 第1〜3回）": [
        _p(learn.page_kai1, "DSとは・必要なスキル", "kai1", "1️⃣"),
        _p(learn.page_kai2, "DSプロセスと報告", "kai2", "2️⃣"),
        _p(learn.page_kai3, "DS設計・データの扱い", "kai3", "3️⃣"),
    ],
    "深掘り（発展）": [
        _p(deep.page_seizou, "製造数を決める", "seizou", "4️⃣"),
        _p(deep.page_sns, "SNSは効いたか（因果）", "sns", "5️⃣"),
        _p(deep.page_ab, "新商品テスト（ベイズ）", "ab", "6️⃣"),
    ],
})
nav.run()

st.divider()
st.caption("サンプルは架空のスマートパン屋農家（水〜日営業・2026年4月〜10月21日、商品6種、会員160人）。"
           "店名・地区の人数・会員はすべて架空。機械の提案・優先度・推定はいずれも目安で、決めるのは人です。")
