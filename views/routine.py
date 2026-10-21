"""ルーティン（日→週→月）：今日のルーティン・/nippo・/shuukei・/tsuki

時間の粒度が上がるほど、機械の仕事が減り、人の判断が増える。
    毎日  ① 記録する       : 機械が「いつもと違う」を提案 → 人は OK／直し、ひとこと
    毎週  ② 問題を見つける   : 機械が現状とあるべき姿の差を並べる → 人が今週の課題（Action）を決める
    毎月  ③ 打つ手を決める   : 機械はベイズ推定と順番の目安まで → 人が準備度を答え、順番とロジックモデルを決める
"""
from __future__ import annotations

import re
from datetime import timedelta

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import bakery_core as C
from views.common import DOMAIN_COLOR, FLAG_COLOR, Ctx, csv_download, link, md_download, need_data, now, pct, yen

ACTION_TEMPLATES = {
    "経営": "雨予報・平日の前日に、製造量と人員を見直す（人時売上を守る）",
    "マーケティング": "新作をSNSに週3回投稿し、初回来店の会員に次回特典を渡す",
    "プロダクト": "商品×曜日の製造数の目安（/seizou）を朝に確認してから仕込む",
}
WASTE_ACTIONS = ["製造数の目安（/seizou）を使って仕込み量を下げる", "夕方の値引き・セット販売を試す",
                 "雨予報の日は前日に仕込みを2割減らす", "売切れ時刻を記録し、需要を推定し直す"]


def _latest_day(ctx: Ctx, upto) -> str | None:
    d = [x for x in sorted(ctx.days) if x <= upto.isoformat()]
    return d[-1] if d else (sorted(ctx.days)[-1] if ctx.days else None)


def _mtd(ctx: Ctx, month: str, upto_day: int | None = None) -> pd.Series | None:
    """月の途中までのKPI（前月と比べるときは同じ日数まで）"""
    k = ctx.k[ctx.k["月"] == month]
    if upto_day is not None:
        k = k[pd.to_datetime(k["日付"]).dt.day <= upto_day]
    if k.empty:
        return None
    return C.period_kpi(k.assign(_all="all"), "_all").iloc[0]


def _delta(cur, prev, fmt):
    if cur is None or prev is None or pd.isna(cur) or pd.isna(prev):
        return None
    if fmt == "pct":
        return f"{(cur - prev) * 100:+.1f}pt"
    return f"{(cur - prev) / prev * 100:+.1f}%" if prev else None


