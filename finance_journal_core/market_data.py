from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import tushare as ts


TOKEN_ENV_KEYS = ("TUSHARE_TOKEN", "TS_TOKEN")


def normalize_ts_code(value: str) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return raw
    if "." in raw:
        return raw
    if re.fullmatch(r"\d{6}", raw):
        if raw.startswith(("600", "601", "603", "605", "688", "689", "900")):
            return f"{raw}.SH"
        if raw.startswith(("000", "001", "002", "003", "200", "300", "301")):
            return f"{raw}.SZ"
        if raw.startswith(("430", "440", "830", "831", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "874", "875", "876", "877", "878", "879")):
            return f"{raw}.BJ"
    return raw


def normalize_trade_date(value: str | date | datetime | None) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if not text:
        return ""
    text = text.split("T", 1)[0].split(" ", 1)[0].replace("-", "").replace("/", "")
    if len(text) == 8 and text.isdigit():
        return text
    raise ValueError(f"invalid trade date: {value}")


def to_date(value: str | date | datetime) -> date:
    token = normalize_trade_date(value)
    return datetime.strptime(token, "%Y%m%d").date()


def shift_calendar_date(value: str | date | datetime, days: int) -> str:
    return (to_date(value) + timedelta(days=days)).strftime("%Y%m%d")


