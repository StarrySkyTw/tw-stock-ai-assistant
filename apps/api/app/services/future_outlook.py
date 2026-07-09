from __future__ import annotations

from typing import Any

from app.services.source_quality import is_trusted_source


def build_future_outlook(
    *,
    position: Any,
    analysis: dict[str, Any],
    market_context: dict[str, Any],
    priority_factors: list[dict[str, Any]],
    latest_close: float | None,
    action: str,
    unrealized_pnl_percent: float | None,
) -> dict[str, Any]:
    data_sources = analysis.get("data_sources", {})
    probabilities = _scenario_probabilities(
        analysis=analysis,
        market_context=market_context,
        priority_factors=priority_factors,
        latest_close=latest_close,
        unrealized_pnl_percent=unrealized_pnl_percent,
    )
    label = _outlook_label(probabilities)
    expectation_gap = _expectation_gap(analysis, data_sources)
    leading_indicators = _leading_indicators(analysis, market_context, priority_factors)
    scenarios = _build_scenarios(probabilities, analysis, market_context)
    swing_plan = _build_swing_plan(
        position=position,
        analysis=analysis,
        market_context=market_context,
        probabilities=probabilities,
        latest_close=latest_close,
        action=action,
    )

    return {
        "label": label,
        "horizon": "未來 1-8 週",
        "expectation_gap": expectation_gap,
        "leading_indicators": leading_indicators,
        "scenarios": scenarios,
        "swing_plan": swing_plan,
    }


def build_fallback_future_outlook() -> dict[str, Any]:
    return {
        "label": "資料不足",
        "horizon": "未來 1-8 週",
        "expectation_gap": "核心資料未完成，不能判斷預期差。",
        "leading_indicators": ["先確認價格、營收、重大訊息與 K 線來源。"],
        "scenarios": [
            {
                "name": "等待資料",
                "probability": 100,
                "condition": "資料來源恢復前，不建立未來劇本。",
                "action": "只保留庫存紀錄，不加碼、不追價。",
                "trigger": "價格、營收、重大訊息與 K 線同步後重新判斷。",
                "invalidation": "資料仍不足時，所有結論都降為觀察。",
                "tone": "neutral",
            }
        ],
        "swing_plan": {
            "stance": "等待資料",
            "horizon": "先不做波段",
            "entry_zone": "未建立",
            "add_rule": "資料不足不加碼。",
            "trim_rule": "若已持有，只依既有停損或人工判斷控風險。",
            "stop_rule": "等待失效價同步。",
            "review_rule": "資料來源恢復後重新整理庫存。",
            "position_size_hint": "不新增部位",
        },
    }


def build_candidate_future_outlook(
    *,
    analysis: dict[str, Any],
    market_context: dict[str, Any],
    priority_factors: list[dict[str, Any]],
    latest_close: float | None,
    candidate_status: str,
) -> dict[str, Any]:
    data_sources = analysis.get("data_sources", {})
    if _candidate_core_data_limited(data_sources):
        return build_candidate_fallback_future_outlook(data_limited=True)

    probabilities = _scenario_probabilities(
        analysis=analysis,
        market_context=market_context,
        priority_factors=priority_factors,
        latest_close=latest_close,
        unrealized_pnl_percent=None,
    )
    status_prefix = _candidate_status_prefix(candidate_status)

    return {
        "label": f"{status_prefix}，{_outlook_label(probabilities)}",
        "horizon": "未來 1-8 週",
        "expectation_gap": _expectation_gap(analysis, data_sources),
        "leading_indicators": _leading_indicators(analysis, market_context, priority_factors),
        "scenarios": _build_candidate_scenarios(probabilities, analysis, market_context, candidate_status),
        "swing_plan": _build_candidate_swing_plan(
            analysis=analysis,
            market_context=market_context,
            probabilities=probabilities,
            latest_close=latest_close,
            candidate_status=candidate_status,
        ),
    }


