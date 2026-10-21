"""学ぶ（講義 第1〜3回）を、スマートパン屋農家の題材で手を動かして確かめる

    ① 第1回 DSとは・必要なスキル（ビジネス力／データサイエンス力／データエンジニアリング力、ソフトスキル）
    ② 第2回 DSプロセス（6フェイズ）・Colab と pandas・Markdown で報告書の形にする
    ③ 第3回 DS設計（現状→問題→課題、逆算、ロジックモデル）・オープンデータ・秘密情報と個人情報
"""
from __future__ import annotations

from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

import bakery_core as C
from views.common import DOMAIN_COLOR, Ctx, link, md_download, need_data, now, pct, yen


# ============================================================ ① 第1回
def page_kai1(ctx: Ctx):
    st.title("1️⃣ DSとは・必要なスキル（第1回）")
    st.markdown("**データサイエンス（DS）** ＝ データから課題解決に役立つ知見を引き出し、行動につなげる一連のプロセス。"
                "スマートパン屋農家の「スマート化」とは、**畑 → パン → お客さま** の流れを、データで毎日少しずつ良くすることです。")
    st.markdown("#### 関連用語を、自分のプロジェクトの言葉に置き換える")
    st.dataframe(C.DX_TERMS, hide_index=True, width="stretch")

    st.markdown("#### DSに必要な3つのスキル：今の自分（チーム）と、このプロジェクトで必要な水準")
    st.caption("1＝これから／3＝手伝いがあればできる／5＝ひとりでできる。数字に正解はありません。差の大きいところが次に伸ばすところ。")
    rows = []
    for name, desc in C.SKILLS.items():
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.markdown(f"**{name}**　{desc}")
        now_ = c2.slider("今", 1, 5, 2 if name != "ビジネス力" else 3, key=f"sk_now_{name}")
        need = c3.slider("必要", 1, 5, 4, key=f"sk_need_{name}")
        rows += [{"スキル": name, "区分": "今", "水準": now_}, {"スキル": name, "区分": "必要", "水準": need}]
    sk = pd.DataFrame(rows)
    ch = alt.Chart(sk).mark_bar().encode(
        y=alt.Y("スキル:N", title=None, axis=alt.Axis(labelLimit=220)),
        x=alt.X("水準:Q", scale=alt.Scale(domain=[0, 5]), axis=alt.Axis(tickMinStep=1)),
        yOffset="区分:N", color=alt.Color("区分:N", scale=alt.Scale(domain=["今", "必要"], range=["#2a78d6", "#c9d6e3"]),
                                         legend=alt.Legend(orient="top", title=None)),
        tooltip=["スキル", "区分", "水準"])
    st.altair_chart(ch.properties(height=alt.Step(18)), width="stretch")
    gaps = sk.pivot(index="スキル", columns="区分", values="水準").assign(差=lambda d: d["必要"] - d["今"]).sort_values("差", ascending=False)
    top = gaps.index[0]
    hint = {"ビジネス力": "毎週 /shuukei で「問題（Issue）」を自分の言葉で書く練習から。",
            "データサイエンス力": "深掘り ④〜⑥（新聞売り子・因果・ベイズ）の説明を読み、数字を動かしてみる。",
            "データエンジニアリング力": "日報を「手元のファイル」で毎日同じ形式で溜める（データ準備はDSの時間の約半分）。"}
    st.info(f"いちばん差が大きいのは **{top}**（差 {gaps.loc[top, '差']}）。次の一歩：{hint[top]}")

    st.markdown("#### 3つのスキル × 3つの領域：このダッシュボードでは何をするか")
    st.dataframe(pd.DataFrame({
        "領域": C.DOMAINS,
        "ビジネス力": ["粗利・人時売上の目標を決める", "誰に来てほしいか（ターゲット）を言葉にする", "看板商品と、やめる商品を決める"],
        "データサイエンス力": ["曜日・天気の波を除いて比べる", "SNS投稿の効果を交絡に注意して測る", "廃棄率を区間で語る・製造数を最適化"],
        "データエンジニアリング力": ["日報と販売表を日付で結合", "会員台帳を匿名化して溜める", "商品マスタ（単価・原価）を保守する"],
    }), hide_index=True, width="stretch")

    st.markdown("#### [Soft Skills] チームでDSを進めるための個人資質")
    ss = {s: st.select_slider(s, ["これから", "ときどき", "いつも"], "ときどき", key=f"soft_{i}") for i, s in enumerate(C.SOFT_SKILLS)}
    md = "## 第1回 自己チェック（スマートパン屋農家）\n\n| スキル | 今 | 必要 | 差 |\n|:---|---:|---:|---:|\n"
    md += "".join(f"| {s} | {r['今']} | {r['必要']} | {r['差']} |\n" for s, r in gaps.iterrows())
    md += "\n### ソフトスキル\n" + "".join(f"- {k}：{v}\n" for k, v in ss.items())
    md_download("自己チェックをMarkdownで保存（ノートブックの自己紹介に貼れる）", md, "kai1_selfcheck.md", "dl_k1")


