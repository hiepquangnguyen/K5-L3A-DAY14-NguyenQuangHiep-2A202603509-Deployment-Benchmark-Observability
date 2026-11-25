# Benchmark & Observability Report: Day 14

**Họ tên:** Nguyễn Quang Hiệp (2A202603509)
**Ngày chạy:** 25/11/2026
**Môi trường:** Windows 10, WSL2 Ubuntu 24.04 (Python 3.12.3, 15.9 GB RAM) và Docker Desktop v4.100.1 (Docker 29.9.3, WSL 2 engine)

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | 95% request phản hồi dưới nửa giây để giữ cảm giác phản hồi nhanh, khớp với ngưỡng mặc định của `load_test.py` (p50 nền ở mức ~190 ms). |
| Error rate `/ask` | < 2.0 % | Chừa biên cho tỷ lệ lỗi nền khoảng 1% từ mock LLM upstream (503 tạm thời), giữ error budget 2% để phát hiện sự cố thật mà ít báo động giả. |
| Accuracy trên golden dataset | ≥ 85 % | Đảm bảo agent RAG trả lời đúng phần lớn câu hỏi trong bộ đánh giá và dùng làm ngưỡng quality gate trong CI (sau khi bổ sung KB đạt 100%). |

## 2. Benchmark hiệu năng (develop, `load_test.py`)

Ghi chú Exercise 7.1 (Prometheus metrics tại `/metrics`):
* 3 loại metric có trong output: Counter (`http_requests_total`), Gauge (`agent_in_flight_requests`), Histogram (`http_request_duration_seconds` và metric mới thêm `agent_question_length_chars` đo phân bố độ dài câu hỏi trong `develop/app.py`).
* Middleware gắn label `route` theo `route.path` (mẫu như `/ask`, các URL không khớp gán `unmatched`) thay vì `request.url.path`. Nếu dùng URL thật, khi bot quét hàng nghìn đường dẫn lạ (`/wp-admin`, `/.env`, `/a1b2c3`...) số lượng time series sẽ tăng không kiểm soát và làm tràn RAM của Prometheus.

### 2.1 Concurrency vs latency (agent v2, 300 requests, `MOCK_SLOW_RATE=0.03`)

Nguồn dữ liệu: `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 4.03 | 188.9 | 222.2 | 1683.4 | 1.33% | PASS |
| 10 | 34.57 | 193.7 | 233.2 | 1698.5 | 2.00% | PASS |
| 50 | 111.51 | 198.1 | 287.8 | 1687.8 | 0.67% | PASS |
| 100 | 51.14 | 919.2 | 3898.1 | 4547.5 | 1.33% | FAIL |

Nhận xét: RPS không tăng tuyến tính theo concurrency. Khi tăng concurrency từ 1 lên 10 rồi 50, vì agent chạy bất đồng bộ (`async`/`await`) và chủ yếu chờ I/O từ mock LLM nên RPS tăng từ 4.03 lên 34.57 rồi 111.51 req/s, trong khi p50 giữ quanh 189 đến 198 ms. Đến mức 100 kết nối đồng thời, một process uvicorn đơn lẻ bắt đầu bị nghẽn hàng đợi và event loop, khiến RPS tụt xuống còn 51.14 req/s còn độ trễ tăng mạnh (`p50=919.2 ms`, `p95=3898.1 ms`, trượt SLO `p95 ≤ 500 ms`).

### 2.2 Tail latency (agent v2, 300 requests, concurrency = 20)

Nguồn dữ liệu: `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|
| 0 | 195.5 | 233.6 | 265.9 |
| 0.03 (mặc định) | 230.8 | 241.0 | 1709.3 |
| 0.1 | 321.6 | 1679.3 | 1709.1 |

Nhận xét: Chỉ số p99 phản ứng mạnh nhất với request chậm, tiếp theo là p95 khi tỷ lệ request chậm vượt 5%. Khi tăng `MOCK_SLOW_RATE` từ 0 lên 0.03, `avg` chỉ nhích thêm 35.3 ms (từ 195.5 lên 230.8 ms) nhưng `p99` nhảy hơn 6 lần (từ 265.9 lên 1709.3 ms). Ở mức 0.1 (10% request chậm), `avg` mới ở 321.6 ms nhưng `p95` đã vọt lên 1679.3 ms và làm trượt SLO. Giá trị trung bình bị 90% đến 97% request nhanh kéo xuống nên che mất nhóm người dùng phải chờ gần 2 giây; đặt SLO theo p95 hoặc p99 mới bắt được vấn đề này.

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn dữ liệu: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---:|---:|---:|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.3 | 108.8 | 113.9 |
| Tổng cost (USD) | `$0.000393` | `$0.000758` | `$0.000793` |
| Cost / câu đúng (USD) | `$0.00039315` | `$0.00003607` | `$0.00003446` |
| Latency p50 / p95 (ms) | 169.6 / 187.4 | 177.3 / 209.1 | 172.1 / 219.3 |
| Quality gate | FAIL | PASS | PASS (0 regression) |