def build_candidate_fallback_future_outlook(
    *,
    reason: str = "舊掃描待重算",
    data_limited: bool = False,
) -> dict[str, Any]:
    if data_limited:
        label = "資料不足，不列入未來劇本"
        expectation = "核心資料不足，不能判斷預期差，也不能建立波段候選。"
        condition = "基本面或日 K 不是可驗證來源。"
        action = "不列入波段操作候選；先補資料再重新掃描。"
        trigger = "價格、營收、重大訊息與 K 線來源都可信後重算。"
        position_size = "0%，不建立研究部位。"
    else:
        label = reason
        expectation = "這筆候選是在未來劇本欄位上線前產生，請重新掃描後再判斷。"
        condition = "舊快取缺少事件、預期差與情境機率。"
        action = "不因舊排名操作；重新掃描後才列入研究。"
        trigger = "重新執行市場掃描。"
        position_size = "0%，舊掃描不新增部位。"

    return {
        "label": label,
        "horizon": "重新掃描後",
        "expectation_gap": expectation,
        "leading_indicators": [
            "確認官方或可信基本面來源。",
            "確認可驗證日 K、支撐、壓力與失效價。",
            "重新掃描後才比較候選排序。",
        ],
        "scenarios": [
            {
                "name": "等待重算",
                "probability": 100,
                "condition": condition,
                "action": action,
                "trigger": trigger,
                "invalidation": "資料仍不足時，維持只觀察，不建立波段劇本。",
                "tone": "neutral",
            }
        ],
        "swing_plan": {
            "stance": "先不操作",
            "horizon": "等待重算",
            "entry_zone": "未建立",
            "add_rule": "候選資料不足或舊快取時，不做進場研究。",
            "trim_rule": "若已持有，回到庫存決策頁用持股成本與失效價判斷。",
            "stop_rule": "沒有可信失效價前，不放大風險。",
            "review_rule": "重新掃描並確認資料來源可信後重算。",
            "position_size_hint": position_size,
        },
    }


def _scenario_probabilities(
    *,
    analysis: dict[str, Any],
    market_context: dict[str, Any],
    priority_factors: list[dict[str, Any]],
    latest_close: float | None,
    unrealized_pnl_percent: float | None,
) -> dict[str, int]:
    scores = {"upside": 30.0, "range": 45.0, "downside": 25.0}
    data_sources = analysis.get("data_sources", {})
    if latest_close is None or not is_trusted_source(data_sources.get("price"), "price"):
        scores["upside"] -= 12
        scores["range"] += 12
    if not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        scores["upside"] -= 8
        scores["range"] += 8

    metrics = analysis.get("fundamental_gate", {}).get("metrics", {})
    revenue_yoy = _float_or_none(metrics.get("revenue_yoy"))
    revenue_mom = _float_or_none(metrics.get("revenue_mom"))
    if revenue_yoy is not None and revenue_yoy >= 20 and (revenue_mom is None or revenue_mom >= 0):
        scores["upside"] += 12
        scores["range"] -= 7
        scores["downside"] -= 5
    elif revenue_yoy is not None and revenue_yoy >= 10:
        scores["upside"] += 6
        scores["range"] -= 4
        scores["downside"] -= 2
    elif revenue_yoy is not None and revenue_yoy < 0:
        scores["upside"] -= 10
        scores["range"] -= 4
        scores["downside"] += 14
    if revenue_mom is not None and revenue_mom <= -10:
        scores["upside"] -= 6
        scores["downside"] += 6

    fundamental_status = str(analysis.get("fundamental_gate", {}).get("status") or "unknown")
    valuation_status = str(analysis.get("valuation_gate", {}).get("status") or "unknown")
    timing_status = str(analysis.get("timing_gate", {}).get("status") or "unknown")
    no_chase = bool(analysis.get("research_decision", {}).get("do_not_chase_reason"))
    if fundamental_status == "pass" and timing_status == "pass":
        scores["upside"] += 8
        scores["downside"] -= 5
        scores["range"] -= 3
    if valuation_status in {"watch", "fail"} or no_chase:
        scores["upside"] -= 8
        scores["range"] += 5
        scores["downside"] += 3
    if timing_status == "fail":
        scores["upside"] -= 10
        scores["downside"] += 10

    if market_context.get("event_window"):
        scores["range"] += 8
        scores["upside"] -= 5
        scores["downside"] -= 3
    if market_context.get("event_window") and market_context.get("no_confirmed_bullish"):
        scores["upside"] -= 6
        scores["range"] += 5
        scores["downside"] += 1

    if _has_signal(priority_factors, "chip_context", "risk"):
        scores["upside"] -= 8
        scores["range"] -= 4
        scores["downside"] += 12
    elif market_context.get("chip_wash"):
        scores["range"] += 5
        scores["downside"] -= 3
        scores["upside"] -= 2
    if _has_signal(priority_factors, "event", "risk") or _has_signal(priority_factors, "revenue", "risk"):
        scores["upside"] -= 10
        scores["downside"] += 10

    market_light = str(analysis.get("risk_lights", {}).get("composite") or "yellow")
    if market_light == "red":
        scores["upside"] -= 8
        scores["downside"] += 12
        scores["range"] -= 4
    elif market_light == "green":
        scores["upside"] += 4
        scores["downside"] -= 4

    if unrealized_pnl_percent is not None and unrealized_pnl_percent <= -8:
        scores["upside"] -= 4
        scores["downside"] += 4

    return _normalize_probabilities(scores)