# ============================================================ ② 第2回
def page_kai2(ctx: Ctx):
    st.title("2️⃣ DSプロセスとMarkdown報告（第2回）")
    st.markdown("DSプロセスの型：**業務理解 → データ理解 → データ準備 → モデリング → 評価 → 展開**。"
                "一般に **データ準備がいちばん時間がかかる**（目安で全体の約半分）。")
    ph = C.PHASES
    ch = alt.Chart(ph).mark_bar(color="#3d6b3a").encode(
        x=alt.X("所要時間の目安(%):Q"), y=alt.Y("フェイズ:N", sort=list(ph["フェイズ"]), title=None),
        tooltip=list(ph.columns))
    txt = ch.mark_text(align="left", dx=4, color="#333").encode(text="所要時間の目安(%):Q")
    c1, c2 = st.columns([3, 2])
    c1.dataframe(ph, hide_index=True, width="stretch")
    c2.altair_chart((ch + txt).properties(height=210), width="stretch")

    st.markdown("#### 3つの領域は、いまどのフェイズか（進み具合を記録）")
    saved = ctx.store.table("phases", ["フェイズ"] + C.DOMAINS)
    if saved.empty:
        saved = pd.DataFrame({"フェイズ": ph["フェイズ"],
                              "経営": ["済み", "済み", "進行中", "未着手", "未着手", "未着手"],
                              "マーケティング": ["済み", "進行中", "未着手", "未着手", "未着手", "未着手"],
                              "プロダクト": ["済み", "済み", "済み", "進行中", "未着手", "未着手"]})
    ed = st.data_editor(saved, hide_index=True, width="stretch", disabled=["フェイズ"], key="phase_ed",
                        column_config={d: st.column_config.SelectboxColumn(options=C.PHASE_STATUS, required=True) for d in C.DOMAINS})
    cols = st.columns(3)
    for col, d in zip(cols, C.DOMAINS):
        score = sum({"済み": 1, "進行中": 0.5}.get(x, 0) for x in ed[d]) / len(ed)
        nxt = next((f for f, s in zip(ed["フェイズ"], ed[d]) if s != "済み"), "（すべて済み）")
        col.progress(score, text=f"{C.DOMAIN_ICON[d]} {d}：{score*100:.0f}%　次は「{nxt}」")
    if st.button("進み具合を保存", key="save_phase"):
        ctx.store.save("phases", ed)
        st.toast("保存しました")

    need_data(ctx)
    st.markdown("#### Colab の演習を、このプロジェクトのデータで（pandas で小さな表を作る）")
    st.caption("演習ノートブックの `scores = [72, 85, 90, 64, 78]` を、直近5営業日の客数に置き換えたもの。下の結果はこの場で計算しています。")
    last5 = ctx.k.tail(5)
    scores = [int(x) for x in last5["客数"]]
    code1 = (f"scores = {scores}   # 直近5営業日の客数\nmean = sum(scores) / len(scores)\n"
             "print(\"データ:\", scores)\nprint(\"個数:\", len(scores))\nprint(\"平均:\", mean)")
    st.code(code1, language="python")
    st.code(f"データ: {scores}\n個数: {len(scores)}\n平均: {sum(scores)/len(scores)}", language="text")

    day = ctx.k["日付"].iloc[-1]
    s = ctx.sales[ctx.sales["日付"] == day][["商品", "製造数", "販売数", "廃棄数"]].reset_index(drop=True)
    code2 = ("import pandas as pd\n\n"
             f"df = pd.DataFrame({{\n    \"商品\": {s['商品'].tolist()},\n    \"製造数\": {s['製造数'].astype(int).tolist()},\n"
             f"    \"販売数\": {s['販売数'].astype(int).tolist()},\n}})\n"
             "df[\"廃棄数\"] = df[\"製造数\"] - df[\"販売数\"]\n"
             "print(\"廃棄の合計:\", df[\"廃棄数\"].sum())\n"
             "print(\"いちばん売れた商品:\", df.loc[df[\"販売数\"].idxmax(), \"商品\"])")
    st.code(code2, language="python")
    st.dataframe(s, hide_index=True, width="stretch")
    st.code(f"廃棄の合計: {int(s['廃棄数'].sum())}\nいちばん売れた商品: {s.loc[s['販売数'].astype(int).idxmax(), '商品']}", language="text")
    st.caption(f"（{day} の販売表）")

    st.markdown("#### Markdown で「何のために・何をして・何が分かったか」を書く")
    weeks = ctx.week_kpi()
    row = weeks.iloc[-1]
    ws = row["週"]
    end = (pd.Timestamp(ws) + timedelta(days=6)).date().isoformat()
    gap = C.gap_table(row, C.new_members(ctx.members, ws, end) * 30 / 7, ctx.target)
    note = st.text_input("次にやること（課題）", "廃棄率が目標を超える商品について、曜日・天気との関係を明らかにする")
    md = C.report_markdown(f"週報 {ws} の週", row, gap, note)
    a, b = st.columns(2)
    with a:
        st.caption("書き方（Markdown）")
        st.code(md, language="markdown")
    with b:
        st.caption("表示のされ方")
        with st.container(border=True):
            st.markdown(md)
    md_download("Markdownで保存", md, f"report_{ws}.md", "dl_k2")
    st.caption("見出し `##`、箇条書き `- `、表 `| 列 |` と `|---|`。ノートブックのテキストセルにそのまま貼れます。")


