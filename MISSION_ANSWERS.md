# Day 14 Lab: Mission Answers

Lớp: K5-L3A. Bài tập cá nhân: Deployment, Benchmark & Observability.

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns trong `01-localhost-vs-production/develop/app.py`

1. Hardcode secrets trong mã nguồn (`develop/app.py`, dòng 17 đến 18): `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên GitHub public, key và mật khẩu sẽ bị lộ ngay. Ở bản `production/config.py` (dòng 27, 32), các giá trị này được đọc từ biến môi trường (`os.getenv("OPENAI_API_KEY", "")`, `os.getenv("AGENT_API_KEY", "")`) và có file `.env.example` làm mẫu thay vì commit `.env`.
2. Dùng `print()` để ghi log và in luôn API key (`develop/app.py`, dòng 33 đến 38): dòng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ secret trong log, còn chuỗi text tự do không có timestamp hay level nên khó lọc trên hệ thống log tập trung. Bản `production/app.py` (dòng 28 đến 32 và 111 đến 122) chuyển sang `logging` dạng JSON với các trường như `event`, `question_length`, `client_ip` và không ghi secret.
3. Thiếu endpoint health check và readiness (`develop/app.py`, dòng 42 đến 43): nền tảng cloud hoặc load balancer không kiểm tra được tiến trình còn sống hay đã sẵn sàng nhận request chưa. Bản `production/app.py` (dòng 135 đến 161) thêm `GET /health` cho liveness và `GET /ready` trả về 503 khi `is_ready` còn `False`.
4. Cố định `host="localhost"`, `port=8000` và bật `reload=True` (`develop/app.py`, dòng 49 đến 54): bind `localhost` khiến container không nhận được kết nối từ bên ngoài, port cố định không theo biến `PORT` do Railway hoặc Render cấp, còn `reload=True` chỉ nên dùng lúc dev. Bản `production/app.py` (dòng 194 đến 199) và `production/config.py` (dòng 17 đến 19) đọc `HOST` (mặc định `0.0.0.0`), `PORT` và chỉ bật `reload` khi `DEBUG=true`.
5. Không có graceful shutdown (`develop/app.py`): khi container dừng hoặc deploy bản mới, tiến trình bị ngắt ngang khi request còn đang chạy. Bản `production/app.py` (dòng 39 đến 67 và 180 đến 189) dùng `lifespan` để hạ cờ `is_ready = False` lúc tắt và đăng ký xử lý `SIGTERM`.
6. Thiếu quản lý cấu hình tập trung, CORS và kiểm tra đầu vào (`develop/app.py`, dòng 21 đến 22, 31): `DEBUG = True` và `MAX_TOKENS = 500` được gán cứng, còn `/ask` nhận `question` qua query param mà không kiểm tra rỗng. Bản `production/config.py` gom cấu hình vào `Settings.validate()` để báo lỗi sớm nếu thiếu `AGENT_API_KEY` khi `ENVIRONMENT=production`; `production/app.py` (dòng 77 đến 82, 102 đến 108) thêm `CORSMiddleware` và trả về 422 nếu thiếu `question`.

### Exercise 1.2: Kết quả chạy bản `develop`

Chạy `python app.py` trong `01-localhost-vs-production/develop/` và gửi câu hỏi qua query param:

```bash
curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"
```

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:38:50 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Khi chạy bản `01-localhost-vs-production/production/`:
* `GET /health`: `{"status":"ok","uptime_seconds":1.4,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:38:54.555537+00:00"}`
* `GET /ready`: `{"ready":true}`
* `POST /ask` với JSON `{"question":"Hello"}`: `{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}`

### Exercise 1.3: Bảng so sánh `develop` và `production`

| Feature | Develop (Basic) | Production (Advanced) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode trong `app.py` (`sk-...`, `password123`, `DEBUG=True`) | Đọc từ biến môi trường qua `config.py` (`Settings` và `validate()`) | Cùng một bản build chạy được ở dev, staging và production mà không cần sửa code, tránh lộ secret lên Git và phát hiện sớm khi thiếu cấu hình. |
| **Host & Port** | Cố định `host="localhost"`, `port=8000`, `reload=True` | `HOST=0.0.0.0`, `PORT` lấy từ env, `reload` phụ thuộc `DEBUG` | Container và các nền tảng như Railway, Render yêu cầu lắng nghe trên `0.0.0.0` theo cổng `$PORT` được cấp phát và tắt auto-reload khi chạy thật. |
| **Health / Readiness** | Không có | `GET /health` (liveness) và `GET /ready` (readiness, trả 503 khi chưa sẵn sàng) | Platform dựa vào `/health` để tự khởi động lại container bị treo; load balancer dựa vào `/ready` để chỉ gửi traffic vào instance đang hoạt động bình thường. |
| **Logging** | `print()` dạng text tự do, in cả `OPENAI_API_KEY` | Structured JSON logging qua `logging`, không log secret | Log JSON giúp các công cụ như Datadog, Loki hay ELK parse và lọc theo trường dễ dàng; bỏ secret ra khỏi log để tránh rò rỉ thông tin nhạy cảm. |
| **Shutdown** | Tắt đột ngột | Graceful shutdown qua `lifespan` và `SIGTERM` | Cho phép hoàn tất các request đang xử lý và ngừng nhận traffic mới trước khi thoát, tránh lỗi 502 lúc rolling deploy. |
| **API & CORS** | Nhận query param, không cấu hình CORS | Nhận JSON body có trả lỗi 422, cấu hình `CORSMiddleware` qua `ALLOWED_ORIGINS` | Từ chối sớm dữ liệu sai định dạng và chỉ cho phép các origin hợp lệ gọi API. |

## Part 2: Docker

### Exercise 2.1: Trả lời 4 câu hỏi về `02-docker/develop/Dockerfile`

1. Base image là `python:3.11`, bản Python 3.11 đầy đủ kèm toàn bộ công cụ hệ thống Debian nên dung lượng khá lớn (khoảng 1 GB).
2. Working directory là `/app` (khai báo bằng `WORKDIR /app`). Mọi lệnh `COPY`, `RUN`, `CMD` sau đó đều chạy trong thư mục này.
3. `COPY requirements.txt` và `RUN pip install` cần đứng trước `COPY app.py` để tận dụng Docker layer cache. File `requirements.txt` ít thay đổi hơn code ứng dụng; khi chỉ sửa `app.py`, Docker tái sử dụng layer đã cài thư viện thay vì tải và cài lại từ đầu.
4. `CMD` khai báo lệnh hoặc tham số mặc định khi chạy container và có thể bị ghi đè nếu truyền lệnh khác ở cuối `docker run`. Ngược lại, `ENTRYPOINT` cố định tiến trình chính của container; các tham số truyền thêm (hoặc viết trong `CMD`) sẽ trở thành đối số của `ENTRYPOINT`, muốn đổi hẳn thì phải dùng cờ `--entrypoint`.

### Exercise 2.2 và 2.3: Build image, Multi-stage build và so sánh dung lượng

Phân tích multi-stage build trong `02-docker/production/Dockerfile`:
* Stage 1 (`builder`, dùng `FROM python:3.11-slim AS builder`): cài các gói biên dịch `gcc`, `libpq-dev` rồi chạy `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
* Stage 2 (`runtime`, dùng `FROM python:3.11-slim AS runtime`): tạo user non-root `appuser`, chỉ `COPY --from=builder /root/.local` cùng `main.py` và `utils/mock_llm.py`, thêm `HEALTHCHECK` rồi chạy `uvicorn` với 2 workers.
* Image cuối nhỏ và ít rủi ro hơn vì toàn bộ `gcc`, header thư viện và cache cài đặt bị bỏ lại ở stage `builder`, còn tiến trình bên trong chạy dưới quyền `appuser` thay vì `root`.

Kết quả chạy và test container `my-agent:develop` (build từ gốc repo):

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name cp2-dev -p 8000:8000 my-agent:develop
curl -sS -i -X POST "http://localhost:8000/ask?question=What+is+Docker%3F"
```

```http
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

So sánh dung lượng đo trực tiếp bằng `docker images`:
* `my-agent:develop` (single-stage `python:3.11`): 1.67 GB (`1,667,775,855 bytes`, khoảng 1,667.8 MB)
* `my-agent:advanced` (multi-stage `python:3.11-slim`): 240 MB (`239,815,353 bytes`, khoảng 239.8 MB)
* Chênh lệch: giảm 85.6% (nhỏ hơn gần 7 lần, tiết kiệm khoảng 1.43 GB).

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

Sơ đồ các service trong stack:

```text
                ┌──────────────────────────┐
  Client ──────▶│  Nginx (port 80 / 443)   │  Reverse proxy + rate limit 10r/s + security headers
                └────────────┬─────────────┘
                             │ proxy_pass (internal bridge network)
                             ▼
                ┌──────────────────────────┐
                │   Agent (port 8000)      │  FastAPI + uvicorn (2 workers), không expose ra host
                └──────┬─────────────┬─────┘
                       │             │
        REDIS_URL      ▼             ▼      QDRANT_URL
            ┌──────────────┐   ┌──────────────┐
            │ Redis :6379  │   │ Qdrant :6333 │
            │(redis_data)  │   │(qdrant_data) │
            └──────────────┘   └──────────────┘
```

Khi chạy `docker compose -p k5-day14-docker ps`, stack gồm 4 service: `agent`, `nginx`, `redis` và `qdrant`, nối với nhau qua bridge network `internal` bằng tên service (`agent:8000`, `redis:6379`, `qdrant:6333`). Chỉ `nginx` mở cổng 80 và 443 ra máy host. Service `agent` khai báo `depends_on` kèm `condition: service_healthy` để chờ `redis` và `qdrant` khởi động xong trước.

Kết quả test qua Nginx:

```http
$ curl -sS -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":2.8,"version":"2.0.0","timestamp":"2026-11-25T08:44:12.255104"}
```

```http
$ curl -sS -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

## Part 3: Cloud Deployment

### Exercise 3.1: Deploy agent Part 6 lên Railway

* Public URL: https://agent-production-7b450600.up.railway.app
* Nền tảng và dịch vụ: Railway (project `day14-ai-agent`), gồm service `agent` build từ `06-lab-complete/Dockerfile` theo `railway.toml` và database `Redis` nối qua `${{Redis.REDIS_URL}}`. Biến `AGENT_API_KEY` được đặt trực tiếp trên Railway, không lưu trong code.
* Kết quả 4 lệnh tự kiểm tra CP6:
  * `GET /health` trả về 200 (`{"status":"ok","environment":"production","uptime_seconds":26.7}`)
  * `GET /ready` trả về 200 (`{"status":"ready","redis":"ok","environment":"production"}`)
  * `POST /ask` không có API key trả về 401
  * `POST /ask` có `X-API-Key` hợp lệ trả về 200 (`{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"input_tokens":2,"output_tokens":30,"cost_usd":1.83e-05}}`)
* Ảnh chụp màn hình: xem [DEPLOYMENT.md](DEPLOYMENT.md) và thư mục `screenshots/` (`dashboard.png`, `running.png`, `test.png`).

### Exercise 3.2: So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
|---|---|---|
| **Định dạng và phạm vi** | TOML, chỉ cấu hình build và deploy cho một service riêng lẻ (`[build]`, `[deploy]`). | YAML, hoạt động như file Infrastructure as Code (Blueprint) mô tả cả stack cùng lúc (`type: web`, `type: redis`, disk, region, plan). |
| **Cấu hình build** | Chọn `builder = "DOCKERFILE"` (hoặc `NIXPACKS`) kèm `dockerfilePath`, dùng `CMD` của Dockerfile hoặc `startCommand`. | Chọn `runtime: docker` (hoặc `python` với `buildCommand` và `startCommand`), hỗ trợ bật `autoDeploy: true`. |
| **Health check và restart** | Khai báo `healthcheckPath = "/health"`, `healthcheckTimeout`, `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries`. | Khai báo `healthCheckPath: /health`; Render tự lo restart và zero-downtime deploy. |
| **Biến môi trường và secret** | Không đặt trong `railway.toml`; cấu hình riêng trên Dashboard hoặc bằng CLI (`railway variables set ...`) và nối Redis qua biến tham chiếu nội bộ. | Khai báo danh sách `envVars` ngay trong `render.yaml`, hỗ trợ `generateValue: true` (Render tự sinh secret) hoặc `sync: false` (nhập tay trên Dashboard) để không commit secret. |
| **Vì sao khác nhau** | Railway quản lý tài nguyên (project, database, variables) qua Dashboard và CLI, nên file TOML chỉ giữ phần build và vòng đời chạy của service. | Render hướng đến đồng bộ toàn bộ hạ tầng từ Git theo mô hình Blueprint nên gom cả web service, Redis và danh sách env vào một file YAML. |

### Exercise 3.3: Mô tả pipeline CI/CD GCP Cloud Run (`03-cloud-deployment/production-cloud-run/`)

Khi có commit lên nhánh `main`, pipeline trong `cloudbuild.yaml` chạy lần lượt 4 bước: chạy `pytest` trong container `python:3.11-slim`, build Docker image có dùng layer cache (`--cache-from`) với hai tag `$COMMIT_SHA` và `latest`, đẩy image lên `gcr.io/$PROJECT_ID/ai-agent`, rồi gọi `gcloud run deploy` tới vùng `asia-southeast1` với `min-instances=1` (tránh cold start), `max-instances=10`, giới hạn 1 CPU / 512Mi RAM và lấy secret từ Google Secret Manager qua `--set-secrets`. File `service.yaml` đi kèm khai báo dịch vụ theo chuẩn Knative (`serving.knative.dev/v1`), quy định `containerConcurrency: 80`, tham chiếu secret bằng `secretKeyRef`, cùng `livenessProbe` ở `/health` và `startupProbe` ở `/ready`.

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/`)

* API key được kiểm tra trong dependency `verify_api_key` (`04-api-gateway/develop/app.py`, dòng 39 đến 54). Hàm này đọc header `X-API-Key` bằng `APIKeyHeader(name="X-API-Key", auto_error=False)` và được gắn vào `/ask` qua `Depends(verify_api_key)`.
* Nếu thiếu header, server trả về HTTP 401 Unauthorized; nếu sai key, bản develop trả về HTTP 403 Forbidden (ở Part 6 gộp cả hai trường hợp về HTTP 401 theo yêu cầu script chấm).
* Để xoay vòng (rotate) key mà không gây gián đoạn, server nên chấp nhận đồng thời nhiều key qua biến môi trường (ví dụ `AGENT_API_KEYS=old_key,new_key`): thêm `new_key` song song với `old_key` và deploy, chuyển lần lượt client sang `new_key`, theo dõi cho đến khi hết request dùng `old_key` rồi mới xóa `old_key`.

Kết quả test thực tế với `AGENT_API_KEY=secret-key-123`:

Thiếu key (401):
```http
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 08:41:28 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Có key hợp lệ (200):
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:41:28 GMT
server: uvicorn
content-length: 145
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 4.2: JWT Authentication (`04-api-gateway/production/`)

Client gọi `POST /auth/token` với `{"username": "student", "password": "demo123"}`. Hàm `authenticate_user` và `create_token` trong `auth.py` kiểm tra tài khoản rồi ký JWT bằng thuật toán HS256 chứa `sub`, `role`, `iat` và `exp` (hết hạn sau 60 phút). Khi client gửi `Authorization: Bearer <token>` lên `POST /ask`, `verify_token` kiểm tra chữ ký và thời hạn trực tiếp từ token mà không phải truy vấn database.

Token nhận được (đã che): `eyJhbGciOiJI...[REDACTED]`

Kết quả gọi `/ask` với Bearer token (200 OK kèm security headers):
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:41:33 GMT
server: uvicorn
content-length: 215
content-type: application/json
vary: Origin
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}
```

### Exercise 4.3: Rate Limiting (`04-api-gateway/production/rate_limiter.py`)

* Thuật toán được dùng là Sliding Window Counter. Mỗi user có một `deque` lưu timestamp các request trong 60 giây gần nhất; mỗi lần gọi, hàm `check()` xóa các timestamp cũ hơn `now - 60`, nếu số lượng còn lại lớn hơn hoặc bằng `max_requests` thì trả về 429 Too Many Requests kèm `Retry-After` và các header `X-RateLimit-*`.
* Giới hạn mặc định: tài khoản `student` (role `user`) được 10 request/phút, tài khoản `teacher` (role `admin`) được 100 request/phút.
* Để nới hoặc bỏ qua giới hạn cho admin, `app.py` (dòng 141) đọc `user["role"]` từ JWT để chọn `rate_limiter_admin` thay cho `rate_limiter_user` (hoặc có thể bỏ qua bước kiểm tra nếu `role == "admin"`).

Kết quả chạy vòng lặp gửi tiếp request 2 đến 13 với token của `student` (sau 1 request ở Exercise 4.2):
```text
Req 2..10: HTTP 200
Req 11: HTTP 429 -> {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
Req 12: HTTP 429 -> {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
Req 13: HTTP 429 -> {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

Response `curl -i` khi chạm ngưỡng 429:
```http
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 08:41:35 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795596155
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost Guard

Rate limiting chỉ chặn số lượt gọi trong một phút, trong khi chi phí LLM phụ thuộc vào số token và loại model. Một số ít request có prompt dài vẫn có thể tiêu tốn ngân sách rất nhanh nếu không có giới hạn chi tiêu. Vì vậy cần kết hợp thêm Cost Guard để khóa theo tổng tiền USD theo ngày hoặc tháng.

Cách triển khai Cost Guard dùng Redis cho môi trường nhiều instance:
1. Tạo key theo chu kỳ thời gian trong Redis (như `cost:daily:YYYY-MM-DD` hoặc `budget:{user_id}:YYYY-MM`) kèm TTL tự hết hạn sau khi qua chu kỳ.
2. Trước khi gọi LLM (`check_budget`), đọc tổng tiền hiện tại trong Redis; nếu đã đạt hoặc vượt ngân sách thì trả về HTTP 402 Payment Required, còn khi chạm 80% thì ghi log cảnh báo.
3. Sau khi có kết quả LLM (`record_cost`), tính tiền theo đơn giá input/output token rồi cộng dồn bằng `INCRBYFLOAT` và đặt `EXPIRE` để mọi worker dùng chung một bộ đếm nhất quán.

## Part 5: Scaling & Reliability

### Exercise 5.1 và 5.2: Health/Readiness Checks và Graceful Shutdown (`05-scaling-reliability/develop/`)

`GET /health` (liveness) dùng để kiểm tra tiến trình còn sống hay đã treo; nếu thất bại liên tiếp, platform sẽ restart container. `GET /ready` (readiness) kiểm tra instance đã sẵn sàng nhận traffic hay chưa (đã nạp xong tài nguyên, kết nối được Redis/DB và chưa ở trạng thái tắt); nếu trả về 503, load balancer tạm ngừng gửi request mới tới instance đó nhưng không restart nó.

Kết quả test `05-scaling-reliability/develop/app.py`:
* `GET /health`: `{"status":"ok","uptime_seconds":1.3,"version":"1.0.0","environment":"development","checks":{"memory":{"status":"ok","used_percent":12.5}}}`
* `GET /ready`: `{"ready":true,"in_flight_requests":1}`
* Khi gửi `POST /ask?question=Long+task` và lập tức gửi `kill -TERM <PID>` sau 0.2 giây, request đang chạy vẫn hoàn tất với mã 200 trước khi server thoát:
  ```text
  {"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."} [HTTP 200]
  INFO:     Shutting down
  INFO:     127.0.0.1:54644 - "POST /ask?question=Long+task HTTP/1.1" 200 OK
  INFO:     Waiting for application shutdown.
  2026-11-25 08:44:20,664 INFO 🔄 Graceful shutdown initiated...
  2026-11-25 08:44:20,664 INFO ✅ Shutdown complete
  INFO:     Application shutdown complete.
  INFO:     Finished server process [3604]
  2026-11-25 08:44:20,665 INFO Received signal 15 — uvicorn will handle graceful shutdown
  ```

### Exercise 5.3 đến 5.5: Stateless Design và Load Balancing (`05-scaling-reliability/production/`)

Nếu lưu lịch sử hội thoại trong RAM của từng process, khi chạy 3 instance sau Nginx round-robin, request đầu của người dùng vào Instance 1 nhưng request tiếp theo lại sang Instance 2 (không có dữ liệu phiên trước), và mọi phiên đều mất sạch mỗi lần container khởi động lại. Chuyển toàn bộ session (`session:{session_id}`) sang Redis kèm TTL 3600 giây giúp các instance trở nên stateless và đọc được chung một lịch sử hội thoại.

Chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` trong `05-scaling-reliability/production/` (mở cổng 8080 với 3 container `agent`, `nginx` và `redis`), sau đó chạy `python test_stateless.py`:

```text
Session ID: 3bd40285-4919-4335-8569-fd709ac700b6

Request 1: [instance-036181]  Q: What is Docker?
Request 2: [instance-8cb76f]  Q: Why do we need containers?
Request 3: [instance-5af3e0]  Q: What is Kubernetes?
Request 4: [instance-036181]  Q: How does load balancing work?
Request 5: [instance-8cb76f]  Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-8cb76f', 'instance-036181', 'instance-5af3e0'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

Nginx đã xoay vòng 5 request qua đủ cả 3 instance (`instance-036181`, `instance-8cb76f`, `instance-5af3e0`), nhưng `GET /chat/{session_id}/history` vẫn trả về đủ 10 tin nhắn vì toàn bộ dữ liệu phiên nằm trên Redis.

## Part 6: Final Project (Output `check_production_ready.py`)

Chạy bản đầy đủ có Docker trong `06-lab-complete/` trên WSL2 Ubuntu 24.04 (`os.name == "posix"`):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Một vài thông số đo được từ lần chạy trên:
* Docker image multi-stage (`python:3.11-slim`, user non-root `appuser`, có `HEALTHCHECK`): build mất 35 giây, kích thước 238 MB (nhỏ hơn ngưỡng 500 MB).
* Rate limit và stateless: trả 429 sau đúng 5 request (`RATE_LIMIT_PER_MINUTE=5`), sau khi restart agent vẫn trả 429 nhờ sliding window sorted set lưu trong Redis.
* Structured logging: 17/17 dòng log của ứng dụng là JSON hợp lệ.
* Graceful shutdown: khi gửi `SIGTERM` lúc đang có request, request vẫn trả về 200 và tiến trình thoát với exit code 0; `docker stop` hoàn tất với exit code 0 trong 0.9 giây.

## AI Log

Công cụ sử dụng: Antigravity AI Assistant.

Các phần đã hỏi và nhận hỗ trợ:
1. Cài đặt môi trường Windows/WSL2/Docker: bật WSL2 Ubuntu 24.04, bật WSL integration trên Docker Desktop v4.100.1, tách 3 virtualenv Python (`day14-part6`, `day14-part4`, `day14-part7`) và cài đặt Railway CLI.
2. Part 1 đến Part 5: đối chiếu các lưu ý của lớp K5, chạy mẫu từng phần và rà soát yêu cầu chấm điểm.
3. Part 6 (`06-lab-complete/`): hỗ trợ triển khai `app/config.py`, `app/redis_client.py`, `app/auth.py` (so sánh key bằng `hmac.compare_digest`), `app/rate_limiter.py` (sliding window sorted set trên Redis), `app/cost_guard.py` (`INCRBYFLOAT` trên Redis), `app/main.py` (`JsonFormatter`, `/health`, `/ready`, `/ask`, gọi lại handler `SIGTERM` gốc của uvicorn), `Dockerfile` multi-stage (`--prefix=/install`), `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml` và `render.yaml`.
4. Part 7: hỗ trợ thêm metric `agent_question_length_chars` (Exercise 7.1), cập nhật `KNOWLEDGE_BASE` trong `mock_llm.py` để đạt 23/23 (0 regression), thêm `ENV PYTHONUSERBASE=/home/agent/.local` trong `benchmark-observability/production/Dockerfile` để sửa lỗi `ModuleNotFoundError: uvicorn` khi chạy bằng user non-root, viết `.github/workflows/eval.yml` và rà soát văn phong báo cáo.

Cách tự kiểm tra:
* Toàn bộ số liệu (dung lượng image, phản hồi HTTP 401/200/429, output `test_stateless.py`, kết quả `check_production_ready.py`, JSON từ `load_test.py` và `run_eval.py`, CSV của Locust, trace trên Jaeger và thời gian firing của alert) đều chạy trực tiếp trên máy WSL2/Docker Desktop và đối chiếu khớp với file nộp trong repo.
* Chạy đầy đủ `python check_production_ready.py` trong `06-lab-complete/` đạt `PASS 12/12` (`43/43 checks passed`), giữ nguyên `check_production_ready.py` và `golden_dataset.jsonl` không chỉnh sửa.
