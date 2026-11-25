"""
Production AI Agent — Part 6 Final Project.
"""
import json
import logging
import signal
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Định dạng mọi dòng log của app thành 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, dict):
            payload.update(extra_data)
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
        return json.dumps(payload, ensure_ascii=False)


def _setup_logger() -> logging.Logger:
    app_logger = logging.getLogger("production_agent")
    app_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    app_logger.propagate = False
    if not app_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        app_logger.addHandler(handler)
    return app_logger


logger = _setup_logger()
START_TIME = time.time()


def _log(level: int, event: str, **fields) -> None:
    logger.log(level, event, extra={"extra_data": {"event": event, **fields}})


# Graceful shutdown: ghi log SIGTERM rồi gọi lại handler cũ của uvicorn
_previous_sigterm = signal.getsignal(signal.SIGTERM)


def _on_sigterm(signum, frame):
    _log(logging.INFO, "sigterm_received", signal=signum)
    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)


signal.signal(signal.SIGTERM, _on_sigterm)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log(
        logging.INFO,
        "startup",
        environment=settings.environment,
        port=settings.port,
        rate_limit_per_minute=settings.rate_limit_per_minute,
        daily_budget_usd=settings.daily_budget_usd,
    )
    yield
    _log(logging.INFO, "graceful_shutdown_complete")
    try:
        r.close()
    except Exception:
        pass


app = FastAPI(title="Production AI Agent", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        _log(
            logging.ERROR,
            "unhandled_error",
            method=request.method,
            path=request.url.path,
            status=500,
            ms=elapsed_ms,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _log(
        logging.INFO,
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        ms=elapsed_ms,
    )
    return response


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(default=None, max_length=128)


@app.get("/health")
def health():
    """Liveness probe — luôn trả 200 khi process còn sống, không phụ thuộc Redis."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/ready")
def ready():
    """Readiness probe — 200 khi Redis kết nối được, 503 khi mất kết nối."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis is not available")
    return {"status": "ready", "redis": "ok", "environment": settings.environment}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    request_cost = record_cost(input_tokens, output_tokens)

    _log(
        logging.INFO,
        "ask_completed",
        user_id=body.user_id or "anonymous",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=request_cost,
    )
    return {
        "question": body.question,
        "answer": answer,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": request_cost,
        },
    }