# ============================================================ ③ 第3回
def page_kai3(ctx: Ctx):
    st.title("3️⃣ DS設計・オープンデータ・個人情報（第3回）")
    st.markdown("**分析を始める前に、何のために・何を・どう分析するかを決める回。** 設計はデータを触る前に行い、"
                "**作りたい料理から材料を決める**（逆算）。")
    t1, t2, t3, t4 = st.tabs(["📝 DS設計シート（第一段階）", "➡️ ロジックモデル", "🌐 オープンデータ", "🔒 秘密情報と個人情報"])

    with t1:
        st.markdown("##### 現状／問題／課題の違い（スマートパン屋農家の例）")
        need_data(ctx)
        mk = ctx.month_kpi()
        last = mk.iloc[-2] if len(mk) > 1 else mk.iloc[-1]   # 終わった月
        st.dataframe(pd.DataFrame([
            ["現状（As Is）", "今起きている事実", f"{last['月']} の廃棄率は {pct(last['廃棄率'])}"],
            ["問題（Issue）", "あるべき姿との差", f"上限 {pct(ctx.target.waste_rate)} より {(last['廃棄率'] - ctx.target.waste_rate)*100:+.1f}pt"],
            ["課題（Action）", "差を埋めるために取り組むこと（行動として書く）", "廃棄が増える条件を明らかにし、製造数の決め方を改善する"],
        ], columns=["用語", "意味", "このデータでは"]), hide_index=True, width="stretch")
        st.caption("「廃棄が多い」だけではまだ問題ではありません。あるべき姿（サイドバーの目標）と比べて、初めて問題になります。")

        dom = st.radio("設計する領域", C.DOMAINS, horizontal=True, key="design_dom",
                       format_func=lambda d: f"{C.DOMAIN_ICON[d]} {d}")
        saved = ctx.store.table("design", ["領域", "仮タイトル"] + [k for k, _ in C.DESIGN_ITEMS] + ["記録日時"])
        sv = saved[saved["領域"] == dom]
        ex = C.DESIGN_EXAMPLES[dom]
        cur = {k: (sv.iloc[0][k] if len(sv) else ex[k]) for k, _ in C.DESIGN_ITEMS}

        st.markdown("##### 逆算の順番：右から左へ（ゴール → ほしい分析結果 → 分析手法 → データ処理 → データ）")
        flow = st.columns(len(C.BACKWARD))
        food = {"ゴール": "誰に何を食べさせたい？", "ほしい分析結果": "どんな料理？", "分析手法": "どんな調理法？",
                "データ処理": "下ごしらえ", "使うデータ": "材料"}
        for j, key in enumerate(C.BACKWARD[::-1]):
            n = len(C.BACKWARD) - j
            with flow[j].container(border=True):
                st.markdown(f"**{n}. {key}**")
                st.caption(f"料理なら：{food[key]}")
                st.markdown(f"<small>{cur[key]}</small>", unsafe_allow_html=True)
        st.caption("番号の順（右端の 1.ゴール → 左端の 5.使うデータ）に決める。「冷蔵庫にある材料で何か作る」のではなく「作りたい料理から材料を決める」。")
        with st.form(f"design_{dom}"):
            title = st.text_input("仮タイトル", sv.iloc[0]["仮タイトル"] if len(sv) else
                                  {"経営": "雨の平日に人時売上が落ちるのはなぜか", "マーケティング": "SNSは本当に客を連れてきているか",
                                   "プロダクト": "廃棄と売り逃しの釣り合う製造数はいくつか"}[dom])
            vals = {}
            order = ["ゴール", "ほしい分析結果", "分析手法", "データ処理", "使うデータ"]
            rest = [k for k, _ in C.DESIGN_ITEMS if k not in order]
            labels = dict(C.DESIGN_ITEMS)
            st.markdown("**① 逆算の5項目（先に埋める）**")
            for key in order:
                vals[key] = st.text_area(labels[key], cur[key], height=68, key=f"dz_{dom}_{key}")
            st.markdown("**② 残りの項目**")
            for key in rest:
                vals[key] = st.text_area(labels[key], cur[key], height=68, key=f"dz_{dom}_{key}")
            if st.form_submit_button("設計シートを保存", type="primary"):
                ctx.store.upsert("design", pd.DataFrame([{"領域": dom, "仮タイトル": title, **vals, "記録日時": now()}]),
                                 list(saved.columns), ["領域"])
                st.toast("保存しました")
                cur, sv = vals, pd.DataFrame([{"仮タイトル": title}])
        md = C.design_markdown(dom, cur, sv.iloc[0]["仮タイトル"] if len(sv) else "")
        with st.expander("📋 ノートブックの「課題C」に貼る Markdown"):
            st.code(md, language="markdown")
        md_download("設計シートをMarkdownで保存", md, f"design_{dom}.md", f"dl_design_{dom}")
        st.caption("第一段階は「書けたところまで」で大丈夫。第4回のPBL課題設定で、チーム・教員と一緒に直します。")

    with t2:
        st.markdown("##### やったこと（アウトプット）と、良くなったこと（アウトカム）を分ける")
        rows = [[d] + C.LOGIC_EXAMPLES[d] for d in C.DOMAINS]
        st.dataframe(pd.DataFrame(rows, columns=["領域", "投入", "→ 活動", "→ 結果（アウトプット）", "→ 成果（アウトカム）"]),
                     hide_index=True, width="stretch")
        st.caption("設計シートの「評価指標②（業務面の効果）」が、このアウトカムを書く欄。")
        link(ctx, "tsuki", "毎月 /tsuki でロジックモデルを更新する", "🧭")

    with t3:
        st.markdown("##### 手持ちデータ × オープンデータで、比べる・揃える")
        st.dataframe(C.OPEN_DATA, hide_index=True, width="stretch")
        st.markdown("##### 使う前のチェック")
        chk = ctx.store.table("opendata", ["入手先"] + C.OPEN_DATA_CHECKS)
        if chk.empty:
            chk = pd.DataFrame({"入手先": C.OPEN_DATA["入手先"], **{c: False for c in C.OPEN_DATA_CHECKS}})
        else:
            for c in C.OPEN_DATA_CHECKS:
                chk[c] = chk[c].astype(str).isin(["True", "true", "1"])
        ed = st.data_editor(chk, hide_index=True, width="stretch", disabled=["入手先"], key="od_ed",
                            column_config={c: st.column_config.CheckboxColumn() for c in C.OPEN_DATA_CHECKS})
        if st.button("チェックを保存", key="save_od"):
            ctx.store.save("opendata", ed)
            st.toast("保存しました")
        done = ed[C.OPEN_DATA_CHECKS].all(axis=1)
        st.caption(f"4項目すべて確認済み：{int(done.sum())} / {len(ed)} 件。"
                   "このダッシュボードはオープンデータを自動取得しません（入手先で利用条件を確かめてから、手元で結合）。")

    with t4:
        st.markdown("##### 匿名化の限界：名前を消しても、組合せで誰か分かることがある")
        st.caption("会員台帳には氏名・電話番号を入れていません。それでも「地区×年代×性別」のように条件を重ねると、"
                   "少人数の組合せでは本人が特定できてしまうことがあります（k-匿名性：どの組合せにも k 人以上いるか）。")
        if ctx.members.empty:
            st.info("会員台帳がありません。")
        else:
            q = st.multiselect("組み合わせる属性（準識別子）", ["年代", "性別", "地区", "認知経路"], ["年代", "性別", "地区"])
            kk = st.slider("k（最低人数）", 2, 10, 3)
            c1, c2 = st.columns(2)
            ga = c1.checkbox("地区を大きな区分にまとめる（西条／西条周辺／郊外）")
            gg = c2.checkbox("年代を2区分ずつにまとめる（20〜30代 など）")
            m = ctx.members
            if ga:
                m = C.generalize(m, "地区", C.AREA_COARSE)
            if gg:
                m = C.generalize(m, "年代", C.AGE_COARSE)
            kmin, risky = C.k_anonymity(m, q, kk)
            a, b, c = st.columns(3)
            a.metric("会員数", f"{len(m)} 人")
            b.metric("いちばん少ない組合せの人数", f"{kmin} 人")
            c.metric(f"{kk}人未満の組合せ", f"{len(risky)} 組", help="この組合せの人は、外に出すと特定されるおそれ")
            if len(risky):
                st.dataframe(risky, hide_index=True, width="stretch")
                st.warning("このままでは外部（発表資料・外部のAI・SNS）に出せません。属性をまとめる・列を落とす・少人数は「その他」にする。")
            else:
                st.success(f"どの組合せにも {kk} 人以上います（この属性の組合せに限って）。")
        st.markdown("##### この授業・このプロジェクトでのルール")
        st.markdown("- 預かったデータ（会員台帳・取引先の情報）を **SNSや外部のAIに安易に貼り付けない**\n"
                    "- 決められた保存場所（手元の `data/raw/`、`.gitignore` 済み）以外に置かない。公開サーバーには架空サンプルだけ\n"
                    "- 日報のメモに、お客さま・取引先の名前を書かない（/nippo で人名らしき語を警告）\n"
                    "- 担当は名前ではなく役割で書く（製造担当・販売担当・代表）\n"
                    "- 企業などから預かった非公開データは、秘密保持契約（NDA）に従う")