Những câu v2 trả lời sai ban đầu và cách sửa:

| ID | Keyword bị thiếu | Cách sửa |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm mục từ khóa `["jwt"]` mô tả sự khác nhau giữa API key và JWT (token có chữ ký số, chứa thông tin user và thời điểm hết hạn, xác minh stateless) vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` và chép sang `production/utils/mock_llm.py`. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm mục từ khóa `["hpa", "kubernetes", "autoscal"]` giải thích Kubernetes HPA tự scale số pod theo CPU, memory hoặc custom metrics vào `KNOWLEDGE_BASE` trong `mock_llm.py`. |

Nhận xét về trade-off giữa v1 và v2: Do v2 ghép thêm đoạn tài liệu truy xuất vào prompt, số token trung bình mỗi câu tăng gần gấp đôi (từ 56.3 lên 108.8 và 113.9), tổng chi phí tăng gần gấp đôi (từ `$0.000393` lên `$0.000793`) và p95 tăng thêm khoảng 20 đến 30 ms (từ 187.4 lên 209.1 và 219.3 ms). Đổi lại, độ chính xác tăng từ 4.3% lên 91.3% rồi 100.0% sau khi bổ sung knowledge base. Khi tính theo chi phí trên mỗi câu trả lời đúng, v2 (`$0.00003446`) rẻ hơn khoảng 11.4 lần so với v1 (`$0.00039315`).

Quality gate trong CI/CD (Exercise 7.3): Khi chạy thử `eval_v1` so với `--baseline reports/eval_v2.json`, script báo 20 câu regression, in `Quality gate: ❌ FAIL` và thoát với `exit code 1`. Workflow [`.github/workflows/eval.yml`](.github/workflows/eval.yml) chạy tự động trên mỗi `pull_request` vào nhánh `main`: bật agent v2 rồi chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85`. Nếu accuracy thấp hơn 85% hoặc xuất hiện regression, `exit code 1` sẽ làm job CI thất bại và chặn merge.

## 4. Observability stack (production)

### 4.1 Screenshot và trả lời Exercise 7.4

