"""ページ間で共有する文脈（Ctx）と表示部品"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
import streamlit as st

import bakery_core as C

DOMAIN_COLOR = {"経営": "#2a78d6", "マーケティング": "#eb6834", "プロダクト": "#1baf7a"}
FLAG_COLOR = {C.FLAG_WATCH: "#d03b3b", C.FLAG_GOOD: "#1baf7a", C.FLAG_NORMAL: "#9aa5b1"}


@dataclass
class Ctx:
    daily: pd.DataFrame
    sales: pd.DataFrame
    members: pd.DataFrame
    products: pd.DataFrame
    k: pd.DataFrame                  # 1日1行のKPI
    ref: date
    target: C.Target
    store: object
    is_sample: bool
    tol: float = 0.15
    waste_cap: float = 0.15
    pages: dict = field(default_factory=dict)

    @property
    def days(self) -> set:
        return set(self.daily["日付"])

    def month_kpi(self) -> pd.DataFrame:
        return C.period_kpi(self.k, "月")

    def week_kpi(self) -> pd.DataFrame:
        return C.period_kpi(self.k, "週")


def link(ctx: Ctx, name: str, label: str, icon: str | None = None):
    if name in ctx.pages:
        st.page_link(ctx.pages[name], label=label, icon=icon)


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def yen(v) -> str:
    return C.fmt_value(v, "yen")


def pct(v) -> str:
    return C.fmt_value(v, "pct")


def metric(col, label, value, delta=None, help=None):
    col.metric(label, value, delta, delta_color="off" if delta and not str(delta).startswith(("+", "-")) else "normal",
               help=help)


def need_data(ctx: Ctx):
    if ctx.k.empty:
        st.info("まだ日報がありません。「毎日 /nippo」で1日分を書くと、ここで分析できます。")
        link(ctx, "nippo", "書く /nippo", "✍️")
        st.stop()


def md_download(label: str, text: str, fname: str, key: str):
    st.download_button(label, text.encode("utf-8"), file_name=fname, mime="text/markdown", key=key)


def csv_download(label: str, df: pd.DataFrame, fname: str, key: str):
    st.download_button(label, df.to_csv(index=False).encode("utf-8-sig"), file_name=fname, mime="text/csv", key=key)
