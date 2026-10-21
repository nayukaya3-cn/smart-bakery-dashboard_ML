"""計算部品を、人が先に決めた期待値で検証する（pytest -q）"""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bakery_core as C  # noqa: E402

D, S, M, P = C.load_sample()
K = C.daily_kpi(D, S, P)


def test_sample_shape_and_closed_days():
    # 月・火は定休日：日報に月・火は1日もない
    assert len(D) > 100 and set(K["曜日"]) == set("水木金土日")
    # 廃棄数 = 製造数 − 販売数、販売数は製造数を超えない
    assert (S["廃棄数"] == S["製造数"] - S["販売数"]).all()
    assert (S["販売数"] <= S["製造数"]).all()


def test_kpi_by_hand():
    # 手計算：食パン 10個作って8個売れた（単価420・原価150）→ 売上3360、原価1500、廃棄率0.2
    d = pd.DataFrame([["2026-04-01", "晴", 20, 4, 2.0, 0, "", ""]], columns=C.DAILY_COLS)
    s = pd.DataFrame([["2026-04-01", "自家製小麦の食パン", 10, 8, 2]], columns=C.SALES_COLS)
    k = C.daily_kpi(C.clean_daily(d), C.clean_sales(s), P).iloc[0]
    assert k["売上"] == 3360 and k["材料原価"] == 1500
    assert abs(k["粗利率"] - (3360 - 1500) / 3360) < 1e-9
    assert abs(k["廃棄率"] - 0.2) < 1e-9 and k["客単価"] == 840 and k["人時売上"] == 1680


def test_period_ratio_is_recomputed_from_sums():
    # 週の廃棄率は「日ごとの率の平均」ではなく「合計÷合計」
    w = C.period_kpi(K, "週").iloc[3]
    kw = K[K["週"] == w["週"]]
    assert abs(w["廃棄率"] - kw["廃棄数"].sum() / kw["製造数"].sum()) < 1e-12


def test_missing_waste_is_filled():
    s = pd.DataFrame([["2026-05-01", "米粉パン", 10, 7, None]], columns=C.SALES_COLS)
    assert int(C.clean_sales(s)["廃棄数"].iloc[0]) == 3


def test_flags_waste_cap_and_baseline():
    day = K["日付"].iloc[-1]
    f = C.propose_flags(K, day, 0.15, waste_cap=0.0).set_index("key")
    assert f.loc["廃棄率", "機械の提案"] == C.FLAG_WATCH        # 上限0なら必ず要確認
    assert C.baseline(K, K["日付"].iloc[0], "売上") is None      # 過去がなければ基準なし
    assert C.confirmed(C.FLAG_WATCH, C.CONFIRM_FIX_NORMAL) == C.FLAG_NORMAL
    assert C.confirmed(C.FLAG_GOOD, C.CONFIRM_OK) == C.FLAG_GOOD


def test_streak_skips_closed_days():
    days = {"2026-10-18", "2026-10-21"}            # 日曜と水曜（間の月・火は定休日）
    assert C.streak(days, date(2026, 10, 21)) == 2


def test_beta_and_priority():
    mean, lo, hi = C.beta_post(1, 10)
    assert abs(mean - 2 / 12) < 1e-12 and lo < mean < hi
    assert C.prob_greater(30, 100, 10, 100) > 0.99
    assert C.priority(1000, 3, 0.9) == 0                    # 試して効いた手があれば0
    assert C.priority(1000, 0, 0.5) == 1000 and C.priority(1000, 0, 0.9, w=1) == 1400


def test_newsvendor_matches_critical_ratio():
    rng = np.random.default_rng(0)
    dem = rng.poisson(40, 5000)
    nv = C.newsvendor(dem, 400, 100)
    best = nv.loc[nv["期待粗利"].idxmax(), "製造数"]
    assert abs(best - np.quantile(dem, C.critical_ratio(400, 100))) <= 1


def test_sns_confounding_detected():
    e = C.sns_effect(K)
    # 仕込んだ真の効果は +8%。単純比較は週末の交絡で大きく出て、揃えた推定の区間は真値を含む
    assert e["naive"] > e["adjusted"]
    assert e["lo"] < 0.08 < e["hi"]
    assert e["weekend_sns"] > e["weekend_nosns"]


def test_k_anonymity_and_generalize():
    kmin, risky = C.k_anonymity(M, ["年代", "性別", "地区"], 3)
    assert kmin < 3 and len(risky) > 0
    m2 = C.generalize(C.generalize(M, "地区", C.AREA_COARSE), "年代", C.AGE_COARSE)
    kmin2, _ = C.k_anonymity(m2, ["年代", "地区"], 3)
    assert kmin2 >= kmin


def test_design_markdown_has_all_items():
    md = C.design_markdown("プロダクト", C.DESIGN_EXAMPLES["プロダクト"], "廃棄と売り逃し")
    for _, label in C.DESIGN_ITEMS:
        assert label in md
    assert md.count("|:---|:---|") == 1