def _normalize_probabilities(scores: dict[str, float]) -> dict[str, int]:
    bounded = {key: max(8.0, value) for key, value in scores.items()}
    total = sum(bounded.values()) or 1.0
    normalized = {key: int(round(value / total * 100)) for key, value in bounded.items()}
    diff = 100 - sum(normalized.values())
    normalized["range"] = max(1, normalized["range"] + diff)
    return normalized


def _outlook_label(probabilities: dict[str, int]) -> str:
    upside = probabilities["upside"]
    range_prob = probabilities["range"]
    downside = probabilities["downside"]
    if downside >= upside + 12:
        return "未來偏防守"
    if upside >= downside + 12:
        return "未來偏上行"
    if range_prob >= 45:
        return "事件前震盪"
    return "多空待確認"


def _expectation_gap(analysis: dict[str, Any], data_sources: dict[str, str]) -> str:
    if not is_trusted_source(data_sources.get("fundamental"), "fundamental"):
        return "基本面來源不足，不能判斷市場預期差。"
    metrics = analysis.get("fundamental_gate", {}).get("metrics", {})
    revenue_yoy = _float_or_none(metrics.get("revenue_yoy"))
    revenue_mom = _float_or_none(metrics.get("revenue_mom"))
    valuation_status = str(analysis.get("valuation_gate", {}).get("status") or "unknown")
    no_chase = bool(analysis.get("research_decision", {}).get("do_not_chase_reason"))

    if revenue_yoy is not None and revenue_yoy < 0:
        return "營收年增轉負，存在負向預期差風險。"
    if revenue_mom is not None and revenue_mom <= -10:
        return "營收月減過大，先確認是否只是季節性，否則容易形成負向預期差。"
    if revenue_yoy is not None and revenue_yoy >= 20 and (revenue_mom is None or revenue_mom >= 0):
        if valuation_status == "pass" and not no_chase:
            return "營收動能有正向預期差雛形，仍要等價格守支撐或事件確認。"
        return "營收動能好，但估值或禁追條件代表利多可能已部分反映。"
    if revenue_yoy is not None and revenue_yoy >= 10:
        return "基本面偏正向，但還需要法說、報價或月營收延續才算超預期。"
    return "預期差尚未打開，不能只因股價反彈就假設未來利多。"


def _leading_indicators(
    analysis: dict[str, Any],
    market_context: dict[str, Any],
    priority_factors: list[dict[str, Any]],
) -> list[str]:
    items: list[str] = []
    for catalyst in market_context.get("catalysts", [])[:3]:
        date_text = str(catalyst.get("date") or "")
        label = str(catalyst.get("label") or "")
        if date_text and label:
            items.append(f"{date_text[5:]} {label}")

    metrics = analysis.get("fundamental_gate", {}).get("metrics", {})
    revenue_yoy = _float_or_none(metrics.get("revenue_yoy"))
    revenue_mom = _float_or_none(metrics.get("revenue_mom"))
    if revenue_yoy is not None:
        detail = f"營收年增 {revenue_yoy:.1f}%"
        if revenue_mom is not None:
            detail += f"、月增 {revenue_mom:.1f}%"
        items.append(detail)

    valuation = analysis.get("valuation_gate", {})
    pe_ratio = _float_or_none(valuation.get("pe_ratio"))
    if pe_ratio is not None:
        items.append(f"本益比 {pe_ratio:.1f}，估值狀態 {valuation.get('status', 'unknown')}")

    timing = analysis.get("timing_gate", {})
    support = str(timing.get("support_zone") or "").strip()
    if support:
        items.append(f"K 線支撐：{support}")
    else:
        ma = analysis.get("technical", {}).get("ma", {})
        ma20 = _float_or_none(ma.get("ma20"))
        ma60 = _float_or_none(ma.get("ma60"))
        if ma20 is not None or ma60 is not None:
            items.append(f"均線支撐 MA20 {ma20 or '-'} / MA60 {ma60 or '-'}")

    for signal in priority_factors:
        if signal.get("kind") in {"chip_context", "discipline"}:
            items.append(str(signal.get("detail") or ""))

    return [item for item in items if item][:6]


