from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.core.config import get_settings


async def analyze_news_sentiment(symbol: str, news: list[dict]) -> dict:
    settings = get_settings()
    headlines = [str(item.get("title", "")) for item in news if item.get("title")]
    if not headlines:
        return {"score": 0.0, "label": "neutral", "summary": "目前沒有可用新聞。", "headlines": []}

    if not settings.openai_api_key:
        score = _rule_based_score(headlines)
        return {
            "score": score,
            "label": _label(score),
            "summary": "未設定 OpenAI API key，使用規則式新聞情緒估計。",
            "headlines": headlines[:5],
            "model": None,
        }

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompt = {
        "symbol": symbol,
        "task": "Analyze Taiwan stock news sentiment for swing-trading research.",
        "headlines": headlines[:10],
        "output_schema": {
            "score": "float from -1 to 1",
            "label": "positive|neutral|negative",
            "summary": "Traditional Chinese concise rationale",
        },
    }
    try:
        response = await client.responses.create(
            model=settings.openai_model,
            input=[
                {
                    "role": "system",
                    "content": "You are a cautious financial news sentiment classifier. Do not give trading orders.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "sentiment_result",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "number", "minimum": -1, "maximum": 1},
                            "label": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                            "summary": {"type": "string"},
                        },
                        "required": ["score", "label", "summary"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        parsed = json.loads(response.output_text)
        return {
            "score": float(parsed["score"]),
            "label": parsed["label"],
            "summary": parsed["summary"],
            "headlines": headlines[:5],
            "model": settings.openai_model,
        }
    except Exception:
        score = _rule_based_score(headlines)
        return {
            "score": score,
            "label": _label(score),
            "summary": "OpenAI 情緒分析失敗，已改用規則式估計。",
            "headlines": headlines[:5],
            "model": None,
        }


def _rule_based_score(headlines: list[str]) -> float:
    positive = ["買超", "成長", "突破", "調升", "獲利", "需求", "展望佳", "新高"]
    negative = ["賣超", "衰退", "下修", "虧損", "跌破", "警示", "風險", "疲弱"]
    score = 0
    text = "\n".join(headlines)
    score += sum(text.count(word) for word in positive)
    score -= sum(text.count(word) for word in negative)
    return max(-1.0, min(1.0, score / 5))


def _label(score: float) -> str:
    if score > 0.25:
        return "positive"
    if score < -0.25:
        return "negative"
    return "neutral"