# ============================================================ 今日のルーティン（ホーム）
def page_home(ctx: Ctx):
    st.title("🗓️ 今日のルーティン")
    st.markdown("**毎日3分 記録する → 毎週10分 問題を見つける → 毎月30分 打つ手を決める。** "
                "経営・マーケティング・プロダクトの「スマート化」を、このリズムで少しずつ進化させます。")
    ref = ctx.ref
    ws = C.week_start(ref).isoformat()
    mo = ref.strftime("%Y-%m")
    today = ref.isoformat() in ctx.days
    weekly = ctx.store.table("weekly", C.WEEK_COLS)
    monthly = ctx.store.table("monthly", C.MONTH_COLS)
    checks = ctx.store.table("checks", C.CHECK_COLS)

    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.markdown("#### ✍️ 毎日（3分）")
        st.caption(f"今日：{ref.month}/{ref.day}（{C.WEEKDAYS[ref.weekday()]}）"
                   + ("　定休日（畑の日）" if ref.weekday() in (0, 1) else ""))
        st.metric("今日の日報", "記入済み" if today else "まだ", f"連続 {C.streak(ctx.days, ref)} 営業日",
                  delta_color="off", delta_arrow="off")
        st.caption("日報と販売数を書く → 機械の提案に OK／直し")
        link(ctx, "nippo", "記録する /nippo", "✍️")
    with c2.container(border=True):
        st.markdown("#### 🔍 毎週（10分）")
        st.caption(f"今週：{ws} の週")
        n_w = int((weekly["週"] == ws).sum())
        n_watch = int(((checks["確定"] == C.FLAG_WATCH) & (checks["日付"] >= ws)).sum())
        st.metric("今週の課題（Action）", f"{n_w} 件", f"今週の要確認 {n_watch} 件", delta_color="off", delta_arrow="off")
        st.caption("現状とあるべき姿の差（問題）から、今週の課題を決める")
        link(ctx, "shuukei", "問題を見つける /shuukei", "🔍")
    with c3.container(border=True):
        st.markdown("#### 🧭 毎月（30分）")
        st.caption(f"今月：{ref.month}月（終わった月のふりかえりもここで）")
        st.metric("今月の打つ手", "決定済み" if (monthly["月"] == mo).any() else "まだ",
                  f"これまでの決定 {monthly['月'].nunique()} か月", delta_color="off", delta_arrow="off")
        st.caption("ベイズ推定で順番の目安 → 準備度を答え、順番を決める")
        link(ctx, "tsuki", "打つ手を決める /tsuki", "🧭")

    need_data(ctx)
    last = pd.Timestamp(max(ctx.days))
    if (pd.Timestamp(ref) - last).days > 7:
        st.warning(f"最後の日報は {last:%Y-%m-%d}（{(pd.Timestamp(ref) - last).days}日前）。"
                   + ("サンプルは 2026-10-21 で終わっています。" if ctx.is_sample else ""))

    # ---------------- 3領域のKPI：今月（基準日まで）と前月の同じ日数まで
    cur_m = last.strftime("%Y-%m") if (pd.Timestamp(ref) - last).days > 31 else mo
    upto = min(ref, last.date()).day if cur_m == mo else None
    prev_m = (pd.Period(cur_m) - 1).strftime("%Y-%m")
    cur, prev = _mtd(ctx, cur_m, upto), _mtd(ctx, prev_m, upto)
    st.markdown(f"#### 3つの領域：{cur_m}（{upto or '月末'}日まで）と前月の同じ日数まで")
    if cur is None:
        st.info("今月の日報がまだありません。")
    else:
        end = min(ref, last.date())
        nm30 = C.new_members(ctx.members, (end - timedelta(days=29)).isoformat(), end.isoformat())
        rr, nrr = C.repeat_rate(ctx.members, end)
        g = lambda s, c: None if s is None else s.get(c)  # noqa: E731
        cols = st.columns(3)
        spec = {
            "経営": [("売上", "売上", "yen"), ("粗利率", "粗利率", "pct"), ("人時売上", "人時売上", "yen")],
            "マーケティング": [("1日あたり客数", "1日あたり客数", "num"), ("客単価", "客単価", "yen")],
            "プロダクト": [("廃棄率", "廃棄率", "pct"), ("自家原料比率", "自家原料の売上比率", "pct")],
        }
        for col, (dom, items) in zip(cols, spec.items()):
            with col.container(border=True):
                st.markdown(f"##### {C.DOMAIN_ICON[dom]} {dom}")
                for key, label, fmt in items:
                    v, p = g(cur, key), g(prev, key)
                    inv = "inverse" if key == "廃棄率" else "normal"
                    st.metric(label, C.fmt_value(v, fmt if fmt != "num" else "int"), _delta(v, p, fmt), delta_color=inv)
                if dom == "マーケティング":
                    st.metric("新規会員（直近30日）", f"{nm30} 人", f"目標 {ctx.target.new_members_month:.0f} 人",
                              delta_color="off", delta_arrow="off")
                    st.caption(f"再来店率（初回から30日以上の会員 {nrr} 人）：{pct(rr)}")

    # ---------------- 週ごとの推移（目標線つき）
    st.markdown("#### 週ごとの推移と、あるべき姿（目標線）")
    wk = ctx.week_kpi().tail(20)
    opts = {"売上（1営業日あたり）": ("売上_日", "yen", ctx.target.sales_month / 22, "経営"),
            "粗利率": ("粗利率", "pct", ctx.target.gross_margin, "経営"),
            "人時売上": ("人時売上", "yen", ctx.target.labor_sales, "経営"),
            "1日あたり客数": ("1日あたり客数", "int", None, "マーケティング"),
            "客単価": ("客単価", "yen", ctx.target.unit_price, "マーケティング"),
            "廃棄率": ("廃棄率", "pct", ctx.target.waste_rate, "プロダクト")}
    wk = wk.assign(売上_日=wk["売上"] / wk["営業日"])
    pick = st.segmented_control("指標", list(opts), default="廃棄率", key="home_metric") or "廃棄率"
    col, fmt, goal, dom = opts[pick]
    axis_fmt = ".0%" if fmt == "pct" else ",.0f"
    base = alt.Chart(wk).encode(x=alt.X("週:T", title="週のはじまり（月曜）", axis=alt.Axis(format="%-m/%-d")))
    line = base.mark_line(point=True, color=DOMAIN_COLOR[dom]).encode(
        y=alt.Y(f"{col}:Q", title=pick, axis=alt.Axis(format=axis_fmt), scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("週:T", format="%Y-%m-%d"), alt.Tooltip(f"{col}:Q", format=axis_fmt), "営業日"])
    layers = [line]
    if goal is not None:
        layers.append(alt.Chart(pd.DataFrame({"y": [goal]})).mark_rule(strokeDash=[6, 4], color="#555").encode(y="y:Q"))
    st.altair_chart(alt.layer(*layers).properties(height=240), width="stretch")
    st.caption("点線があるべき姿（サイドバーの目標）。線と点線の差が、第3回でいう「問題（Issue）」です。")

    # ---------------- 記入のリズム
    st.markdown("#### 記入のリズム：書いた日（毎日）")
    d = pd.date_range(C.week_start(ref) - timedelta(weeks=15), C.week_start(ref) + timedelta(days=6))
    rt = pd.DataFrame({"日": d})
    rt["曜日"] = rt["日"].dt.weekday.map(lambda i: C.WEEKDAYS[i])
    rt["週"] = (rt["日"] - pd.to_timedelta(rt["日"].dt.weekday, unit="D")).dt.strftime("%-m/%-d")
    rt["状態"] = np.where(rt["日"].dt.date.astype(str).isin(ctx.days), "記入",
                        np.where(rt["日"].dt.weekday.isin([0, 1]), "定休日", "未記入"))
    rt.loc[rt["日"] > pd.Timestamp(ref), "状態"] = "これから"
    heat = alt.Chart(rt).mark_rect(stroke="white", strokeWidth=2, cornerRadius=3).encode(
        x=alt.X("週:O", sort=list(dict.fromkeys(rt["週"])), title="週のはじまり（月曜）", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("曜日:N", sort=C.WEEKDAYS, title=None),
        color=alt.Color("状態:N", scale=alt.Scale(domain=["記入", "未記入", "定休日", "これから"],
                                                 range=["#3d6b3a", "#f2c14e", "#e6e9e6", "#ffffff"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("日:T", format="%Y-%m-%d"), "曜日", "状態"])
    st.altair_chart(heat.properties(height=alt.Step(22)), width="stretch")

    st.markdown("#### 日・週・月で、機械と人の分担を変える")
    st.dataframe(pd.DataFrame([
        ["毎日（3分）", "/nippo", "① 記録する", "KPI計算・同じ曜日との比較 → 「要確認／よい変化」の提案",
         "数字を入れる。提案に OK／直し、ひとこと（なぜか）", "日報・販売表・確認"],
        ["毎週（10分）", "/shuukei", "② 問題を見つける", "現状（As Is）とあるべき姿の差を並べる",
         "どの問題に取り組むか選び、課題（Action）を書く", "今週の課題"],
        ["毎月（30分）", "/tsuki", "③ 打つ手を決める", "廃棄率をベイズ推定・前月より悪化した確率・順番の目安",
         "準備度を答え、順番・打つ手・担当（役割）・期限、ロジックモデルを決める", "決定と、翌月のふりかえり"],
    ], columns=["いつ", "ページ", "3段構え", "機械がすること", "人がすること", "残るもの"]), hide_index=True, width="stretch")


# ============================================================ 毎日 /nippo
def page_nippo(ctx: Ctx):
    st.title("✍️ 毎日 /nippo（3分）")
    st.markdown("**① 記録する。** 日報と販売数を入れると、機械が「いつもと違う」ところを提案します。"
                "人は **OK／直し** と、**なぜか（ひとこと）** を残します。")
    day = st.date_input("日付", ctx.ref, key="nippo_day")
    ds = day.isoformat()
    if day.weekday() in (0, 1):
        st.info("月・火は定休日（畑の日）の設定です。営業した日なら、そのまま記録できます。")
    cur_d = ctx.daily[ctx.daily["日付"] == ds]
    cur_s = ctx.sales[ctx.sales["日付"] == ds]
    exists = not cur_d.empty
    if exists:
        st.success("この日の日報はすでにあります。直して保存すると置き換わります。")
    r = cur_d.iloc[0] if exists else None

    with st.form(f"nippo_{ds}"):
        st.markdown("##### 日報（経営・マーケティング）")
        c = st.columns(6)
        weather = c[0].selectbox("天気", ["晴", "曇", "雨"], index=["晴", "曇", "雨"].index(r["天気"]) if exists and r["天気"] in ("晴", "曇", "雨") else 0)
        temp = c[1].number_input("最高気温（℃）", -10.0, 45.0, float(r["最高気温"]) if exists and pd.notna(r["最高気温"]) else 20.0, 0.5)
        cust = c[2].number_input("客数（会計数）", 0, 2000, int(r["客数"]) if exists and pd.notna(r["客数"]) else 60)
        labor = c[3].number_input("労働時間（全員の合計）", 0.0, 300.0, float(r["労働時間"]) if exists and pd.notna(r["労働時間"]) else 28.0, 0.5)
        sns = c[4].checkbox("SNS投稿した", bool(int(r["SNS投稿"])) if exists else False)
        event = c[5].text_input("イベント", r["イベント"] if exists else "", placeholder="マルシェ出店 など")
        memo = st.text_input("メモ（気づき）", r["メモ"] if exists else "",
                             placeholder="例：雨で午後の客足が鈍い。クロワッサンは14時に売切れ。")
        st.markdown("##### 販売（プロダクト）　廃棄数は「製造数−販売数」で自動計算")
        active = ctx.products[pd.to_datetime(ctx.products["販売開始"], errors="coerce").fillna(pd.Timestamp("2000-01-01"))
                              <= pd.Timestamp(day)]["商品"].tolist()
        base = pd.DataFrame({"商品": active})
        if not cur_s.empty:
            base = base.merge(cur_s[["商品", "製造数", "販売数"]], on="商品", how="left")
        else:
            # 下書き：直近4回の同じ曜日の販売数の中央値 ×1.1 を製造数の初期値に
            hist = ctx.sales[pd.to_datetime(ctx.sales["日付"]).dt.weekday == day.weekday()]
            hist = hist[hist["日付"] < ds].sort_values("日付").groupby("商品").tail(4)
            med = hist.groupby("商品")["販売数"].median()
            base["製造数"] = [int(round(float(med.get(p, 10)) * 1.1)) for p in active]
            base["販売数"] = None
        base["製造数"] = pd.to_numeric(base["製造数"], errors="coerce").astype("Int64")
        base["販売数"] = pd.to_numeric(base["販売数"], errors="coerce").astype("Int64")
        st.caption("製造数の初期値は、直近4回の同じ曜日の販売数の中央値×1.1（下書き）。商品の追加は商品マスタ（products.csv）で。")
        h = st.columns([3, 2, 2])
        h[0].caption("商品")
        h[1].caption("製造数")
        h[2].caption("販売数（売れなかったら 0）")
        made_l, sold_l = [], []
        for j, r_ in base.iterrows():
            rc = st.columns([3, 2, 2], vertical_alignment="center")
            rc[0].markdown(r_["商品"])
            made_l.append(rc[1].number_input("製造数", 0, 9999, None if pd.isna(r_["製造数"]) else int(r_["製造数"]), 1,
                                             key=f"mk_{ds}_{j}", label_visibility="collapsed"))
            sold_l.append(rc[2].number_input("販売数", 0, 9999, None if pd.isna(r_["販売数"]) else int(r_["販売数"]), 1,
                                             key=f"sd_{ds}_{j}", label_visibility="collapsed", placeholder="販売数"))
        ok = st.form_submit_button("この日を保存", type="primary")
    if ok:
        ed = pd.DataFrame({"商品": base["商品"], "製造数": pd.array(made_l, dtype="Int64"),
                           "販売数": pd.array(sold_l, dtype="Int64")})
        if ed["販売数"].isna().any() or ed["製造数"].isna().any():
            st.error("製造数・販売数が空の商品があります（売れなかったら 0 を入れる）。")
        elif (ed["販売数"].fillna(0) > ed["製造数"].fillna(0)).any():
            st.error("販売数が製造数より多い商品があります。")
        else:
            if re.search(r"[一-龥ぁ-んァ-ヶ]{1,6}(さん|様|ちゃん|くん)", memo):
                st.warning("メモに人の名前らしき語があります。お客さまの名前は書かず「常連の方」などにしてください。")
            ed = ed.assign(日付=ds, 廃棄数=ed["製造数"] - ed["販売数"])
            ctx.store.add_day({"日付": ds, "天気": weather, "最高気温": temp, "客数": int(cust), "労働時間": labor,
                               "SNS投稿": int(sns), "イベント": event, "メモ": memo}, ed)
            st.toast("保存しました")
            st.rerun()

    # ---------------- 機械の提案 → 人の確認
    review = ds if exists else _latest_day(ctx, day)
    if review is None:
        return
    st.divider()
    st.markdown(f"#### 機械の提案：{review}（{C.WEEKDAYS[pd.Timestamp(review).weekday()]}）"
                + ("" if review == ds else "　※この日の日報がまだないので、直近の日を表示"))
    st.caption("基準＝直近4回の同じ曜日の中央値。機械は「いつもと違う」までしか言いません。"
               "**なぜ違うか・問題かどうかは人が決めます**（第3回：現状は、あるべき姿と比べて初めて問題になる）。")
    kr = ctx.k[ctx.k["日付"] == review].iloc[0]
    c = st.columns(5)
    c[0].metric("売上", yen(kr["売上"]))
    c[1].metric("粗利率", pct(kr["粗利率"]))
    c[2].metric("客数", f"{int(kr['客数'])}")
    c[3].metric("客単価", yen(kr["客単価"]))
    c[4].metric("廃棄率", pct(kr["廃棄率"]))

    flags = C.propose_flags(ctx.k, review, ctx.tol, ctx.waste_cap)
    checks = ctx.store.table("checks", C.CHECK_COLS)
    prev = checks[checks["日付"] == review].set_index("指標")
    flags["人の確認"] = [prev["人の確認"].get(m, C.CONFIRM_OK) if len(prev) else C.CONFIRM_OK for m in flags["指標"]]
    flags["ひとこと"] = [prev["ひとこと"].get(m, "") if len(prev) else "" for m in flags["指標"]]
    edf = st.data_editor(
        flags.drop(columns="key"), hide_index=True, width="stretch", key=f"flag_ed_{review}",
        disabled=["領域", "指標", "今日", "基準", "差", "機械の提案"],
        column_config={"人の確認": st.column_config.SelectboxColumn(options=C.CONFIRM_OPTS, required=True),
                       "ひとこと": st.column_config.TextColumn(help="なぜか（例：雨・マルシェ・仕込みミス）")})
    if st.button("確認を保存", key=f"save_flags_{review}"):
        rows = edf.assign(日付=review, 確定=[C.confirmed(p, c) for p, c in zip(edf["機械の提案"], edf["人の確認"])],
                          記録日時=now())
        ctx.store.upsert("checks", rows, C.CHECK_COLS, ["日付", "指標"])
        st.toast("確認を保存しました（毎週 /shuukei で使います）")

    st.markdown("##### 商品別の気づき（プロダクト）")
    pf = C.product_flags(ctx.sales, review, max(0.2, ctx.waste_cap))
    st.dataframe(pf, hide_index=True, width="stretch",
                 column_config={"廃棄率": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)})
    st.caption("売切れは「よいこと」に見えますが、需要はもっとあった（売り逃し）かもしれません。"
               "売切れ時刻をメモに残すと、/seizou で需要の推定に使えます。")
    if kr["メモ"]:
        st.info(f"📝 メモ：{kr['メモ']}")


# ============================================================ 毎週 /shuukei
def page_shuukei(ctx: Ctx):
    st.title("🔍 毎週 /shuukei（10分）")
    st.markdown("**② 問題を見つける。** 機械が **現状（As Is）** と **あるべき姿** の差を並べます。"
                "人は、どの **問題（Issue）** に取り組むかを選び、**課題（Action）** を「〜を明らかにする／改善する」の形で書きます。")
    need_data(ctx)
    wk = ctx.week_kpi()
    weeks = wk["週"].tolist()
    cur_ws = C.week_start(ctx.ref).isoformat()
    done = [w for w in weeks if w < cur_ws]          # 毎週のふりかえりは「終わった週」を既定にする
    default = done[-1] if done else weeks[-1]
    ws = st.selectbox("週（月曜はじまり）", weeks[::-1], index=weeks[::-1].index(default),
                      help="既定は基準日の前の週（終わった週）。今週の途中経過も選べます。")
    wk = wk.assign(**{"売上/営業日": wk["売上"] / wk["営業日"]})
    row = wk[wk["週"] == ws].iloc[0]
    i = weeks.index(ws)
    prev = wk.iloc[i - 1] if i > 0 else None

    c = st.columns(6)
    items = [("売上/営業日", "yen"), ("粗利率", "pct"), ("人時売上", "yen"), ("1日あたり客数", "int"), ("客単価", "yen"), ("廃棄率", "pct")]
    for col, (key, fmt) in zip(c, items):
        v, p = row[key], (prev[key] if prev is not None else None)
        col.metric(key, C.fmt_value(v, fmt), _delta(v, p, fmt) if prev is not None else None,
                   delta_color="inverse" if key == "廃棄率" else "normal")
    st.caption(f"営業日 {int(row['営業日'])} 日。比率は日ごとの率の平均ではなく、週の合計から計算し直しています。")

    end = (pd.Timestamp(ws) + timedelta(days=6)).date().isoformat()
    nm = C.new_members(ctx.members, ws, end)
    gap = C.gap_table(row, nm * 30 / 7, ctx.target)

    st.markdown("#### 現状 → あるべき姿 → 問題")
    st.dataframe(gap.drop(columns="_rel"), hide_index=True, width="stretch")
    issues = gap[gap["問題（Issue）"] == "あり"].sort_values("_rel", ascending=False)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### 日ごとの動き（この週）")
        kw = ctx.k[ctx.k["週"] == ws].copy()
        kw["日"] = kw["日付"].str[5:] + "（" + kw["曜日"] + "）"
        bars = alt.Chart(kw).mark_bar(color=DOMAIN_COLOR["経営"]).encode(
            x=alt.X("日:N", title=None, sort=list(kw["日"])), y=alt.Y("売上:Q", axis=alt.Axis(format=",.0f")),
            tooltip=["日", alt.Tooltip("売上:Q", format=",.0f"), "客数", "天気", "メモ"])
        wl = alt.Chart(kw).mark_line(point=True, color=DOMAIN_COLOR["プロダクト"]).encode(
            x=alt.X("日:N", sort=list(kw["日"])), y=alt.Y("廃棄率:Q", axis=alt.Axis(format=".0%", titleColor=DOMAIN_COLOR["プロダクト"])),
            tooltip=["日", alt.Tooltip("廃棄率:Q", format=".1%")])
        st.altair_chart(alt.layer(bars, wl).resolve_scale(y="independent").properties(height=240), width="stretch")
        st.caption("棒＝売上（左軸）、線＝廃棄率（右軸）。天気やメモはマウスを重ねると出ます。")
    with right:
        st.markdown("#### 商品の地図（この週）")
        pk = C.product_kpi(ctx.sales[ctx.sales["日付"].between(ws, end)], ctx.products)
        sc = alt.Chart(pk).mark_circle(opacity=0.8, color=DOMAIN_COLOR["プロダクト"]).encode(
            x=alt.X("販売数:Q"), y=alt.Y("廃棄率:Q", axis=alt.Axis(format=".0%")),
            size=alt.Size("廃棄金額:Q", legend=None, scale=alt.Scale(range=[60, 900])),
            tooltip=["商品", "販売数", alt.Tooltip("廃棄率:Q", format=".1%"), alt.Tooltip("廃棄金額:Q", format=",.0f"), "売切れ日"])
        txt = alt.Chart(pk).mark_text(dy=-14, fontSize=11, color="#333").encode(
            x="販売数:Q", y="廃棄率:Q", text="商品:N")
        rule = alt.Chart(pd.DataFrame({"y": [ctx.target.waste_rate]})).mark_rule(strokeDash=[6, 4]).encode(y="y:Q")
        st.altair_chart(alt.layer(sc, txt, rule).properties(height=240), width="stretch")
        st.caption("右上（よく売れるのに廃棄も多い）が、手を打つと効きやすい商品。円の大きさ＝廃棄金額。")

    checks = ctx.store.table("checks", C.CHECK_COLS)
    wc = checks[(checks["日付"] >= ws) & (checks["日付"] <= end) & (checks["確定"] == C.FLAG_WATCH)]
    st.markdown("#### 今週、人が「要確認」とした記録（毎日 /nippo から）")
    if wc.empty:
        st.caption("まだありません。/nippo で機械の提案を確認すると、ここに集まります。")
    else:
        st.dataframe(wc[["日付", "領域", "指標", "今日", "基準", "ひとこと"]], hide_index=True, width="stretch")

    st.divider()
    st.markdown("#### 人が決める：今週の課題（Action）")
    weekly = ctx.store.table("weekly", C.WEEK_COLS)
    if issues.empty:
        st.success("この週は、あるべき姿との差（問題）がありません。目標を上げるか、別の指標を見てみましょう。")
    opts = issues["指標"].tolist() or gap["指標"].tolist()
    with st.form(f"weekly_{ws}"):
        pick = st.selectbox("取り組む問題（差が大きい順に並べています）", opts)
        gr = gap.set_index("指標").loc[pick]
        dom = gr["領域"]
        act = st.text_area("課題（Action）", value=f"{pick}が目標に届かない原因を明らかにし、{ACTION_TEMPLATES[dom]}",
                           help="行動として書く：「〜を明らかにする」「〜を改善する」")
        if st.form_submit_button("今週の課題として保存", type="primary"):
            ctx.store.upsert("weekly", pd.DataFrame([{
                "週": ws, "領域": dom, "指標": pick, "現状": gr["現状（As Is）"], "あるべき姿": gr["あるべき姿"],
                "問題": f"差 {gr['差']}", "課題（Action）": act, "記録日時": now()}]), C.WEEK_COLS, ["週", "指標"])
            st.toast("保存しました")
            st.rerun()
    if len(weekly):
        st.dataframe(weekly.sort_values("週", ascending=False), hide_index=True, width="stretch")
        csv_download("課題の記録をCSVで保存", weekly, "weekly_actions.csv", "dl_weekly")

    note = weekly[weekly["週"] == ws]["課題（Action）"].tolist()
    md = C.report_markdown(f"週報 {ws} の週（スマートパン屋農家）", row, gap, " / ".join(note))
    with st.expander("📝 この週をMarkdownの報告書にする（第2回：ノートブックに貼れる）"):
        st.code(md, language="markdown")
        md_download("Markdownで保存", md, f"weekly_{ws}.md", "dl_weekly_md")


# ============================================================ 毎月 /tsuki
def page_tsuki(ctx: Ctx):
    st.title("🧭 毎月 /tsuki（30分）")
    st.markdown("**③ 打つ手を決める。** 機械は商品ごとの廃棄率を **ベイズ推定（90%区間）** し、前月より悪化した確率と"
                "**順番の目安** まで出します。人は **準備度** を答え、**順番・打つ手・担当（役割）・期限** を決め、"
                "3つの領域の **ロジックモデル** を更新します。")
    need_data(ctx)
    mk = ctx.month_kpi()
    months = mk["月"].tolist()
    mo_ref = ctx.ref.strftime("%Y-%m")
    mo = st.selectbox("月", months[::-1], index=months[::-1].index(mo_ref) if mo_ref in months else 0)
    mk = mk.assign(**{"売上/営業日": mk["売上"] / mk["営業日"]})
    row = mk[mk["月"] == mo].iloc[0]
    i = months.index(mo)
    prev = mk.iloc[i - 1] if i > 0 else None
    c = st.columns(6)
    for col, (key, fmt) in zip(c, [("売上/営業日", "yen"), ("粗利率", "pct"), ("人時売上", "yen"), ("1日あたり客数", "int"),
                                   ("客単価", "yen"), ("廃棄率", "pct")]):
        v, p = row[key], (prev[key] if prev is not None else None)
        col.metric(key, C.fmt_value(v, fmt), _delta(v, p, fmt) if prev is not None else None,
                   delta_color="inverse" if key == "廃棄率" else "normal")
    if mo == mo_ref:
        st.caption(f"今月は途中（営業日 {int(row['営業日'])} 日）。月の途中でも比べられるよう、売上は営業日あたりで表示しています。")

    # ---------------- ベイズ推定
    st.markdown("#### 商品ごとの廃棄率：ベイズ推定（Beta(1,1) 事前 × 製造数のうち廃棄の数）")
    wt = C.monthly_waste_table(ctx.sales, ctx.products, mo)
    if wt.empty:
        st.info("この月の販売データがありません。")
        return
    order = wt.sort_values("廃棄率（推定）", ascending=False)["商品"].tolist()
    base = alt.Chart(wt).encode(y=alt.Y("商品:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)))
    err = base.mark_rule(strokeWidth=3, color="#9aa5b1").encode(
        x=alt.X("90%区間_下:Q", title="廃棄率（点＝事後平均、線＝90%区間）", axis=alt.Axis(format=".0%")), x2="90%区間_上:Q")
    pt = base.mark_point(filled=True, size=90, color=DOMAIN_COLOR["プロダクト"]).encode(
        x="廃棄率（推定）:Q",
        tooltip=["商品", "製造数", "廃棄数", alt.Tooltip("廃棄率（推定）:Q", format=".1%"),
                 alt.Tooltip("P(前月より悪化):Q", format=".0%")])
    rule = alt.Chart(pd.DataFrame({"x": [ctx.target.waste_rate]})).mark_rule(strokeDash=[6, 4]).encode(x="x:Q")
    st.altair_chart(alt.layer(err, pt, rule).properties(height=40 * len(wt) + 40), width="stretch")
    st.caption("区間が点線（上限）をまたぐ商品は「上限を超えているとは言い切れない」。数が少ない新商品ほど区間が広くなります。")

    # ---------------- 優先度 → 人が順番を決める
    st.markdown("#### 人が決める：手を打つ順番")
    w = st.slider("悪化の確率をどれだけ重く見るか（w）", 0.0, 3.0, 1.0, 0.5,
                  help="優先度 = 廃棄金額 × (1 − 準備度/3) × (1 + w × max(0, P(悪化) − 0.5))。重みに正解はありません。")
    monthly = ctx.store.table("monthly", C.MONTH_COLS)
    saved = monthly[monthly["月"] == mo].set_index("商品")
    ready_lbl = list(C.READY.values())
    t = wt[["商品", "廃棄率（推定）", "P(前月より悪化)", "廃棄金額", "売切れ日"]].copy()
    t["準備度"] = [saved["準備度"].get(p, ready_lbl[0]) if len(saved) else ready_lbl[0] for p in t["商品"]]
    t["優先度の目安"] = [C.priority(l, ready_lbl.index(r) if r in ready_lbl else 0, pu, w)
                     for l, r, pu in zip(t["廃棄金額"], t["準備度"], t["P(前月より悪化)"])]
    t["機械の順位"] = t["優先度の目安"].rank(ascending=False, method="first").astype(int)
    t = t.sort_values("機械の順位")
    t["人が決めた順位"] = [int(saved["人が決めた順位"].get(p)) if len(saved) and str(saved["人が決めた順位"].get(p, "")).isdigit()
                     else m for p, m in zip(t["商品"], t["機械の順位"])]
    for col, default in (("打つ手", WASTE_ACTIONS[0]), ("担当（役割）", "製造担当"), ("期限", ""), ("入れ替えた理由", "")):
        t[col] = [saved[col].get(p, default) if len(saved) else default for p in t["商品"]]
    ed = st.data_editor(
        t, hide_index=True, width="stretch", key=f"tsuki_ed_{mo}_{w}",
        disabled=["商品", "廃棄率（推定）", "P(前月より悪化)", "廃棄金額", "売切れ日", "優先度の目安", "機械の順位"],
        column_config={
            "廃棄率（推定）": st.column_config.NumberColumn(format="percent"),
            "P(前月より悪化)": st.column_config.NumberColumn(format="percent"),
            "廃棄金額": st.column_config.NumberColumn(format="¥%d"),
            "優先度の目安": st.column_config.NumberColumn(format="%.0f"),
            "準備度": st.column_config.SelectboxColumn(options=ready_lbl, required=True),
            "人が決めた順位": st.column_config.NumberColumn(min_value=1, step=1),
            "打つ手": st.column_config.SelectboxColumn(options=WASTE_ACTIONS + ["（その他：理由欄に書く）"]),
            "担当（役割）": st.column_config.TextColumn(help="名前ではなく役割で（製造担当・販売担当・代表 など）"),
        })
    st.caption("準備度：0 手がない／1 担当は決まっている／2 手順が書いてある／3 試して効いた（3なら優先度は0）。"
               "**機械が出すのは提案順まで。順番を決めるのは人**（入れ替えたら理由を残す）。")
    if st.button("今月の決定を保存", type="primary", key=f"save_m_{mo}"):
        ctx.store.upsert("monthly", ed.assign(月=mo, 記録日時=now()), C.MONTH_COLS, ["月", "商品"])
        st.toast("保存しました")
        st.rerun()

    # ---------------- ロジックモデル
    st.markdown("#### 人が決める：3つの領域のロジックモデル（第3回）")
    st.caption("「やったこと（アウトプット）」と「良くなったこと（アウトカム）」を分けて書く。"
               "評価したいのはアウトカム（例：10回投稿した、ではなく、再来店率が上がったか）。")
    logic = ctx.store.table("logic", C.LOGIC_COLS)
    tabs = st.tabs([f"{C.DOMAIN_ICON[d]} {d}" for d in C.DOMAINS])
    kpi_opts = ["売上", "粗利率", "人時売上", "1日あたり客数", "客単価", "新規会員", "再来店率", "廃棄率", "売切れ率", "自家原料比率"]
    for tab, dom in zip(tabs, C.DOMAINS):
        with tab:
            sv = logic[(logic["月"] == mo) & (logic["領域"] == dom)]
            ex = C.LOGIC_EXAMPLES[dom]
            vals = sv.iloc[0][["投入", "活動", "アウトプット", "アウトカム"]].tolist() if len(sv) else ex
            with st.form(f"logic_{mo}_{dom}"):
                cc = st.columns(4)
                new = [cc[j].text_area(lbl, vals[j], height=110, key=f"lg_{mo}_{dom}_{j}")
                       for j, lbl in enumerate(["投入", "→ 活動", "→ 結果（アウトプット）", "→ 成果（アウトカム）"])]
                kpi = st.selectbox("成果を測る指標（このダッシュボードの数字）", kpi_opts,
                                   index=kpi_opts.index(sv.iloc[0]["成果指標"]) if len(sv) and sv.iloc[0]["成果指標"] in kpi_opts
                                   else {"経営": 2, "マーケティング": 6, "プロダクト": 7}[dom], key=f"lgk_{mo}_{dom}")
                if st.form_submit_button("ロジックモデルを保存"):
                    ctx.store.upsert("logic", pd.DataFrame([{"月": mo, "領域": dom, "投入": new[0], "活動": new[1],
                                                             "アウトプット": new[2], "アウトカム": new[3],
                                                             "成果指標": kpi, "記録日時": now()}]),
                                     C.LOGIC_COLS, ["月", "領域"])
                    st.toast("保存しました")

    # ---------------- ふりかえり
    st.markdown("#### ふりかえり：前月に決めた手と、今月の廃棄率")
    if prev is None:
        st.caption("前月のデータがありません。")
        return
    pm = prev["月"]
    pdec = monthly[monthly["月"] == pm]
    pw = C.monthly_waste_table(ctx.sales, ctx.products, pm)[["商品", "廃棄率（推定）"]].rename(columns={"廃棄率（推定）": f"{pm} の廃棄率"})
    cmp = pw.merge(wt[["商品", "廃棄率（推定）", "P(前月より悪化)"]].rename(columns={"廃棄率（推定）": f"{mo} の廃棄率"}), on="商品", how="outer")
    if len(pdec):
        cmp = cmp.merge(pdec[["商品", "人が決めた順位", "打つ手"]].rename(columns={"打つ手": f"{pm} に決めた手"}), on="商品", how="left")
    else:
        st.caption(f"{pm} の決定はまだ記録されていません（サンプルでは、この月に決めて保存すると翌月ここに並びます）。")
    st.dataframe(cmp, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="percent") for c in cmp.columns if "廃棄率" in c or "P(" in c})
    st.warning("並べているのは **前後関係** であって、手が効いた証明ではありません（天気・季節・新商品も同時に変わる）。"
               "効いたかを確かめたいときは、⑤（因果の目）や⑥（A/B）の考え方を使います。")