def _build_scenarios(
    probabilities: dict[str, int],
    analysis: dict[str, Any],
    market_context: dict[str, Any],
) -> list[dict[str, Any]]:
    event_text = _event_text(market_context)
    support = _support_text(analysis)
    stop = _stop_text(analysis)
    return [
        {
            "name": "上行情境",
            "probability": probabilities["upside"],
            "condition": f"{event_text}後出現超預期，且價格守住 {support}。",
            "action": "只在回測支撐不破、量縮止跌或突破後回測成功時小幅分批；不追急拉長紅。",
            "trigger": "營收/法說/CPI 方向優於市場預期，且法人或籌碼賣壓收斂。",
            "invalidation": stop,
            "tone": "positive",
        },
        {
            "name": "震盪換手",
            "probability": probabilities["range"],
            "condition": f"{event_text}前後消息未明，價格在支撐與壓力間整理。",
            "action": "續抱但不加碼；靠近支撐才研究，接近壓力或爆量不追。",
            "trigger": "量縮、融資下降、價格未跌破支撐，代表籌碼可能正在清洗。",
            "invalidation": stop,
            "tone": "neutral",
        },
        {
            "name": "轉弱情境",
            "probability": probabilities["downside"],
            "condition": f"{event_text}不如預期，或價格跌破 {support}。",
            "action": "先減碼，若同時出現營收/重大消息利空與跌破失效價，改做離場檢查。",
            "trigger": "法人賣壓擴大、融資續增、營收轉弱或跌破失效價。",
            "invalidation": "重新站回支撐並出現可信利多前，不恢復加碼。",
            "tone": "risk",
        },
    ]


def _build_candidate_scenarios(
    probabilities: dict[str, int],
    analysis: dict[str, Any],
    market_context: dict[str, Any],
    candidate_status: str,
) -> list[dict[str, Any]]:
    event_text = _event_text(market_context)
    support = _support_text(analysis)
    stop = _stop_text(analysis)
    qualified = candidate_status == "qualified_research"
    upside_action = (
        "列入優先研究；只在回測支撐不破、量縮止跌或突破後回測成功時，才允許小幅試單。"
        if qualified
        else "仍不直接追價；先等候選阻擋條件解除，再回到小部位研究。"
    )
    range_action = (
        "維持候選觀察，不急著買；只記錄支撐、籌碼清洗與事件前後變化。"
        if candidate_status != "qualified_research"
        else "保留候選資格；靠近支撐才研究，接近壓力或爆量不追。"
    )

    return [
        {
            "name": "上行突破",
            "probability": probabilities["upside"],
            "condition": f"{event_text}後出現超預期，且價格守住 {support}。",
            "action": upside_action,
            "trigger": "營收、法說、總經或產業領先指標優於市場預期，且法人賣壓收斂。",
            "invalidation": stop,
            "tone": "positive",
        },
        {
            "name": "震盪換手",
            "probability": probabilities["range"],
            "condition": f"{event_text}前後消息未明，價格在支撐與壓力間整理。",
            "action": range_action,
            "trigger": "量縮、融資下降、價格未跌破支撐，代表籌碼可能正在清洗。",
            "invalidation": stop,
            "tone": "neutral",
        },
        {
            "name": "轉弱排除",
            "probability": probabilities["downside"],
            "condition": f"{event_text}不如預期，或價格跌破 {support}。",
            "action": "從候選移除或降為低優先觀察；不要用跌深當成買進理由。",
            "trigger": "法人賣壓擴大、融資續增、營收轉弱或跌破失效價。",
            "invalidation": "重新站回支撐並出現可信利多前，不恢復為波段候選。",
            "tone": "risk",
        },
    ]


