"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Không ping Redis lúc import để app vẫn khởi động được và /health trả 200
ngay cả khi Redis chưa sẵn sàng.
"""
import redis
from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1.5,
    socket_timeout=1.5,
)


def redis_healthy() -> bool:
    """Ping Redis cho GET /ready; lỗi kết nối → False."""
    try:
        return bool(r.ping())
    except Exception:
        return False
