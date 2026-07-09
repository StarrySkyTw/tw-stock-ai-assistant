from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from app.services.data_providers.base import FundamentalData, ShareholdingData, normalize_price_frame
from app.services.data_providers.cache import cached_provider_call


class TwseProvider:
    base_url = "https://openapi.twse.com.tw/v1"
    realtime_url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    twse_pe_url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    tpex_pe_url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
    twse_revenue_url = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
    tpex_revenue_url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"
    twse_quarter_url = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
    tpex_quarter_url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"
    twse_institutional_url = "https://www.twse.com.tw/rwd/zh/fund/T86"
    twse_margin_url = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
    tpex_institutional_url = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
    tpex_margin_url = "https://www.tpex.org.tw/www/zh-tw/margin/balance"
    tdcc_shareholding_url = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
    twse_material_info_url = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
    tpex_material_info_url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O"
    company_profile_urls = (
        "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
        "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
    )

    async def stock_profile(self, symbol: str) -> dict[str, str | None]:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return {"name": None, "industry": None}

        for url in self.company_profile_urls:
            try:
                profile = _extract_company_profile(await _json_list(url), normalized_symbol)
            except Exception:
                continue
            if profile["name"] or profile["industry"]:
                return profile

        return await self.realtime_profile(normalized_symbol)

    async def market_type(self, symbol: str) -> str | None:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return None

        for market, url in (("twse", self.company_profile_urls[0]), ("tpex", self.company_profile_urls[1])):
            try:
                profile = _extract_company_profile(await _json_list(url), normalized_symbol)
            except Exception:
                continue
            if profile["name"] or profile["industry"]:
                return market
        return None

    async def realtime_profile(self, symbol: str) -> dict[str, str | None]:
        normalized_symbol = symbol.upper().strip()
        channels = _realtime_channels(normalized_symbol)
        if not channels:
            return {"name": None, "industry": None}

        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "stockai/0.1"}) as client:
            for channel in channels:
                try:
                    response = await client.get(
                        self.realtime_url,
                        params={
                            "ex_ch": channel,
                            "json": "1",
                            "delay": "0",
                            "_": str(int(datetime.now().timestamp() * 1000)),
                        },
                    )
                    response.raise_for_status()
                    profile = _extract_realtime_profile(response.json())
                except Exception:
                    continue
                if profile["name"]:
                    return profile
        return {"name": None, "industry": None}

    async def daily_prices(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        # TWSE OpenAPI is primarily a daily snapshot source; it is used as fallback/cross-check.
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self.base_url}/exchangeReport/STOCK_DAY_ALL")
            response.raise_for_status()
            rows = response.json()
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        id_col = "Code" if "Code" in df.columns else "證券代號"
        matched = df[df[id_col].astype(str).str.strip() == symbol].copy()
        if matched.empty:
            return matched
        date_value = pd.to_datetime(end_date).date()
        out = pd.DataFrame(
            {
                "date": [date_value],
                "open": [matched.iloc[0].get("OpeningPrice", matched.iloc[0].get("開盤價"))],
                "high": [matched.iloc[0].get("HighestPrice", matched.iloc[0].get("最高價"))],
                "low": [matched.iloc[0].get("LowestPrice", matched.iloc[0].get("最低價"))],
                "close": [matched.iloc[0].get("ClosingPrice", matched.iloc[0].get("收盤價"))],
                "volume": [matched.iloc[0].get("TradeVolume", matched.iloc[0].get("成交股數"))],
            }
        )
        for column in ["open", "high", "low", "close", "volume"]:
            out[column] = pd.to_numeric(out[column].astype(str).str.replace(",", ""), errors="coerce")
        return normalize_price_frame(out)

    async def fundamentals(self, symbol: str) -> FundamentalData:
        values, _ = await self.fundamentals_with_source(symbol)
        return values

    async def fundamentals_with_source(self, symbol: str) -> tuple[FundamentalData, str]:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return FundamentalData(), "unavailable"

        for source, pe_url, revenue_url, quarter_url in (
            ("twse-openapi", self.twse_pe_url, self.twse_revenue_url, self.twse_quarter_url),
            ("tpex-openapi", self.tpex_pe_url, self.tpex_revenue_url, self.tpex_quarter_url),
        ):
            pe_row, revenue_row, quarter_row = await _gather_official_rows(
                normalized_symbol,
                pe_url=pe_url,
                revenue_url=revenue_url,
                quarter_url=quarter_url,
            )
            if pe_row is None and revenue_row is None and quarter_row is None:
                continue
            data = _fundamental_from_official_rows(pe_row, revenue_row, quarter_row)
            if any(value is not None for value in data.to_dict().values()):
                return data, source
        return FundamentalData(), "unavailable"

    async def institutional_flows(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        frame, _ = await self.institutional_flows_with_source(symbol, start_date, end_date)
        return frame

    async def institutional_flows_with_source(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[pd.DataFrame, str]:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return _empty_institutional_frame(), "unavailable"

        market = await self.market_type(normalized_symbol)
        markets = [market] if market in {"twse", "tpex"} else ["twse", "tpex"]
        for target_market in markets:
            rows = []
            for trading_date in _recent_weekdays(start_date, end_date, limit=25):
                try:
                    row = (
                        await self._twse_institutional_row(normalized_symbol, trading_date)
                        if target_market == "twse"
                        else await self._tpex_institutional_row(normalized_symbol, trading_date)
                    )
                except Exception:
                    row = None
                if row:
                    rows.append(row)
            if rows:
                return pd.DataFrame(rows).sort_values("date").reset_index(drop=True), (
                    "twse-t86" if target_market == "twse" else "tpex-insti"
                )
        return _empty_institutional_frame(), "unavailable"

    async def margin_balances(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        frame, _ = await self.margin_balances_with_source(symbol, start_date, end_date)
        return frame

    async def margin_balances_with_source(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[pd.DataFrame, str]:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return _empty_margin_frame(), "unavailable"

        market = await self.market_type(normalized_symbol)
        markets = [market] if market in {"twse", "tpex"} else ["twse", "tpex"]
        for target_market in markets:
            rows = []
            for trading_date in _recent_weekdays(start_date, end_date, limit=25):
                try:
                    row = (
                        await self._twse_margin_row(normalized_symbol, trading_date)
                        if target_market == "twse"
                        else await self._tpex_margin_row(normalized_symbol, trading_date)
                    )
                except Exception:
                    row = None
                if row:
                    rows.append(row)
            if rows:
                return pd.DataFrame(rows).sort_values("date").reset_index(drop=True), (
                    "twse-margin" if target_market == "twse" else "tpex-margin"
                )
        return _empty_margin_frame(), "unavailable"

    async def _twse_institutional_row(self, symbol: str, trading_date: date) -> dict[str, float | date] | None:
        payload = await _json_object(
            self.twse_institutional_url,
            params={"date": trading_date.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"},
        )
        if payload.get("stat") != "OK":
            return None
        for row in payload.get("data") or []:
            if not row or str(row[0]).strip() != symbol:
                continue
            foreign = _to_float(row[4])
            trust = _to_float(row[10])
            dealer = _to_float(row[11])
            total = _to_float(row[18])
            return {
                "date": trading_date,
                "foreign_net": foreign or 0.0,
                "investment_trust_net": trust or 0.0,
                "dealer_net": dealer or 0.0,
                "total_net": total if total is not None else (foreign or 0.0) + (trust or 0.0) + (dealer or 0.0),
            }
        return None

    async def _tpex_institutional_row(self, symbol: str, trading_date: date) -> dict[str, float | date] | None:
        payload = await _json_object(
            self.tpex_institutional_url,
            params={"response": "json", "date": _roc_slash_date(trading_date), "type": "Daily"},
        )
        for row in _first_table_rows(payload):
            if not row or str(row[0]).strip() != symbol:
                continue
            foreign = _to_float(row[10])
            trust = _to_float(row[13])
            dealer = _to_float(row[22])
            total = _to_float(row[23])
            return {
                "date": trading_date,
                "foreign_net": foreign or 0.0,
                "investment_trust_net": trust or 0.0,
                "dealer_net": dealer or 0.0,
                "total_net": total if total is not None else (foreign or 0.0) + (trust or 0.0) + (dealer or 0.0),
            }
        return None

    async def _twse_margin_row(self, symbol: str, trading_date: date) -> dict[str, float | date | None] | None:
        payload = await _json_object(
            self.twse_margin_url,
            params={"date": trading_date.strftime("%Y%m%d"), "selectType": "ALL", "response": "json"},
        )
        tables = payload.get("tables") if isinstance(payload, dict) else None
        rows = tables[1].get("data") if isinstance(tables, list) and len(tables) > 1 else []
        for row in rows or []:
            if not row or str(row[0]).strip() != symbol:
                continue
            margin_balance = _to_float(row[6])
            short_balance = _to_float(row[12])
            return _margin_row(trading_date, margin_balance, short_balance)
        return None

    async def _tpex_margin_row(self, symbol: str, trading_date: date) -> dict[str, float | date | None] | None:
        payload = await _json_object(
            self.tpex_margin_url,
            params={"response": "json", "date": _roc_slash_date(trading_date)},
        )
        for row in _first_table_rows(payload):
            if not row or str(row[0]).strip() != symbol:
                continue
            margin_balance = _to_float(row[6])
            short_balance = _to_float(row[14])
            return _margin_row(trading_date, margin_balance, short_balance)
        return None

    async def shareholding_with_source(self, symbol: str) -> tuple[ShareholdingData, str]:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return ShareholdingData(), "unavailable"

        try:
            text = await _text_payload(self.tdcc_shareholding_url)
            data = _extract_tdcc_shareholding(text, normalized_symbol)
        except Exception:
            data = ShareholdingData()
        if any(value is not None for value in data.to_dict().values()):
            return data, "tdcc"
        return ShareholdingData(), "unavailable"

    async def material_events_with_source(self, symbol: str) -> tuple[list[dict], str]:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return [], "unavailable"

        market = await self.market_type(normalized_symbol)
        sources = (
            [("twse-material", self.twse_material_info_url)]
            if market == "twse"
            else [("tpex-material", self.tpex_material_info_url)]
            if market == "tpex"
            else [
                ("twse-material", self.twse_material_info_url),
                ("tpex-material", self.tpex_material_info_url),
            ]
        )
        for source, url in sources:
            try:
                rows = _extract_material_events(await _json_list(url), normalized_symbol, source)
            except Exception:
                continue
            return rows, source
        return [], "unavailable"

    async def realtime_quote(self, symbol: str) -> pd.DataFrame:
        quote = await self.realtime_snapshot(symbol)
        if quote is None:
            return pd.DataFrame()
        return normalize_price_frame(pd.DataFrame([quote]))

    async def realtime_snapshot(self, symbol: str) -> dict | None:
        normalized_symbol = symbol.upper().strip()
        channels = _realtime_channels(normalized_symbol)
        if not channels:
            return None

        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "stockai/0.1"}) as client:
            for channel in channels:
                response = await client.get(
                    self.realtime_url,
                    params={
                        "ex_ch": channel,
                        "json": "1",
                        "delay": "0",
                        "_": str(int(datetime.now().timestamp() * 1000)),
                    },
                )
                response.raise_for_status()
                quote = _extract_quote(response.json())
                if quote is not None:
                    return quote
        return None


def _realtime_channels(symbol: str) -> list[str]:
    if symbol in {"TAIEX", "^TWII", "TWII", "T00"}:
        return ["tse_t00.tw"]
    if symbol.isdigit():
        return [f"tse_{symbol}.tw", f"otc_{symbol}.tw"]
    return []


def _extract_quote(payload: dict) -> dict | None:
    rows = payload.get("msgArray") or []
    if not rows:
        return None

    row = rows[0]
    close = _to_float(row.get("z")) or _to_float(row.get("pz")) or _to_float(row.get("y"))
    quote_date = _parse_market_date(row.get("d") or row.get("^"))
    if close is None or quote_date is None:
        return None

    open_price = _to_float(row.get("o")) or close
    high_price = _to_float(row.get("h")) or max(open_price, close)
    low_price = _to_float(row.get("l")) or min(open_price, close)
    volume = _to_float(row.get("v"))
    if volume is None and row.get("@") == "t00.tw":
        volume = _to_float(row.get("m"))
    volume = volume or 0.0

    return {
        "date": quote_date,
        "name": row.get("n"),
        "full_name": row.get("nf"),
        "open": open_price,
        "high": max(high_price, open_price, close),
        "low": min(low_price, open_price, close),
        "close": close,
        "previous_close": _to_float(row.get("y")),
        "volume": volume * 1000,
    }


INDUSTRY_CODE_MAP = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "14": "建材營造",
    "15": "航運業",
    "16": "觀光餐旅",
    "17": "金融保險業",
    "18": "貿易百貨",
    "20": "其他業",
    "21": "化學工業",
    "22": "生技醫療業",
    "23": "油電燃氣業",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "文化創意業",
    "33": "農業科技業",
    "34": "電子商務業",
    "35": "綠能環保業",
    "36": "數位雲端業",
    "37": "運動休閒業",
    "38": "居家生活業",
}


def _extract_company_profile(payload: object, symbol: str) -> dict[str, str | None]:
    if not isinstance(payload, list):
        return {"name": None, "industry": None}
    for row in payload:
        if not isinstance(row, dict):
            continue
        row_symbol = _first_text(row, ("SecuritiesCompanyCode", "公司代號", "Code", "stock_id", "股票代號"))
        if row_symbol != symbol:
            continue
        return {
            "name": _first_text(row, ("CompanyAbbreviation", "公司簡稱", "Name", "股票名稱", "CompanyName", "公司名稱")),
            "industry": _industry_from_company_row(row),
        }
    return {"name": None, "industry": None}


def _extract_realtime_profile(payload: dict) -> dict[str, str | None]:
    rows = payload.get("msgArray") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _first_text(row, ("n", "nf"))
        if name:
            return {"name": name, "industry": None}
    return {"name": None, "industry": None}


async def _gather_official_rows(
    symbol: str,
    *,
    pe_url: str,
    revenue_url: str,
    quarter_url: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    pe_rows, revenue_rows, quarter_rows = await _json_list(pe_url), await _json_list(revenue_url), await _json_list(quarter_url)
    return (
        _find_symbol_row(pe_rows, symbol),
        _find_symbol_row(revenue_rows, symbol),
        _find_symbol_row(quarter_rows, symbol),
    )


def _fundamental_from_official_rows(
    pe_row: dict[str, Any] | None,
    revenue_row: dict[str, Any] | None,
    quarter_row: dict[str, Any] | None,
) -> FundamentalData:
    pe_ratio = _to_float(_first_value(pe_row, ("PEratio", "PriceEarningRatio", "本益比")))
    pb_ratio = _to_float(_first_value(pe_row, ("PBratio", "PriceBookRatio", "股價淨值比")))
    eps = _to_float(_first_value(quarter_row, ("基本每股盈餘(元)", "基本每股盈餘", "BasicEarningsPerShare")))
    revenue_yoy = _to_float(_first_value(revenue_row, ("營業收入-去年同月增減(%)",)))
    revenue_mom = _to_float(_first_value(revenue_row, ("營業收入-上月比較增減(%)",)))
    revenue = _to_float(_first_value(quarter_row, ("營業收入", "OperatingRevenue")))
    operating_income = _to_float(_first_value(quarter_row, ("營業利益", "OperatingIncome")))
    operating_margin = _ratio_percent(operating_income, revenue)
    roe = _ratio_percent(pb_ratio, pe_ratio)
    return FundamentalData(
        eps=eps,
        roe=roe,
        gross_margin=None,
        operating_margin=operating_margin,
        pe_ratio=pe_ratio,
        pb_ratio=pb_ratio,
        revenue_yoy=revenue_yoy,
        revenue_mom=revenue_mom,
    )


def _find_symbol_row(rows: list[Any], symbol: str) -> dict[str, Any] | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_symbol = _first_text(row, ("Code", "SecuritiesCompanyCode", "公司代號", "stock_id", "股票代號"))
        if row_symbol == symbol:
            return row
    return None


def _first_value(row: dict[str, Any] | None, keys: tuple[str, ...]) -> Any:
    if not row:
        return None
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _first_table_rows(payload: dict[str, Any]) -> list[list[Any]]:
    tables = payload.get("tables") if isinstance(payload, dict) else None
    if not isinstance(tables, list) or not tables:
        return []
    rows = tables[0].get("data") if isinstance(tables[0], dict) else []
    return rows if isinstance(rows, list) else []


def _empty_institutional_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "foreign_net", "investment_trust_net", "dealer_net", "total_net"])


def _empty_margin_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "margin_purchase_balance", "short_sale_balance", "short_margin_ratio"])