def _build_candidate_swing_plan(
    *,
    analysis: dict[str, Any],
    market_context: dict[str, Any],
    probabilities: dict[str, int],
    latest_close: float | None,
    candidate_status: str,
) -> dict[str, str]:
    support = _support_text(analysis)
    resistance = _resistance_text(analysis)
    stop = _stop_text(analysis)
    price_plan = analysis.get("price_plan", {})
    position_size_hint = str(price_plan.get("position_size_hint") or "小部位研究，不一次打滿。")

    if latest_close is None:
        return {
            "stance": "等待可信價格",
            "horizon": "先不做波段",
            "entry_zone": "未建立",
            "add_rule": "沒有可信價格，不建立進場區或支撐假設。",
            "trim_rule": "若已持有，回到庫存決策頁用成本與風險控管。",
            "stop_rule": stop,
            "review_rule": "價格與日 K 同步後重新掃描。",
            "position_size_hint": "0%，不建立研究部位。",
        }

    if candidate_status == "qualified_research":
        stance = "等觸發，不追價"
        add_rule = f"{_event_text(market_context)}後若超預期，且回測 {support} 不破，才把候選轉為小部位研究。"
        trim_rule = f"接近 {resistance}、爆量急拉或事件未確認時，不追高，已持有者才檢查降風險。"
        position_size = position_size_hint
    elif candidate_status == "wait_price":
        stance = "等便宜價"
        add_rule = f"估值或價位未到，先等靠近 {support} 且風險報酬改善。"
        trim_rule = f"若反彈靠近 {resistance} 但估值仍不便宜，候選維持等待。"
        position_size = "0%，價格未進入安全邊際。"
    elif candidate_status == "reject":
        stance = "先排除"
        add_rule = "阻擋條件未解除前，不做波段研究。"
        trim_rule = "若只是候選，直接移出優先清單；若已持有，回庫存頁做減碼檢查。"
        position_size = "0%，不建立研究部位。"
    else:
        stance = "只觀察"
        add_rule = f"只記錄 {support} 是否守住、事件後是否出現超預期；沒有確認前不進場。"
        trim_rule = f"反彈靠近 {resistance} 也不追價，等待下一次可信資料重算。"
        position_size = "0%，尚未符合波段候選條件。"

    if probabilities["downside"] >= probabilities["upside"] + 12:
        stance = f"{stance}，偏防守"

    return {
        "stance": stance,
        "horizon": "1-4 週波段候選，重大事件後重算",
        "entry_zone": support,
        "add_rule": add_rule,
        "trim_rule": trim_rule,
        "stop_rule": stop,
        "review_rule": "CPI、法說、月營收、重大訊息或跌破失效價後立即重算。",
        "position_size_hint": position_size,
    }


def _build_swing_plan(
    *,
    position: Any,
    analysis: dict[str, Any],
    market_context: dict[str, Any],
    probabilities: dict[str, int],
    latest_close: float | None,
    action: str,
) -> dict[str, str]:
    support = _support_text(analysis)
    resistance = _resistance_text(analysis)
    stop = _stop_text(analysis)
    position_size_hint = str(analysis.get("price_plan", {}).get("position_size_hint") or "")
    if not position_size_hint:
        position_size_hint = "事件前維持小部位或原部位，不因反彈放大。"

    if latest_close is None:
        return {
            "stance": "等待資料",
            "horizon": "先不做波段",
            "entry_zone": "未建立",
            "add_rule": "沒有可信價格不加碼。",
            "trim_rule": "若已持有，只依人工停損控風險。",
            "stop_rule": stop,
            "review_rule": "價格、營收、重大訊息同步後重新判斷。",
            "position_size_hint": "不新增部位",
        }

    if action in {"sell", "reduce"}:
        stance = "反彈減碼"
        add_rule = "這個劇本不做加碼；除非事件後重新轉為上行情境。"
        trim_rule = f"反彈靠近 {resistance}、量縮或籌碼仍弱時先降部位。"
    elif market_context.get("event_window"):
        stance = "事件前守倉"
        add_rule = f"{_event_text(market_context)}後，若守住 {support} 且利多超預期，才允許小幅分批。"
        trim_rule = f"事件前急拉靠近 {resistance} 或爆量不追，必要時先收回部分風險。"
    elif probabilities["upside"] >= probabilities["downside"] + 12:
        stance = "回測分批"
        add_rule = f"回測 {support} 不破、再站回短線轉強點才小幅加碼。"
        trim_rule = f"接近 {resistance} 且量能不續航時先停利一部分。"
    else:
        stance = "區間波段"
        add_rule = f"只在靠近 {support} 並出現止跌訊號時研究。"
        trim_rule = f"靠近 {resistance}、事件未確認或籌碼轉弱時降低部位。"

    entry_price = _float_or_none(getattr(position, "entry_price", None))
    close_vs_cost = ""
    if entry_price and latest_close:
        distance = (latest_close / entry_price - 1) * 100
        close_vs_cost = f"；現價相對成本 {distance:+.1f}%"

    return {
        "stance": stance,
        "horizon": "1-4 週波段，重大事件後重算",
        "entry_zone": f"{support}{close_vs_cost}",
        "add_rule": add_rule,
        "trim_rule": trim_rule,
        "stop_rule": stop,
        "review_rule": "CPI、法說、月營收、重大訊息或跌破失效價後立即重算。",
        "position_size_hint": position_size_hint,
    }


