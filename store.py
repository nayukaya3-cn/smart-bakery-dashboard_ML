"""記録の置き場所

- 手元ファイル（persist=True）: data/raw/ 以下に保存（.gitignore 済み・リポジトリに入らない）
    data/raw/daily.csv              日報（1営業日1行：天気・客数・労働時間・SNS投稿・メモ）
    data/raw/sales.csv              販売表（1営業日×商品：製造数・販売数・廃棄数）
    data/raw/members.csv            会員台帳（氏名・連絡先は入れない。会員IDと属性だけ）
    data/raw/products.csv           商品マスタ（無ければサンプルの商品マスタを使う）
    data/raw/routine/checks.csv     毎日：機械の提案への OK／直し
    data/raw/routine/weekly.csv     毎週：選んだ問題と課題（Action）
    data/raw/routine/monthly.csv    毎月：準備度・人が決めた順番・打つ手
    data/raw/routine/logic.csv      毎月：ロジックモデル
    data/raw/routine/design.csv     第3回：DS設計シート
- サンプル・アップロード（persist=False）: ブラウザのセッション内だけ（CSVで保存可）
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import bakery_core as C

RAW_DIR = C.DATA_DIR / "raw"
FILES = {"daily": C.DAILY_COLS, "sales": C.SALES_COLS, "members": C.MEMBER_COLS, "products": C.PRODUCT_COLS}


class Store:
    def __init__(self, persist: bool, root: Path = RAW_DIR):
        self.persist = persist
        self.root = root
        self.rdir = root / "routine"
        if persist:
            self.rdir.mkdir(parents=True, exist_ok=True)
        st.session_state.setdefault("_store", {})
        st.session_state.setdefault("_added", {})

    # ------------------------------------------------------------ 記録の表（ルーティン）
    def table(self, name: str, cols: list[str]) -> pd.DataFrame:
        if self.persist:
            p = self.rdir / f"{name}.csv"
            if p.exists():
                t = pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                return t.reindex(columns=cols, fill_value="")
            return pd.DataFrame(columns=cols)
        return st.session_state["_store"].get(name, pd.DataFrame(columns=cols)).copy()

    def save(self, name: str, t: pd.DataFrame):
        if self.persist:
            t.to_csv(self.rdir / f"{name}.csv", index=False, encoding="utf-8-sig")
        else:
            st.session_state["_store"][name] = t.copy()

    def upsert(self, name: str, rows: pd.DataFrame, cols: list[str], keys: list[str]):
        """同じキーの行は置き換え、新しい行は足す"""
        t = pd.concat([self.table(name, cols), rows.reindex(columns=cols).astype(str)], ignore_index=True)
        self.save(name, t.drop_duplicates(keys, keep="last").reset_index(drop=True))

    # ------------------------------------------------------------ 日報・販売の追記（毎日）
    def added(self, kind: str) -> pd.DataFrame:
        return st.session_state["_added"].get(kind, pd.DataFrame(columns=FILES[kind]))

    def add_day(self, daily_row: dict, sales_rows: pd.DataFrame):
        """1営業日分を保存（同じ日付があれば置き換え）"""
        d = pd.DataFrame([daily_row], columns=C.DAILY_COLS)
        s = sales_rows.reindex(columns=C.SALES_COLS)
        day = daily_row["日付"]
        if self.persist:
            ensure_files()
            for kind, new in (("daily", d), ("sales", s)):
                p = RAW_DIR / f"{kind}.csv"
                old = pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                old = old[old["日付"] != day]
                pd.concat([old, new.astype(str)], ignore_index=True).to_csv(p, index=False, encoding="utf-8-sig")
        else:
            for kind, new in (("daily", d), ("sales", s)):
                old = self.added(kind)
                old = old[old["日付"] != day]
                st.session_state["_added"][kind] = pd.concat([old, new], ignore_index=True)


def ensure_files():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for kind, cols in FILES.items():
        p = RAW_DIR / f"{kind}.csv"
        if not p.exists():
            base = C.PRODUCTS if kind == "products" else pd.DataFrame(columns=cols)
            base.to_csv(p, index=False, encoding="utf-8-sig")


def read_local():
    ensure_files()
    rd = lambda n: pd.read_csv(RAW_DIR / f"{n}.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")  # noqa: E731
    return (C.clean_daily(rd("daily")), C.clean_sales(rd("sales")), C.clean_members(rd("members")),
            C.clean_products(rd("products")))