def _margin_row(trading_date: date, margin_balance: float | None, short_balance: float | None) -> dict[str, float | date | None]:
    ratio = _ratio_percent(short_balance, margin_balance)
    return {
        "date": trading_date,
        "margin_purchase_balance": margin_balance,
        "short_sale_balance": short_balance,
        "short_margin_ratio": ratio,
    }


def _recent_weekdays(start_date: str, end_date: str, *, limit: int) -> list[date]:
    start = pd.to_datetime(start_date, errors="coerce").date()
    end = pd.to_datetime(end_date, errors="coerce").date()
    output: list[date] = []
    current = end
    while current >= start and len(output) < limit:
        if current.weekday() < 5:
            output.append(current)
        current -= timedelta(days=1)
    return list(reversed(output))


def _roc_slash_date(value: date) -> str:
    return f"{value.year - 1911:03d}/{value.month:02d}/{value.day:02d}"


async def _json_list(url: str, params: dict[str, str] | None = None) -> list[Any]:
    payload = await _json_payload(url, params=params)
    return payload if isinstance(payload, list) else []


async def _json_object(url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    payload = await _json_payload(url, params=params)
    return payload if isinstance(payload, dict) else {}


async def _json_payload(url: str, params: dict[str, str] | None = None) -> Any:
    query = params or {}
    cache_key = "twse-json:" + url + "?" + "&".join(f"{key}={value}" for key, value in sorted(query.items()))

    async def fetch() -> Any:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=4.0),
            headers={"User-Agent": "stockai/0.1"},
        ) as client:
            response = await client.get(url, params=query or None)
            response.raise_for_status()
            return response.json()

    return await cached_provider_call(cache_key, 1800, fetch)