def normalize_datetime_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip().replace("/", "-")
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]} 00:00:00"
    if re.fullmatch(r"\d{14}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]} {text[8:10]}:{text[10:12]}:{text[12:14]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text} 00:00:00"
    return text


def safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TushareMarketData:
    def __init__(self, token: str | None = None, timeout: int = 30):
        self.token = token
        self.timeout = timeout

    def _read_token(self) -> str:
        if self.token:
            return self.token.strip()
        for key in TOKEN_ENV_KEYS:
            value = os.getenv(key, "").strip()
            if value:
                return value
        raise RuntimeError("Tushare token is missing. Set TUSHARE_TOKEN or TS_TOKEN first.")

    def _client(self):
        return ts.pro_api(self._read_token(), timeout=self.timeout)

    def call_endpoint(self, endpoint: str, fields: str = "", **params: Any) -> pd.DataFrame:
        clean_params = {key: value for key, value in params.items() if value not in (None, "")}
        if fields:
            clean_params["fields"] = fields
        try:
            client = self._client()
            func = getattr(client, endpoint, None)
            if callable(func):
                result = func(**clean_params)
            else:
                result = client.query(endpoint, **clean_params)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Tushare endpoint {endpoint} failed: {exc}") from exc
        if not isinstance(result, pd.DataFrame):
            raise RuntimeError(f"Tushare endpoint {endpoint} returned an unexpected payload.")
        return result

    def resolve_stock(self, symbol_or_name: str) -> dict[str, Any]:
        query = str(symbol_or_name or "").strip()
        normalized = normalize_ts_code(query)
        symbol = normalized.split(".", 1)[0]
        df = self.call_endpoint(
            "stock_basic",
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )
        df = df.fillna("")
        exact = df[
            (df["ts_code"].str.upper() == normalized)
            | (df["symbol"] == symbol)
            | (df["name"] == query)
        ]
        if exact.empty and query and not query.isdigit():
            exact = df[df["name"].astype(str).str.contains(query, na=False)]
        if exact.empty:
            raise RuntimeError(f"unable to resolve stock: {query}")
        row = exact.iloc[0].to_dict()
        row["ts_code"] = normalize_ts_code(str(row.get("ts_code") or row.get("symbol") or query))
        return row

    def get_trade_calendar(self, start_date: str, end_date: str, is_open: int = 1) -> list[str]:
        df = self.call_endpoint(
            "trade_cal",
            exchange="SSE",
            start_date=normalize_trade_date(start_date),
            end_date=normalize_trade_date(end_date),
            is_open=is_open,
            fields="exchange,cal_date,is_open,pretrade_date",
        )
        if df.empty:
            return []
        return sorted(df["cal_date"].astype(str).tolist())

    def is_trade_day(self, value: str | date | datetime) -> bool:
        token = normalize_trade_date(value)
        days = self.get_trade_calendar(token, token, is_open=1)
        return token in set(days)

    def next_trade_dates(self, anchor_date: str | date | datetime, count: int) -> list[str]:
        anchor = to_date(anchor_date)
        end = anchor + timedelta(days=max(20, count * 20))
        return self.get_trade_calendar((anchor + timedelta(days=1)).strftime("%Y%m%d"), end.strftime("%Y%m%d"), is_open=1)[:count]

    def previous_trade_dates(self, anchor_date: str | date | datetime, count: int, inclusive: bool = False) -> list[str]:
        anchor = to_date(anchor_date)
        start = anchor - timedelta(days=max(20, count * 20))
        days = self.get_trade_calendar(start.strftime("%Y%m%d"), anchor.strftime("%Y%m%d"), is_open=1)
        if not inclusive:
            days = [item for item in days if item < anchor.strftime("%Y%m%d")]
        return days[-count:]

    def previous_trade_date(self, anchor_date: str | date | datetime, count: int = 1, inclusive: bool = False) -> str:
        dates = self.previous_trade_dates(anchor_date, count, inclusive=inclusive)
        if not dates:
            raise RuntimeError(f"no previous trade date found before {normalize_trade_date(anchor_date)}")
        return dates[-1]

    def next_trade_date(self, anchor_date: str | date | datetime, count: int = 1) -> str:
        dates = self.next_trade_dates(anchor_date, count)
        if not dates:
            raise RuntimeError(f"no next trade date found after {normalize_trade_date(anchor_date)}")
        return dates[count - 1]

    def trade_days_between(self, start_date: str | date | datetime, end_date: str | date | datetime) -> list[str]:
        return self.get_trade_calendar(normalize_trade_date(start_date), normalize_trade_date(end_date), is_open=1)

    def get_daily_bars(
        self,
        ts_code: str,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        df = self.call_endpoint(
            "daily",
            ts_code=normalize_ts_code(ts_code),
            trade_date=normalize_trade_date(trade_date) if trade_date else "",
            start_date=normalize_trade_date(start_date) if start_date else "",
            end_date=normalize_trade_date(end_date) if end_date else "",
            fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
        )
        if df.empty:
            return []
        df = df.sort_values("trade_date")
        if limit > 0:
            df = df.tail(limit)
        return df.fillna("").to_dict(orient="records")

    def latest_bar(self, ts_code: str, on_or_before: str | None = None) -> dict[str, Any] | None:
        end_date = normalize_trade_date(on_or_before) if on_or_before else normalize_trade_date(date.today())
        start_date = shift_calendar_date(end_date, -15)
        bars = self.get_daily_bars(ts_code, start_date=start_date, end_date=end_date)
        return bars[-1] if bars else None

    def _bar_change_pct(self, bar: dict[str, Any] | None) -> float | None:
        if not bar:
            return None
        pct_chg = safe_float(bar.get("pct_chg"))
        if pct_chg is not None:
            return round(pct_chg, 2)
        close_price = safe_float(bar.get("close"))
        pre_close = safe_float(bar.get("pre_close"))
        if close_price and pre_close:
            return round((close_price / pre_close - 1) * 100, 2)
        return None

    def build_market_snapshot(
        self,
        trade_date: str,
        ts_code: str | None = None,
        name: str | None = None,
        sector_name: str | None = None,
        sector_change_pct: float | None = None,
    ) -> dict[str, Any]:
        token = normalize_trade_date(trade_date)
        sh_bar = self.latest_bar("000001.SH", token)
        cyb_bar = self.latest_bar("399006.SZ", token)
        return {
            "trade_date": token,
            "ts_code": normalize_ts_code(ts_code) if ts_code else "",
            "name": name or "",
            "sh_change_pct": self._bar_change_pct(sh_bar),
            "cyb_change_pct": self._bar_change_pct(cyb_bar),
            "up_down_ratio": None,
            "limit_up_count": None,
            "limit_down_count": None,
            "sector_name": sector_name or "",
            "sector_change_pct": safe_float(sector_change_pct),
            "sector_strength_tag": "",
            "raw_payload": {
                "sh_bar": sh_bar,
                "cyb_bar": cyb_bar,
            },
        }
