"""
Rate limiting (tiêu chí 7) — sliding window 60 giây lưu trong Redis.
"""
import hashlib
import time
import uuid
from fastapi import HTTPException
from redis.exceptions import RedisError
from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Giới hạn tối đa RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    key_digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    redis_key = f"ratelimit:{key_digest}"
    now = time.time()
    window_start = now - WINDOW_SECONDS

    try:
        r.zremrangebyscore(redis_key, 0, window_start)
        current_count = r.zcard(redis_key)

        if current_count >= settings.rate_limit_per_minute:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = WINDOW_SECONDS
            if oldest:
                retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now:.6f}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS * 2)
        pipe.execute()
    except HTTPException:
        raise
    except RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter store unavailable")
