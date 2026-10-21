"""深掘り（発展）：最適化・因果・ベイズ

    ④ 製造数を決める   … 新聞売り子問題（作りすぎの損 vs 売り逃しの損）    → プロダクト・経営
    ⑤ SNS投稿は効いたか … 交絡（週末に投稿が多い）を揃えて比べる          → マーケティング
    ⑥ 新商品テスト     … Beta-二項モデルで「BがAより良い確率」を出す      → プロダクト・マーケティング
"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import bakery_core as C
from views.common import DOMAIN_COLOR, Ctx, need_data, pct, yen


# ============================================================ ④ 新聞売り子
def page_seizou(ctx: Ctx):
    st.title("🍞 製造数を決める（新聞売り子問題）")
    st.markdown("作りすぎれば **廃棄（原価の損）**、作り足りなければ **売り逃し（粗利の損）**。"
                "両方の損が釣り合う製造数は、需要の分布の **臨界比 =（単価−原価）÷ 単価** の分位点です。")
    need_data(ctx)
    c1, c2, c3 = st.columns(3)
    prods = ctx.products["商品"].tolist()
    p = c1.selectbox("商品", prods, index=0)
    wd = c2.selectbox("曜日", C.WEEKDAYS[2:] + C.WEEKDAYS[:2], index=0)
    wx = c3.selectbox("天気（予報）", ["すべて", "晴", "曇", "雨"], index=0)
    pr = ctx.products.set_index("商品").loc[p]
    price, cost = float(pr["単価"]), float(pr["原価"])

    s = ctx.sales[ctx.sales["商品"] == p].merge(ctx.daily[["日付", "天気"]], on="日付", how="left")
    s = s[pd.to_datetime(s["日付"]).dt.weekday == C.WEEKDAYS.index(wd)]
    if wx != "すべて":
        s = s[s["天気"] == wx]
    if len(s) < 4:
        st.info(f"条件に合う日が {len(s)} 日しかありません。曜日か天気の条件をゆるめてください。")
        return
    s = s.copy()
    s["売切れ"] = s["廃棄数"] == 0
    adj = st.slider("売切れの日の需要を、販売数の何倍とみなすか（打ち切りの補正）", 1.0, 1.5, 1.15, 0.05,
                    help="売切れの日は「それ以上は売れなかった」のではなく「それ以上は作っていなかった」。販売数は需要の下限にすぎません。")
    demand = np.where(s["売切れ"], s["販売数"].astype(float) * adj, s["販売数"].astype(float))
    cr = C.critical_ratio(price, cost)
    nv = C.newsvendor(demand, price, cost)
    best = nv.loc[nv["期待粗利"].idxmax()]
    q_cr = float(np.quantile(demand, cr))
    actual = float(s["製造数"].astype(float).mean())
    act_row = C.newsvendor(demand, price, cost, [int(round(actual))]).iloc[0]

    m = st.columns(4)
    m[0].metric("臨界比", f"{cr:.2f}", f"単価 {yen(price)}・原価 {yen(cost)}", delta_color="off", delta_arrow="off")
    m[1].metric("目安の製造数", f"{int(best['製造数'])} 個", f"需要の {cr*100:.0f}% 分位 ≒ {q_cr:.0f}", delta_color="off", delta_arrow="off")
    m[2].metric("いまの平均製造数", f"{actual:.0f} 個", f"売切れ {s['売切れ'].mean()*100:.0f}% の日", delta_color="off", delta_arrow="off")
    m[3].metric("期待粗利の差（1日）", yen(best["期待粗利"] - act_row["期待粗利"]),
                f"廃棄 {act_row['期待廃棄']:.1f} → {best['期待廃棄']:.1f} 個", delta_color="off", delta_arrow="off")

    long = nv.melt(id_vars="製造数", value_vars=["期待粗利", "期待廃棄"], var_name="指標", value_name="値")
    base = alt.Chart(nv).encode(x=alt.X("製造数:Q"))
    prof = base.mark_line(color=DOMAIN_COLOR["経営"], strokeWidth=3).encode(
        y=alt.Y("期待粗利:Q", axis=alt.Axis(format=",.0f", titleColor=DOMAIN_COLOR["経営"])),
        tooltip=["製造数", alt.Tooltip("期待粗利:Q", format=",.0f"), alt.Tooltip("期待廃棄:Q", format=".1f"),
                 alt.Tooltip("売切れ確率:Q", format=".0%")])
    waste = base.mark_line(color=DOMAIN_COLOR["プロダクト"], strokeDash=[5, 3]).encode(
        y=alt.Y("期待廃棄:Q", title="期待廃棄（個）", axis=alt.Axis(titleColor=DOMAIN_COLOR["プロダクト"])))
    rules = alt.Chart(pd.DataFrame({"x": [best["製造数"], actual], "lbl": ["目安", "いま"]})).mark_rule(color="#555").encode(
        x="x:Q", strokeDash=alt.StrokeDash("lbl:N", legend=alt.Legend(orient="top", title=None)))
    st.altair_chart(alt.layer(alt.layer(prof, rules), waste).resolve_scale(y="independent").properties(height=280), width="stretch")
    st.caption(f"実線＝1日の期待粗利（左軸）、破線＝期待廃棄（右軸）。条件に合う日：{len(s)} 日（うち売切れ {int(s['売切れ'].sum())} 日）。"
               "過去の需要がこれからも同じ、という仮定の上での目安です。")
    with st.expander("考え方（なぜ臨界比の分位点なのか）"):
        st.markdown(f"1個多く作るとき、売れれば **{yen(price - cost)}** 得をし、売れ残れば **{yen(cost)}** 損をします。"
                    f"「売れる確率 × {yen(price - cost)} ＝ 売れ残る確率 × {yen(cost)}」となる所が釣り合いで、"
                    f"そこでは **需要がその数を下回る確率 ＝ {cr:.2f}**。粗利率の高い商品ほど、多めに作るのが合理的になります。\n\n"
                    "発展：曜日・天気・季節で需要を予測する回帰と組み合わせる、日々の結果から学び直す（強化学習のバンディット）、"
                    "売切れ時刻から打ち切りを推定する（生存時間分析）。")


# ============================================================ ⑤ SNS（交絡）
def page_sns(ctx: Ctx):
    st.title("📸 SNS投稿は効いたか（因果の目）")
    st.markdown("「投稿した日は客が多い」は、投稿の **効果** でしょうか？　投稿は **週末に多い** ので、"
                "週末だから客が多いだけかもしれません（**交絡**）。曜日・天気・気温・イベント・季節を揃えて比べます。")
    need_data(ctx)
    n1 = int((ctx.k["SNS投稿"] == 1).sum())
    if len(ctx.k) < 30 or n1 < 5 or len(ctx.k) - n1 < 5:
        st.info(f"日報が {len(ctx.k)} 日分（投稿した日 {n1} 日）です。条件を揃えた比較には、"
                "30日以上・投稿した日としない日がそれぞれ5日以上ほしいところです。")
        st.stop()
    e = C.sns_effect(ctx.k)
    m = st.columns(3)
    m[0].metric("単純比較（投稿した日 vs しない日）", f"{e['naive']*100:+.1f}%", "交絡を含む", delta_color="off", delta_arrow="off")
    m[1].metric("条件を揃えた推定", f"{e['adjusted']*100:+.1f}%", f"95%区間 {e['lo']*100:+.1f}% 〜 {e['hi']*100:+.1f}%",
                delta_color="off", delta_arrow="off")
    m[2].metric("投稿日のうち週末の割合", pct(e["weekend_sns"]), f"投稿しない日では {pct(e['weekend_nosns'])}", delta_color="off", delta_arrow="off")

    left, right = st.columns([2, 3])
    with left:
        st.graphviz_chart("""