* [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [`screenshots/grafana-dashboard.png`](screenshots/grafana-dashboard.png)
* [x] Một trace chậm trong Jaeger (thấy span chiếm nhiều thời gian nhất): [`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)
* [x] Một trace lỗi trong Jaeger (có event `exception`): [`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)
* [x] Trang Alerts của Prometheus với 4 alert đang firing: [`screenshots/prometheus-alert-firing.png`](screenshots/prometheus-alert-firing.png)

Trả lời 4 câu hỏi Exercise 7.4 (quan sát khi chạy Locust 30 users, ramp up 5 trên 2 instance agent):
1. Trên Grafana lúc có tải 30 users (Traffic 18.2 req/s, Error rate 0.80%), `p95` là 296.62 ms (tooltip biểu đồ lúc 16:11:25 ghi `p95 = 294 ms`, `p50 = 176 ms`, `p99 = 1.84 s`) và `avg` là 236 ms (truy vấn Prometheus cùng thời điểm cho `p95 = 292.8 ms`, `avg = 230.8 ms`). Mức `avg` thấp hơn `p95` khoảng 60 ms và thấp hơn `p99` tới 1.6 giây do khoảng 3% request rơi vào slow tail (+1500 ms).
2. Nginx chia đều traffic giữa 2 instance. Truy vấn `sum by (instance) (rate(http_requests_total{job="agent", route="/ask"}[1m]))` ghi nhận `172.18.0.3:8000` đạt 3.53 req/s và `172.18.0.8:8000` đạt 2.95 req/s nhờ round-robin và cơ chế `resolve` DNS trong `nginx.conf`.
3. `input tokens/s` (497.7 tokens/s) lớn gần gấp đôi `output tokens/s` (260.4 tokens/s) vì mỗi request v2 đều gửi kèm `SYSTEM_PROMPT`, đoạn ngữ cảnh retrieve từ `KNOWLEDGE_BASE` và câu hỏi, trong khi phần trả lời ngắn hơn nhiều.
4. `curl http://localhost:8080/metrics` trả về `HTTP/1.1 404 Not Found` do `nginx/nginx.conf` có khối `location = /metrics { return 404; }`. Việc chặn này tránh lộ số liệu hệ thống, route và chi phí ra bên ngoài; chỉ Prometheus nằm trong mạng nội bộ `obs_net` mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống" và unit test alert rules

Chạy `docker run --rm -v "$PWD/prometheus:/p" --entrypoint promtool prom/prometheus:v3.16.0 test rules /p/alert_rules_test.yml` trả về `SUCCESS`.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi đến lúc firing | Panel phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`, giá trị đo `19.33% > 5%`) | 80.8 giây (~1 phút 21 giây) | Golden Signals Error rate chuyển đỏ; biểu đồ Requests/s theo status code (đường `503` tăng mạnh) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`, giá trị đo `1.96s > 1s`) | 136.2 giây (~2 phút 16 giây) | Golden Signals Latency p95 chuyển đỏ; biểu đồ Latency `/ask` vượt ngưỡng 1s |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`, giá trị đo `$9.92/giờ > $2/giờ`) | ~148 giây (~2 phút 28 giây) | Golden Signals LLM cost (1h) và biểu đồ Cost USD/giờ tăng khoảng 16 lần |
| D | `docker pause k5-day14-observability-agent-1` | `AgentInstanceDown` (`for: 30s`, `up == 0` trên `172.18.0.3:8000`) | 40.3 giây | Golden Signals Instances up giảm từ 2 xuống 1; target trên Prometheus chuyển `DOWN` |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | Không firing | Panel Retrieval hit ratio giảm về 0%, tokens/s giảm, bảng version đổi sang `v1` |

Ghi chú về thí nghiệm D: Dùng `docker pause` khiến container bị treo nhưng vẫn còn tên trong Docker DNS, nên Prometheus scrape bị timeout (`up == 0`) và kích hoạt `AgentInstanceDown`. Nếu dùng `docker stop`, container biến mất khỏi DNS nên Prometheus không coi đó là target bị down. Ngoài ra, lỗi `504 Gateway Timeout` do Nginx cắt kết nối (sau `proxy_read_timeout 10s`) không xuất hiện trên metric của agent vì request chưa hoàn tất ở app; khi chạy thật cần theo dõi thêm metric của Nginx và kiểm tra giả lập (synthetic check) từ bên ngoài.

Cách phát hiện sự cố kiểu thí nghiệm E trong production: Các metric hạ tầng (4 Golden Signals) chỉ biết service có trả 200 và chạy nhanh hay không, không đánh giá được câu trả lời đúng hay sai. Để bắt lỗi tụt chất lượng như chuyển nhầm sang `v1` hoặc hỏng bước retrieval, cần kết hợp chạy eval quality gate trên golden dataset trong CI trước khi deploy, chấm mẫu định kỳ traffic thật bằng LLM-as-a-judge (hoặc phản hồi thumbs-down của người dùng), và đặt cảnh báo riêng cho `retrieval_hit_ratio` nếu tụt bất thường.

### 4.3 Debug bằng trace

Trace chậm nhất đã phân tích ([`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)):

* `trace_id`: `b0132334a18a4d3039461c9a47a63169`
* Tổng thời gian: 1718.1 ms (Jaeger hiển thị 1.7s, gồm 4 span: `POST /ask`, `agent.run`, `agent.retrieve_context` mất 19.8 ms và `chat mock-llm-small`)
* Span chiếm nhiều thời gian nhất: `chat mock-llm-small` mất 1695.4 ms (chiếm 98.7% tổng thời gian), cho thấy request chậm là do lượt gọi LLM upstream chứ không phải bước tìm tài liệu hay code FastAPI.
* Dòng log JSON tương ứng (lọc bằng `docker compose -p k5-day14-observability logs --no-color agent | grep b0132334a18a4d3039461c9a47a63169`):

```json
{"ts": "2026-11-25T09:12:04.613373+00:00", "level": "INFO", "service": "observable-agent", "instance": "99e6784154f5", "event": "llm_call", "trace_id": "b0132334a18a4d3039461c9a47a63169", "span_id": "ed7881fa16918f98", "request_id": "485b96f24dea", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1695.4}
{"ts": "2026-11-25T09:12:04.613880+00:00", "level": "INFO", "service": "observable-agent", "instance": "99e6784154f5", "event": "http_request", "trace_id": "b0132334a18a4d3039461c9a47a63169", "span_id": "ed7881fa16918f98", "request_id": "485b96f24dea", "method": "POST", "route": "/ask", "status": 200, "ms": 1718.1}
```