async def _text_payload(url: str, params: dict[str, str] | None = None) -> str:
    query = params or {}
    cache_key = "twse-text:" + url + "?" + "&".join(f"{key}={value}" for key, value in sorted(query.items()))

    async def fetch() -> str:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=4.0),
            headers={"User-Agent": "stockai/0.1"},
        ) as client:
            response = await client.get(url, params=query or None)
            response.raise_for_status()
            return response.content.decode("utf-8-sig", errors="replace")

    return await cached_provider_call(cache_key, 21600, fetch)


def _extract_tdcc_shareholding(text: str, symbol: str) -> ShareholdingData:
    if not text:
        return ShareholdingData()
    rows = []
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    for row in reader:
        row_symbol = str(row.get("證券代號") or "").strip()
        if row_symbol == symbol:
            rows.append(row)
    if not rows:
        return ShareholdingData()

    latest_date = max(str(row.get("資料日期") or "").strip() for row in rows)
    rows = [row for row in rows if str(row.get("資料日期") or "").strip() == latest_date]
    shareholder_count = 0
    total_shareholder_count = None
    large_holder_ratio = 0.0
    has_large_holder_ratio = False
    for row in rows:
        level = int(_to_float(row.get("持股分級")) or 0)
        people = int(_to_float(row.get("人數")) or 0)
        ratio = _to_float(row.get("占集保庫存數比例%"))
        if level == 17:
            total_shareholder_count = people or None
            continue
        shareholder_count += people
        # TDCC level 15-16 approximates the large-holder bucket; level 17 is the 100% total row.
        if 15 <= level <= 16 and ratio is not None:
            large_holder_ratio += ratio
            has_large_holder_ratio = True
    return ShareholdingData(
        large_holder_ratio=round(large_holder_ratio, 2) if has_large_holder_ratio else None,
        shareholder_count=total_shareholder_count or shareholder_count or None,
    )


