# Deployment Information

## Public URL
https://agent-production-7b450600.up.railway.app

## Platform
Railway (project `day14-ai-agent`), gồm hai service: `agent` build từ `06-lab-complete/Dockerfile` theo `railway.toml` và database `Redis` chạy nội bộ trên cùng project.

## Test Commands

Đặt biến `BASE` và `AGENT_API_KEY` (lấy từ Railway Dashboard, không lưu trong code):

```bash
export BASE="https://agent-production-7b450600.up.railway.app"
export AGENT_API_KEY="<YOUR_RAILWAY_AGENT_API_KEY>"
```

### 4 lệnh tự kiểm tra (CP6)

```bash
# 1. Liveness health check -> 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness check (kiểm tra kết nối Redis trên cloud) -> 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Gọi /ask không có API key -> 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'

# 4. Gọi /ask có API key hợp lệ -> 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

### Kết quả kiểm tra thực tế

* `GET /health` trả về HTTP 200:
  ```json
  {"status":"ok","environment":"production","uptime_seconds":26.7}
  ```
* `GET /ready` trả về HTTP 200:
  ```json
  {"status":"ready","redis":"ok","environment":"production"}
  ```
* `POST /ask` (không gửi `X-API-Key`) trả về HTTP 401.
* `POST /ask` (gửi `X-API-Key` hợp lệ) trả về HTTP 200:
  ```json
  {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"input_tokens":2,"output_tokens":30,"cost_usd":1.83e-05}}
  ```

## Environment Variables Set

Các biến cấu hình trên service `agent` của Railway (đặt qua `railway variable set`, không đưa secret vào repo):

* `PORT` (`8000`)
* `ENVIRONMENT` (`production`)
* `REDIS_URL` (`${{Redis.REDIS_URL}}`, trỏ tới service Redis trên Railway)
* `AGENT_API_KEY` (khóa ngẫu nhiên đặt riêng trên Railway)
* `RATE_LIMIT_PER_MINUTE` (`10`)
* `DAILY_BUDGET_USD` (`1.0`)
* `LOG_LEVEL` (`INFO`)

## Screenshots
* [Deployment dashboard](screenshots/dashboard.png)
* [Service running](screenshots/running.png)
* [Test results](screenshots/test.png)