digraph { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#f4f6f4", color="#9aa5b1", fontname="sans-serif"];
  週末 -> SNS投稿 [label=" 投稿しやすい"]; 週末 -> 客数 [label=" 客が多い"];
  天気 -> 客数; イベント -> 客数; SNS投稿 -> 客数 [label=" 知りたい効果", color="#eb6834", penwidth=2]; }""")
        st.caption("週末 → 投稿、週末 → 客数 の2本の矢印があると、単純比較には週末の効果が混ざります（裏口の道）。")
    with right:
        k = ctx.k.copy()
        k["日の種類"] = np.where(pd.to_datetime(k["日付"]).dt.weekday >= 5, "週末", "平日")
        k["SNS"] = np.where(k["SNS投稿"] == 1, "投稿した", "しない")
        g = k.groupby(["日の種類", "SNS"]).agg(平均客数=("客数", "mean"), 日数=("日付", "count")).reset_index()
        ch = alt.Chart(g).mark_bar().encode(
            x=alt.X("SNS:N", title=None, sort=["しない", "投稿した"]), y=alt.Y("平均客数:Q"),
            color=alt.Color("SNS:N", scale=alt.Scale(domain=["しない", "投稿した"], range=["#c9d6e3", DOMAIN_COLOR["マーケティング"]]), legend=None),
            column=alt.Column("日の種類:N", title=None, sort=["平日", "週末"]), tooltip=["日の種類", "SNS", alt.Tooltip("平均客数:Q", format=".1f"), "日数"])
        st.altair_chart(ch.properties(height=220, width=150))
        st.caption("同じ「平日どうし」「週末どうし」で比べると、差はずっと小さくなります（層別）。")

    with st.expander("回帰の表（log客数 ＝ 切片 ＋ SNS投稿 ＋ 週末 ＋ 雨 ＋ 曇 ＋ 最高気温 ＋ イベント ＋ 経過）"):
        tab = e["table"]
        st.dataframe(tab.round(4), hide_index=True, width="stretch")
        st.caption(f"n = {tab.attrs['n']}、R² = {tab.attrs['R2']:.3f}。log客数の係数 b は、およそ (e^b − 1) × 100 % の違い。")
    st.warning("揃えられるのは **測った条件だけ**。新作を出した日に投稿しがち、など測っていない交絡は残ります。"
               "確かめたいなら、投稿する日をくじ引きで決める（ランダム化）のがいちばん確かです。"
               + ("（サンプルには真の効果 +8% を仕込んであります）" if ctx.is_sample else ""))


# ============================================================ ⑥ ベイズA/B
def page_ab(ctx: Ctx):
    st.title("🧪 新商品テスト（ベイズA/B）")
    st.markdown("試食やPOPの有無で、購入率は変わったか。**Beta-二項モデル** で、それぞれの購入率の分布と "
                "**「BがAより良い確率」** を出します。p値の代わりに「どれくらい確からしいか」で話せます。")
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown("**A：いつも通り**")
        na = st.number_input("声をかけた（見た）人数 A", 1, 100000, 120, key="na")
        ka = st.number_input("買った人数 A", 0, 100000, 18, key="ka")
    with c2.container(border=True):
        st.markdown("**B：試してみる（例：柿デニッシュの試食あり）**")
        nb = st.number_input("声をかけた（見た）人数 B", 1, 100000, 115, key="nb")
        kb = st.number_input("買った人数 B", 0, 100000, 27, key="kb")
    if ka > na or kb > nb:
        st.error("買った人数が、声をかけた人数より多くなっています。")
        return
    prior = st.select_slider("事前の考え", ["何も知らない Beta(1,1)", "購入率は1〜2割くらい Beta(3,15)"], "何も知らない Beta(1,1)")
    a0, b0 = (1, 1) if prior.startswith("何も") else (3, 15)
    rng = np.random.default_rng(3)
    xa = rng.beta(a0 + ka, b0 + na - ka, 40000)
    xb = rng.beta(a0 + kb, b0 + nb - kb, 40000)
    p_b = float((xb > xa).mean())
    lift = (xb - xa)
    m = st.columns(3)
    m[0].metric("P(B の購入率 > A)", f"{p_b*100:.1f}%")
    m[1].metric("差（B−A）の中央値", f"{np.median(lift)*100:+.1f}pt",
                f"90%区間 {np.quantile(lift, .05)*100:+.1f} 〜 {np.quantile(lift, .95)*100:+.1f}pt", delta_color="off", delta_arrow="off")
    pu = ctx.products.set_index("商品")
    gain = np.median(lift) * 100 * (pu.loc["柿とクリームチーズのデニッシュ", "単価"] - pu.loc["柿とクリームチーズのデニッシュ", "原価"]) \
        if "柿とクリームチーズのデニッシュ" in pu.index else np.nan
    m[2].metric("100人あたりの粗利の差（目安）", yen(gain), "デニッシュの単価−原価で計算", delta_color="off", delta_arrow="off")

    xs = np.linspace(0, max(np.quantile(xa, .999), np.quantile(xb, .999)) * 1.1, 200)
    from math import lgamma
    def dens(x, a, b):
        x = np.clip(x, 1e-9, 1 - 1e-9)
        return np.exp((a - 1) * np.log(x) + (b - 1) * np.log(1 - x) + lgamma(a + b) - lgamma(a) - lgamma(b))
    df = pd.concat([pd.DataFrame({"購入率": xs, "密度": dens(xs, a0 + ka, b0 + na - ka), "群": "A：いつも通り"}),
                    pd.DataFrame({"購入率": xs, "密度": dens(xs, a0 + kb, b0 + nb - kb), "群": "B：試す"})])
    ch = alt.Chart(df).mark_area(opacity=0.45).encode(
        x=alt.X("購入率:Q", axis=alt.Axis(format=".0%")), y=alt.Y("密度:Q", axis=None),
        color=alt.Color("群:N", scale=alt.Scale(range=["#9aa5b1", DOMAIN_COLOR["マーケティング"]]), legend=alt.Legend(orient="top", title=None)))
    st.altair_chart(ch.properties(height=220), width="stretch")
    if p_b >= 0.95:
        st.success("B が良い可能性が高い（95%以上）。B を標準にし、翌月の /tsuki でふりかえる。")
    elif p_b <= 0.05:
        st.info("A のほうが良い可能性が高い。B はやめる。")
    else:
        st.info("まだどちらとも言えない。人数を増やして続ける（決める基準：95% / 5% を先に決めておく）。")
    st.caption("A と B は同じ時期・同じ曜日に、日ごと交互に（できればくじ引きで）割り当てる。そうしないと⑤の交絡が入り込みます。")