Trace lỗi đã phân tích ([`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)):
* `trace_id`: `a49d85bcb22cf49d4eed4952da2997fa` (tổng thời gian 104 ms; span `chat mock-llm-small` mất 80.2 ms có event `exception`: `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`).
* Dòng log JSON cùng `trace_id`:
```json
{"ts": "2026-11-25T09:13:00.013599+00:00", "level": "INFO", "service": "observable-agent", "instance": "e9807602bcf8", "event": "llm_error", "trace_id": "a49d85bcb22cf49d4eed4952da2997fa", "span_id": "a15354f4e60216e1", "request_id": "9b1ea2fede73", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

## 5. Benchmark scaling (production, Locust headless, 100 users, ramp 10, 2 phút)

Nguồn dữ liệu: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`.

### Endpoint `POST /ask`

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---:|---:|---:|---:|---:|---:|
| 1 | 56.48 | 210 | 880 | 1700 | 75 (1.11%) |
| 3 | 59.35 | 200 | 250 | 1700 | 67 (0.95%) |

### Tổng hợp (`Aggregated`: `POST /ask` và `GET /health`)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---:|---:|---:|---:|---:|---:|
| 1 | 61.96 | 210 | 840 | 1700 | 75 (1.01%) |
| 3 | 65.69 | 190 | 240 | 1700 | 67 (0.86%) |

Giải thích kết quả: Khi chỉ chạy 1 container bị giới hạn `0.5 CPU`, tải 100 users làm hàng đợi xử lý cục bộ bị nghẽn (ngay cả `GET /health` cũng bị kéo `p95` lên 340 ms), đẩy `p95` của `/ask` lên 880 ms. Scale lên 3 instance giúp Nginx chia đều tải và kéo `p95` của `/ask` xuống còn 250 ms (`GET /health` giảm xuống 17 ms), RPS tăng từ 56.48 lên 59.35 req/s. Tuy nhiên, `p50` (~200 ms) và `p99` (1700 ms) gần như không đổi vì sau khi gỡ nghẽn CPU ở FastAPI, nút thắt còn lại nằm ở độ trễ nội tại của upstream LLM (~120 đến 180 ms nền, 20 ms retrieval và 3% request slow tail cộng thêm 1500 ms) cùng thời gian nghỉ giữa các lượt hỏi của user (`wait_time = 0.5–2s`). Thêm container chỉ xử lý được nghẽn tính toán phía agent chứ không rút ngắn được thời gian phản hồi hay lỗi 503 (~1%) từ nhà cung cấp LLM.

## 6. Kết luận

3 điều rút ra sau bài thực hành benchmark và observability:
1. Latency trung bình dễ gây hiểu nhầm khi có tail latency (ví dụ `MOCK_SLOW_RATE=0.03` chỉ tăng `avg` thêm 35 ms nhưng đẩy `p99` lên 1.7 giây). Cần đặt SLO theo `p95`/`p99` và đo ở nhiều mức concurrency để biết điểm bão hòa (như khi tụt RPS ở `c=100`).
2. Các chỉ số hạ tầng như RPS, latency và error rate không phát hiện được lỗi giảm chất lượng câu trả lời (thí nghiệm E với `v1`). Cần chạy eval trên golden dataset kèm theo dõi `cost / câu đúng` và khóa bằng quality gate trong CI.
3. Khi gắn `trace_id` xuyên suốt metrics, traces và logs, luồng điều tra sự cố đi rất gọn: Grafana và alert báo có vấn đề, Jaeger chỉ thẳng span `chat mock-llm-small` chiếm 98.7% thời gian, và lọc log JSON theo `trace_id` lấy ra ngay chi tiết request đó.

Các metric và alert nên bổ sung nếu đưa agent lên production thật:
* Metric ở tầng Nginx/Load Balancer: tỷ lệ lỗi `502`/`504` và `429` rate limit (những lỗi bị chặn trước khi vào tới ứng dụng).
* Metric cho Redis và Cost Guard: độ trễ kết nối Redis, mức dùng RAM, số lượt bị chặn `402` và cảnh báo sớm khi chi tiêu đạt 80% ngân sách ngày/tháng.
* Chỉ số chất lượng AI: cảnh báo khi `agent_retrieval_hit_ratio` tụt mạnh, kết hợp chấm mẫu online (LLM-as-a-judge) và đo thời gian tới token đầu tiên (TTFT) nếu bật streaming.
* Alertmanager để định tuyến alert `critical` sang Slack/PagerDuty và phân nhóm để tránh cảnh báo lặp.
