# Docker Log Generator Recipes

Run `fuzzy-train` in Docker to test local log forwarders, Docker log drivers, Loki Docker plugin, or Vector Docker source.

---

## 1. Quick `docker run` One-Liners

### Continuous JSON Logs (Default)
```bash
docker run -d --name log-streamer-json \
  sagarnikam123/fuzzy-train:latest \
  -f json -r 10 -z utc
```

### Multi-Line Stack Traces (Java / Spring Boot)
Test your Docker log driver or collector's multi-line parser:
```bash
docker run -d --name log-streamer-java \
  sagarnikam123/fuzzy-train:latest \
  --stack java --failure-rate 0.2 -r 2
```

### HTTP Access Log Simulation (Alert Testing)
```bash
docker run -d --name log-streamer-http \
  sagarnikam123/fuzzy-train:latest \
  -f http --failure-rate 0.1 -r 5
```

### High-Throughput Load (Stress Testing)
```bash
docker run -d --name log-streamer-load \
  sagarnikam123/fuzzy-train:latest \
  -f json -r 2000
```

---

## 2. Multi-Service Observability Simulation (`docker-compose`)

The included [`docker-compose-observability.yml`](docker-compose-observability.yml) launches 4 realistic microservices with different log formats and rates:

* **`order-service`**: Java Spring Boot logs with realistic multi-line stack traces on errors.
* **`auth-service`**: Structured JSON logs with high volume (1,000 lines/sec).
* **`api-gateway`**: HTTP access log simulator with status codes 200 and 500.
* **`legacy-app`**: Apache combined access logs.

### Start Simulation
```bash
docker compose -f examples/docker/docker-compose-observability.yml up -d
```

### Stream Specific Service Logs
```bash
docker compose -f examples/docker/docker-compose-observability.yml logs -f order-service
```

### Stop Simulation
```bash
docker compose -f examples/docker/docker-compose-observability.yml down
```

---

## 3. Fixed-Volume (1 GB, 10 GB) & Throughput Pacing (0.5 MB/s, 1.0 MB/s)

Control exact byte throughput and total volume to test ingestion rate limiters, storage quotas, and log rotation:

### A. Stream at 1.0 MB/sec until 1 GB is reached, then stop
Runs for ~17 minutes at 1.0 MB/s (`-r 4000`), then the container cleanly exits:
```bash
docker run --rm -v "$(pwd)/logs":/logs sagarnikam123/fuzzy-train:latest \
  -f json -r 4000 -b 1gb -o file --file /logs/benchmark-1gb.log
```

### B. Stream at 0.5 MB/sec until 10 GB is reached, then stop
Runs at ~0.5 MB/s (`-r 2000`) until 10 GB is reached:
```bash
docker run --rm -v "$(pwd)/logs":/logs sagarnikam123/fuzzy-train:latest \
  -f json -r 2000 -b 10gb -o file --file /logs/benchmark-10gb.log
```

### C. Generate 10 GB split into 1 GB rotated files
Generates ten 1 GB files (`benchmark.log`, `benchmark1.log`, ..., `benchmark9.log`) and stops:
```bash
docker run --rm -v "$(pwd)/logs":/logs sagarnikam123/fuzzy-train:latest \
  -f json -r 5000 -b 10gb -p 1gb -o file --file /logs/benchmark.log
```

### D. Throughput Tuning Reference:
| Target Throughput | Format | Average Line Size | CLI Flag |
| :--- | :--- | :--- | :--- |
| **0.5 MB/sec** | `json` | ~250 B | `-r 2000` |
| **1.0 MB/sec** | `json` | ~250 B | `-r 4000` |
| **0.5 MB/sec** | `apache-combined` | ~300 B | `-r 1700` |
| **1.0 MB/sec** | `apache-combined` | ~300 B | `-r 3400` |
| **0.5 MB/sec** | `logfmt` | ~175 B | `-r 2900` |
| **1.0 MB/sec** | `logfmt` | ~175 B | `-r 5800` |

