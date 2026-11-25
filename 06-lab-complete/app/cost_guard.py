"""
Cost guard (tiêu chí 8) — theo dõi và giới hạn ngân sách LLM trong Redis.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from redis.exceptions import RedisError
from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
COST_TTL_SECONDS = 48 * 3600  # 2 ngày


def _daily_cost_key() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{today}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    try:
        raw = r.get(_daily_cost_key())
        spent = float(raw) if raw is not None else 0.0
    except RedisError:
        raise HTTPException(status_code=503, detail="Budget store unavailable")

    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Daily LLM budget exceeded",
                "spent_usd": round(spent, 6),
                "budget_usd": settings.daily_budget_usd,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    key = _daily_cost_key()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, COST_TTL_SECONDS)
        pipe.execute()
    except RedisError:
        pass
    return round(cost, 8)