def _extract_material_events(rows: list[Any], symbol: str, source: str) -> list[dict]:
    output = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_symbol = _first_text(row, ("公司代號", "SecuritiesCompanyCode", "Code", "stock_id", "股票代號"))
        if row_symbol != symbol:
            continue
        title = _clean_event_text(_first_text(row, ("主旨 ", "主旨", "Subject", "Title")) or "")
        if not title:
            continue
        event_date = _parse_market_date(
            _first_text(row, ("發言日期", "Date", "出表日期", "事實發生日", "EventDate")) or ""
        )
        explanation = _clean_event_text(_first_text(row, ("說明", "Description", "內容")) or "")
        output.append(
            {
                "published_at": event_date.isoformat() if event_date else "",
                "title": title,
                "source": source,
                "url": "https://mops.twse.com.tw/mops/web/t05st02",
                "summary": explanation[:220],
            }
        )
    return output[:10]


def _clean_event_text(value: str) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())


def _industry_from_company_row(row: dict) -> str | None:
    raw_industry = _first_text(
        row,
        (
            "Industry",
            "industry",
            "IndustryName",
            "industry_name",
            "產業別",
            "產業名稱",
            "SecuritiesIndustryName",
        ),
    )
    if raw_industry:
        return raw_industry
    code = _first_text(row, ("SecuritiesIndustryCode", "產業代號", "industry_code"))
    if not code:
        return None
    return INDUSTRY_CODE_MAP.get(code.zfill(2), code)


def _first_text(row: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        text = str(value or "").replace("\u3000", " ").strip()
        if text and text not in {"-", "－", "--"}:
            return text
    return None


def _parse_market_date(value: object) -> date | None:
    text = str(value or "").strip()
    try:
        if len(text) == 8:
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        if len(text) == 7:
            return date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:7]))
    except ValueError:
        return None
    return None


def _to_float(value: object) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "--", "N/A", "NaN", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _ratio_percent(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator * 100, 2)
