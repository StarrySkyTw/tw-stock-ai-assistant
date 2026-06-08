from __future__ import annotations

import json
from datetime import date

from app.services.data_providers import MarketDataService
from app.services.indicators import calculate_indicators, summarize_technical
from app.services.market_risk import MarketRiskEngine
from app.services.scoring import (
    recommendation_from_score,
    score_fundamental,
    score_institutional,
    score_sentiment,
    score_technical,
    summarize_institutional,
)
from app.services.sentiment import analyze_news_sentiment


class AnalysisService:
    def __init__(self) -> None:
        self.data = MarketDataService()
        self.risk_engine = MarketRiskEngine()

    async def analyze(
        self,
        symbol: str,
        entry_price: float | None = None,
        highest_price: float | None = None,
        atr_multiplier: float = 2.0,
    ) -> dict:
        symbol = symbol.upper().strip()
        stock_name = await self.data.stock_name(symbol)
        prices, price_source = await self.data.prices(symbol, years=2)
        indicators = calculate_indicators(prices)
        technical = summarize_technical(indicators)
        flows, flow_source = await self.data.institutional_flows(symbol)
        institutional = summarize_institutional(flows)
        fundamentals, fundamental_source = await self.data.fundamentals(symbol)
        shareholding, _ = await self.data.shareholding(symbol)
        news, news_source = await self.data.news(symbol)
        sentiment = await analyze_news_sentiment(symbol, news)
        risk = await self.risk_engine.evaluate()

        technical_score, tech_reasons, tech_risks = score_technical(technical)
        institutional_score, inst_reasons, inst_risks = score_institutional(
            institutional, _float_or_none(shareholding.get("large_holder_ratio"))
        )
        fundamental_score, fund_reasons, fund_risks = score_fundamental(fundamentals)
        sentiment_score, sentiment_reasons, sentiment_risks = score_sentiment(sentiment)

        raw_score = technical_score + institutional_score + fundamental_score + sentiment_score
        adjusted_score = raw_score
        risk_adjustment = 0.0
        risks = tech_risks + inst_risks + fund_risks + sentiment_risks
        reasons = tech_reasons + inst_reasons + fund_reasons + sentiment_reasons
        if risk["lights"]["risk_indicator"] == "red":
            risk_adjustment = -8.0
            adjusted_score += risk_adjustment
            risks.append("Market Risk Engine 顯示風險紅燈，總分下修 8 分。")
        adjusted_score = max(0, min(100, adjusted_score))
        score_breakdown = {
            "technical": round(technical_score, 2),
            "institutional": round(institutional_score, 2),
            "fundamental": round(fundamental_score, 2),
            "sentiment": round(sentiment_score, 2),
            "market_risk_adjustment": risk_adjustment,
        }

        latest = indicators.iloc[-1]
        close = float(latest["close"])
        effective_entry = entry_price or close
        stop_loss = _stop_loss(effective_entry, technical, close)
        trailing = _trailing_take_profit(
            indicators, effective_entry, highest_price, atr_multiplier=atr_multiplier
        )

        reasons.append(f"價格資料來源：{price_source}；法人資料來源：{flow_source}。")
        if fundamental_source != "finmind":
            reasons.append("基本面資料目前使用 sample fallback，設定 FinMind token 後可取得真實資料。")
        if news_source != "finmind":
            reasons.append("新聞情緒目前使用 sample fallback。")
        decision_plan = _decision_plan(
            symbol=symbol,
            name=stock_name,
            recommendation=recommendation_from_score(adjusted_score),
            adjusted_score=adjusted_score,
            raw_score=raw_score,
            score_breakdown=score_breakdown,
            technical=technical,
            institutional=institutional,
            sentiment=sentiment,
            stop_loss=stop_loss,
            trailing=trailing,
            risk_lights=risk["lights"],
            reasons=reasons,
            risks=risks,
            data_sources={
                "price": price_source,
                "institutional": flow_source,
                "fundamental": fundamental_source,
                "news": news_source,
            },
        )

        return {
            "symbol": symbol,
            "name": stock_name,
            "analysis_date": date.today(),
            "raw_score": round(raw_score, 2),
            "adjusted_score": round(adjusted_score, 2),
            "recommendation": recommendation_from_score(adjusted_score),
            "reasons": reasons,
            "risks": risks or ["目前未偵測到重大單一風險，但仍需遵守停損。"],
            "technical": technical,
            "institutional": institutional,
            "fundamental": {**fundamentals, "signals": fund_reasons[:4]},
            "sentiment": sentiment,
            "stop_loss": stop_loss,
            "trailing_take_profit": trailing,
            "risk_lights": risk["lights"],
            "decision_plan": decision_plan,
        }

    async def chart(self, symbol: str, range_name: str = "1y") -> dict:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        symbol = symbol.upper().strip()
        stock_name = await self.data.stock_name(symbol)
        display_name = f"{symbol} {stock_name}" if stock_name else symbol
        years = 5 if range_name == "5y" else 3 if range_name == "3y" else 1
        prices, _ = await self.data.prices(symbol, years=years)
        df = calculate_indicators(prices)
        fig = make_subplots(
            rows=4,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.075,
            row_heights=[0.5, 0.16, 0.18, 0.16],
            subplot_titles=("價格走勢", "成交量", "MACD", "RSI14"),
        )
        fig.add_trace(
            go.Candlestick(
                x=df["date"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="K線",
                increasing_line_color="#16a34a",
                increasing_fillcolor="rgba(22, 163, 74, 0.45)",
                decreasing_line_color="#dc2626",
                decreasing_fillcolor="rgba(220, 38, 38, 0.45)",
            ),
            row=1,
            col=1,
        )
        ma_styles = {
            "ma5": ("MA5", "#f97316", 2.4),
            "ma20": ("MA20", "#06b6d4", 3.0),
            "ma60": ("MA60", "#8b5cf6", 3.0),
        }
        for ma, (label, color, width) in ma_styles.items():
            fig.add_trace(
                go.Scatter(
                    x=df["date"],
                    y=df[ma],
                    mode="lines",
                    name=label,
                    line={"color": color, "width": width},
                    hovertemplate=f"{label}: %{{y:.2f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )
        fig.add_trace(
            go.Bar(
                x=df["date"],
                y=df["volume"],
                name="成交量",
                marker={"color": "rgba(249, 115, 22, 0.65)"},
                hovertemplate="成交量: %{y:,.0f}<extra></extra>",
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["dif"],
                name="DIF",
                line={"color": "#0ea5e9", "width": 2.4},
                hovertemplate="DIF: %{y:.2f}<extra></extra>",
            ),
            row=3,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["macd"],
                name="MACD",
                line={"color": "#ec4899", "width": 2.4},
                hovertemplate="MACD: %{y:.2f}<extra></extra>",
            ),
            row=3,
            col=1,
        )
        fig.add_trace(
            go.Bar(
                x=df["date"],
                y=df["osc"],
                name="OSC",
                marker={"color": "rgba(34, 197, 94, 0.55)"},
                hovertemplate="OSC: %{y:.2f}<extra></extra>",
            ),
            row=3,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["rsi14"],
                name="RSI14",
                line={"color": "#a855f7", "width": 2.5},
                hovertemplate="RSI14: %{y:.2f}<extra></extra>",
            ),
            row=4,
            col=1,
        )
        fig.add_hline(y=0, line_width=1, line_dash="dot", line_color="#9ca3af", row=3, col=1)
        fig.add_hline(y=70, line_width=1, line_dash="dot", line_color="#ef4444", row=4, col=1)
        fig.add_hline(y=30, line_width=1, line_dash="dot", line_color="#22c55e", row=4, col=1)
        fig.update_layout(
            title={"text": f"{display_name} 技術圖表", "x": 0.01, "xanchor": "left"},
            height=980,
            margin=dict(l=96, r=32, t=72, b=84),
            hovermode="x unified",
            bargap=0.1,
        )
        fig.update_yaxes(title_text="", row=1, col=1, showline=True, linewidth=1)
        fig.update_yaxes(title_text="", row=2, col=1, showline=True, linewidth=1)
        fig.update_yaxes(title_text="", row=3, col=1, showline=True, linewidth=1)
        fig.update_yaxes(title_text="", row=4, col=1, range=[0, 100], showline=True, linewidth=1)
        fig.update_xaxes(showline=True, linewidth=1)
        fig.update_xaxes(rangeslider_visible=False)
        fig.update_xaxes(
            rangeslider_visible=True,
            rangeslider_thickness=0.07,
            rangeslider_bgcolor="rgba(148, 163, 184, 0.16)",
            rangeslider_bordercolor="#6b7280",
            rangeslider_borderwidth=1,
            row=4,
            col=1,
        )
        _add_horizontal_axis_labels(fig)
        return {"symbol": symbol, "name": stock_name, "range": range_name, "figure": json.loads(fig.to_json())}


def _decision_plan(
    *,
    symbol: str,
    name: str | None,
    recommendation: str,
    adjusted_score: float,
    raw_score: float,
    score_breakdown: dict[str, float],
    technical: dict,
    institutional: dict,
    sentiment: dict,
    stop_loss: dict,
    trailing: dict,
    risk_lights: dict,
    reasons: list[str],
    risks: list[str],
    data_sources: dict[str, str],
) -> dict:
    composite_light = risk_lights.get("composite", "yellow")
    risk_indicator = risk_lights.get("risk_indicator", "yellow")
    trend = technical.get("trend", "neutral")
    close = _float_or_none(technical.get("latest_close"))
    ma20 = _float_or_none(technical.get("ma", {}).get("ma20"))
    ma60 = _float_or_none(technical.get("ma", {}).get("ma60"))
    rsi14 = _float_or_none(technical.get("rsi", {}).get("rsi14"))
    atr_stop = _float_or_none(stop_loss.get("atr_stop"))
    take_profit = _float_or_none(trailing.get("current_take_profit_price"))
    risk_reward = _float_or_none(trailing.get("risk_reward_ratio"))
    flow_5d = _float_or_none(institutional.get("five_day_total")) or 0.0
    flow_20d = _float_or_none(institutional.get("twenty_day_total")) or 0.0

    bias = _decision_bias(adjusted_score, composite_light, trend)
    confidence = _decision_confidence(adjusted_score, composite_light, trend, data_sources, reasons, risks)
    action = _decision_action(adjusted_score, composite_light, risk_indicator, trend)
    research_position_size = _research_position_size(adjusted_score, composite_light, confidence)

    headline = f"{recommendation}，但先看條件是否成立"
    if bias == "bearish":
        headline = "風險優先，先保護本金"
    elif bias == "bullish":
        headline = "偏多觀察，可用條件分批驗證"

    checklist = {
        "進場條件": [
            f"總分維持 75 以上，目前 {round(adjusted_score, 1)}。",
            f"大盤綜合燈號不是紅燈，目前為 {_light_label(composite_light)}。",
            _price_condition("收盤價守在 MA20 上方", close, ma20),
            "近 5 日或 20 日法人合計轉為買超。",
            _risk_reward_condition(risk_reward),
        ],
        "不進場條件": [
            "Market Risk Engine 或綜合燈號轉紅。",
            _break_condition("收盤價跌破 MA60", close, ma60),
            "RSI14 高於 75 且沒有回測支撐，不追價。",
            "新聞或基本面資料仍是 sample fallback 時，不把結論當成完整事實。",
        ],
        "出場條件": [
            _stop_condition("跌破 ATR 停損", close, atr_stop),
            _stop_condition("跌破移動停利", close, take_profit),
            "跌破 MA60 或分數降到 40 以下時，優先降風險。",
            "重大利空新聞出現時，重新產生分析，不延用舊結論。",
        ],
    }

    scenarios = [
        {
            "name": "偏多情境",
            "condition": (
                f"收盤價站穩 MA20({_fmt(ma20)})，法人 5 日與 20 日至少一個維持買超，"
                f"綜合燈號為 {_light_label(composite_light)} 或轉綠。"
            ),
            "action": "只在條件成立時分批研究，優先用小部位驗證，不用一次押滿。",
            "invalidation": f"跌破 MA20({_fmt(ma20)}) 或風險燈號轉紅。",
        },
        {
            "name": "中性情境",
            "condition": f"分數落在 60 到 75，或價格在 MA20({_fmt(ma20)}) 附近震盪。",
            "action": "保持觀察，等待量能、法人或新聞脈絡給出更明確方向。",
            "invalidation": "連續弱於大盤、法人轉賣超，或分數跌破 60。",
        },
        {
            "name": "偏空情境",
            "condition": (
                f"跌破 MA60({_fmt(ma60)})、Market Risk Engine 轉紅，"
                f"或法人轉賣超，目前 5 日 {_fmt(flow_5d, 0)}、20 日 {_fmt(flow_20d, 0)}。"
            ),
            "action": "先避開新倉或降低研究部位，等趨勢修復後再評估。",
            "invalidation": "重新站回 MA20，法人買盤回來，且風險燈號不再是紅燈。",
        },
    ]

    next_review_triggers = [
        "價格觸及停損、移動停利或 MA60。",
        "總分跨越 75、60、40 任一門檻。",
        "Market Risk Engine 燈號改變。",
        "財報、月營收、法說會或重大新聞公布後。",
        "至少每 5 個交易日重新整理一次，不用舊資料做新決策。",
    ]

    data_quality = [
        f"價格資料來源：{data_sources.get('price', 'unknown')}",
        f"法人資料來源：{data_sources.get('institutional', 'unknown')}",
        f"基本面資料來源：{data_sources.get('fundamental', 'unknown')}",
        f"新聞資料來源：{data_sources.get('news', 'unknown')}",
    ]
    if any(source != "finmind" for key, source in data_sources.items() if key in {"fundamental", "news"}):
        data_quality.append("基本面或新聞若為 sample fallback，適合練習流程，不適合直接當實盤依據。")

    return {
        "headline": headline,
        "bias": bias,
        "action": action,
        "confidence": confidence,
        "research_position_size": research_position_size,
        "score_breakdown": score_breakdown,
        "checklist": checklist,
        "scenarios": scenarios,
        "next_review_triggers": next_review_triggers,
        "data_quality": data_quality,
        "ai_snapshot_prompt": _ai_snapshot_prompt(
            symbol=symbol,
            name=name,
            adjusted_score=adjusted_score,
            raw_score=raw_score,
            recommendation=recommendation,
            technical=technical,
            institutional=institutional,
            sentiment=sentiment,
            risk_lights=risk_lights,
            stop_loss=stop_loss,
            trailing=trailing,
            reasons=reasons,
            risks=risks,
            data_quality=data_quality,
        ),
    }


def _decision_bias(adjusted_score: float, composite_light: str, trend: str) -> str:
    if adjusted_score >= 75 and composite_light != "red" and trend == "bullish":
        return "bullish"
    if adjusted_score < 40 or composite_light == "red":
        return "bearish"
    return "neutral"


def _decision_action(adjusted_score: float, composite_light: str, risk_indicator: str, trend: str) -> str:
    if composite_light == "red" or risk_indicator == "red" or adjusted_score < 40:
        return "暫停新倉或減碼，先等風險燈號與趨勢修復。"
    if adjusted_score >= 75 and trend == "bullish":
        return "列入分批研究名單，只在進場條件成立時執行。"
    if adjusted_score >= 60:
        return "保持觀察，不追價；等價格、量能與法人同步後再行動。"
    return "偏弱觀察，除非出現明確轉強訊號，否則先保留現金。"


def _decision_confidence(
    adjusted_score: float,
    composite_light: str,
    trend: str,
    data_sources: dict[str, str],
    reasons: list[str],
    risks: list[str],
) -> str:
    fallback_count = sum(1 for source in data_sources.values() if source not in {"finmind", "yahoo", "twse"})
    mixed_evidence = bool(reasons and risks)
    if fallback_count >= 2 or composite_light == "red":
        return "低"
    if adjusted_score >= 75 and trend == "bullish" and composite_light == "green" and not mixed_evidence:
        return "高"
    return "中"


def _research_position_size(adjusted_score: float, composite_light: str, confidence: str) -> str:
    if composite_light == "red" or adjusted_score < 40:
        return "0%，先不建立新的研究部位。"
    if adjusted_score < 60 or confidence == "低":
        return "0-10%，只適合觀察或極小部位驗證。"
    if adjusted_score < 75 or composite_light == "yellow":
        return "10-25%，分批且保留現金。"
    return "25-40%，仍需分批，並先設定停損。"


def _ai_snapshot_prompt(
    *,
    symbol: str,
    name: str | None,
    adjusted_score: float,
    raw_score: float,
    recommendation: str,
    technical: dict,
    institutional: dict,
    sentiment: dict,
    risk_lights: dict,
    stop_loss: dict,
    trailing: dict,
    reasons: list[str],
    risks: list[str],
    data_quality: list[str],
) -> str:
    display_name = f"{symbol} {name}" if name else symbol
    lines = [
        "請用保守、可驗證、不可保證報酬的方式分析以下股票快照。",
        f"標的：{display_name}",
        f"總分：{round(adjusted_score, 1)} / 100，原始分數：{round(raw_score, 1)}，系統建議：{recommendation}",
        (
            "風險燈號："
            f"大盤 {_light_label(risk_lights.get('market_trend'))}，"
            f"技術 {_light_label(risk_lights.get('technical'))}，"
            f"風險 {_light_label(risk_lights.get('risk_indicator'))}，"
            f"綜合 {_light_label(risk_lights.get('composite'))}"
        ),
        (
            "技術："
            f"收盤 {_fmt(technical.get('latest_close'))}，"
            f"MA20 {_fmt(technical.get('ma', {}).get('ma20'))}，"
            f"MA60 {_fmt(technical.get('ma', {}).get('ma60'))}，"
            f"RSI14 {_fmt(technical.get('rsi', {}).get('rsi14'))}"
        ),
        (
            "法人："
            f"5日 {_fmt(institutional.get('five_day_total'), 0)}，"
            f"20日 {_fmt(institutional.get('twenty_day_total'), 0)}，"
            f"60日 {_fmt(institutional.get('sixty_day_total'), 0)}"
        ),
        (
            "停損停利："
            f"ATR停損 {_fmt(stop_loss.get('atr_stop'))}，"
            f"移動停利 {_fmt(trailing.get('current_take_profit_price'))}"
        ),
        f"新聞情緒：{sentiment.get('label')}，摘要：{sentiment.get('summary')}",
        f"主要理由：{'; '.join(reasons[:4])}",
        f"主要風險：{'; '.join(risks[:4]) if risks else '目前未列出重大單一風險'}",
        f"資料品質：{'; '.join(data_quality)}",
        "請輸出：1. 市場概況 2. 偏多/中性/偏空三情境 3. 進場條件 4. 不進場條件 5. 停損停利與重新檢查時間。",
    ]
    return "\n".join(lines)


def _price_condition(label: str, close: float | None, reference: float | None) -> str:
    if close is None or reference is None:
        return f"{label}，但目前資料不足需重新確認。"
    status = "成立" if close >= reference else "未成立"
    return f"{label}：{status}，收盤 {_fmt(close)}，參考價 {_fmt(reference)}。"


def _break_condition(label: str, close: float | None, reference: float | None) -> str:
    if close is None or reference is None:
        return f"{label}，但目前資料不足需重新確認。"
    status = "成立" if close < reference else "未成立"
    return f"{label}：{status}，收盤 {_fmt(close)}，參考價 {_fmt(reference)}。"


def _stop_condition(label: str, close: float | None, reference: float | None) -> str:
    if close is None or reference is None:
        return f"{label}，但目前資料不足需重新確認。"
    status = "已觸發" if close <= reference else "未觸發"
    return f"{label}：{status}，收盤 {_fmt(close)}，觸發價 {_fmt(reference)}。"


def _risk_reward_condition(value: float | None) -> str:
    if value is None:
        return "風險報酬比尚未可用，輸入買進價後再確認。"
    status = "足夠" if value >= 1.5 else "不足"
    return f"風險報酬比至少 1.5，目前 {format(value, '.2f')}，{status}。"


def _light_label(light: object) -> str:
    return {"green": "綠燈", "yellow": "黃燈", "red": "紅燈"}.get(str(light), "未知")


def _fmt(value: object, digits: int = 2) -> str:
    numeric = _float_or_none(value)
    if numeric is None:
        return "-"
    return format(numeric, f".{digits}f")


def _stop_loss(entry_price: float, technical: dict, close: float) -> dict:
    atr = technical.get("atr14")
    ma20 = technical["ma"].get("ma20")
    ma60 = technical["ma"].get("ma60")
    notes = ["固定百分比、ATR、均線停損需依持倉週期擇一執行，避免任意移動停損。"]
    return {
        "fixed_5_percent": round(entry_price * 0.95, 2),
        "fixed_8_percent": round(entry_price * 0.92, 2),
        "fixed_10_percent": round(entry_price * 0.90, 2),
        "atr_stop": round(entry_price - 2 * atr, 2) if atr is not None else None,
        "ma20_stop_triggered": bool(ma20 is not None and close < ma20),
        "ma60_stop_triggered": bool(ma60 is not None and close < ma60),
        "notes": notes,
    }


def _trailing_take_profit(indicators, entry_price: float, highest_price: float | None, atr_multiplier: float) -> dict:
    latest = indicators.iloc[-1]
    atr = latest.get("atr14")
    estimated = highest_price is None
    latest_high = float(latest["high"])
    if highest_price is not None:
        high_used = max(float(highest_price), latest_high, entry_price)
    else:
        high_used = max(float(indicators.tail(60)["high"].max()), latest_high, entry_price)
    take_profit = round(high_used - atr_multiplier * float(atr), 2) if atr == atr else None
    estimated_return = (
        round((take_profit / entry_price - 1) * 100, 2)
        if take_profit is not None and entry_price
        else None
    )
    downside = entry_price - take_profit if take_profit is not None else None
    upside = high_used - entry_price
    risk_reward = round(upside / abs(downside), 2) if downside and downside != 0 else None
    return {
        "current_take_profit_price": take_profit,
        "atr_multiplier": atr_multiplier,
        "estimated_return_percent": estimated_return,
        "risk_reward_ratio": risk_reward,
        "highest_price_used": round(high_used, 2),
        "is_estimated_highest_price": estimated,
    }


def _add_horizontal_axis_labels(fig) -> None:
    labels = [
        ("yaxis", "價格"),
        ("yaxis2", "成交量"),
        ("yaxis3", "MACD"),
        ("yaxis4", "RSI"),
    ]
    for axis_name, label in labels:
        domain = getattr(fig.layout, axis_name).domain
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=-0.065,
            y=(domain[0] + domain[1]) / 2,
            text=label,
            textangle=0,
            showarrow=False,
            xanchor="right",
            yanchor="middle",
            font={"size": 13},
        )


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