def _event_text(market_context: dict[str, Any]) -> str:
    catalysts = market_context.get("catalysts", [])
    if not catalysts:
        return "下一個重大催化"
    labels = []
    for catalyst in catalysts[:2]:
        date_text = str(catalyst.get("date") or "")
        label = str(catalyst.get("label") or "")
        labels.append(f"{date_text[5:]} {label}" if date_text else label)
    return "、".join(label for label in labels if label) or "下一個重大催化"


def _support_text(analysis: dict[str, Any]) -> str:
    timing = analysis.get("timing_gate", {})
    support = str(timing.get("support_zone") or "").strip()
    if support:
        return support
    ma = analysis.get("technical", {}).get("ma", {})
    ma20 = _float_or_none(ma.get("ma20"))
    ma60 = _float_or_none(ma.get("ma60"))
    if ma20 is not None and ma60 is not None:
        return f"MA20 {ma20:.2f} / MA60 {ma60:.2f}"
    if ma20 is not None:
        return f"MA20 {ma20:.2f}"
    if ma60 is not None:
        return f"MA60 {ma60:.2f}"
    watch_price = _float_or_none(analysis.get("price_plan", {}).get("watch_price"))
    if watch_price is not None:
        return f"觀察價 {watch_price:.2f}"
    return "尚未建立支撐"


def _resistance_text(analysis: dict[str, Any]) -> str:
    timing = analysis.get("timing_gate", {})
    no_chase = str(timing.get("no_chase_zone") or "").strip()
    if no_chase:
        return no_chase
    research_price = _float_or_none(analysis.get("price_plan", {}).get("research_price"))
    if research_price is not None:
        return f"研究價 {research_price:.2f}"
    latest_close = _float_or_none(analysis.get("technical", {}).get("latest_close"))
    if latest_close is not None:
        return f"現價附近 {latest_close:.2f}"
    return "尚未建立壓力"


def _stop_text(analysis: dict[str, Any]) -> str:
    timing = analysis.get("timing_gate", {})
    price_plan = analysis.get("price_plan", {})
    invalidation = _float_or_none(timing.get("invalidation_price")) or _float_or_none(price_plan.get("invalidation_price"))
    if invalidation is not None:
        return f"跌破 {invalidation:.2f} 時，波段假設失效。"
    ma = analysis.get("technical", {}).get("ma", {})
    ma60 = _float_or_none(ma.get("ma60"))
    if ma60 is not None:
        return f"跌破 MA60 {ma60:.2f} 且無利多修復時，波段假設失效。"
    return "尚未建立失效價；沒有失效價前不放大部位。"


def _has_signal(signals: list[dict[str, Any]], kind: str, tone: str) -> bool:
    return any(signal.get("kind") == kind and signal.get("tone") == tone for signal in signals)


def _candidate_core_data_limited(data_sources: dict[str, Any]) -> bool:
    return not is_trusted_source(data_sources.get("fundamental"), "fundamental") or not is_trusted_source(
        data_sources.get("price"), "price"
    )


def _candidate_status_prefix(candidate_status: str) -> str:
    labels = {
        "qualified_research": "合格候選",
        "wait_price": "等便宜價",
        "watch_only": "只觀察",
        "reject": "排除",
    }
    return labels.get(candidate_status, "只觀察")


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
