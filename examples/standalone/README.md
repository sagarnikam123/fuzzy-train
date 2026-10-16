# Standalone Python Log Generator Recipes

Direct `python3 fuzzy-train.py` recipes for local testing, CI pipelines, and developer environments.

---

## 1. Multi-Line Stack Trace Evaluation

Test if your log forwarder (Fluent Bit, Vector.dev, Promtail, Logstash) properly stitches multi-line stack traces into single events:

```bash
# Java Spring Boot / HikariCP stack traces (20% error rate, 5 lines/sec)
python3 fuzzy-train.py --stack java --failure-rate 0.2 -r 5

# Python FastAPI / SQLAlchemy / Uvicorn traces (1 error every 10s)
python3 fuzzy-train.py --stack python -e 10s -r 2

# Go panic & goroutine traces (10% panic rate)
python3 fuzzy-train.py --multiline go --failure-rate 0.1 -r 2

# Node.js Express / Prisma stack traces
python3 fuzzy-train.py --stack nodejs --failure-rate 0.2 -r 3

# .NET ASP.NET Core & EF Core stack traces
python3 fuzzy-train.py --stack dotnet --failure-rate 0.2 -r 3

# Ruby Rails & Sidekiq stack traces
python3 fuzzy-train.py --stack ruby --failure-rate 0.2 -r 3

# Rust Tokio runtime panic traces
python3 fuzzy-train.py --stack rust --failure-rate 0.1 -r 2

# PHP Laravel & PDO exception traces
python3 fuzzy-train.py --stack php --failure-rate 0.2 -r 2
```

---

## 2. Structured JSON & logfmt Logs

```bash
# Continuous JSON logs with UTC timestamps (10 lines/sec)
python3 fuzzy-train.py -f json -r 10 -z utc

# logfmt format (key="value") with incremental integer trace IDs
python3 fuzzy-train.py -f logfmt -r 5 --trace-id-type integer

# Minimal logs without timestamp or trace ID (message only)
python3 fuzzy-train.py -f json --no-timestamp --no-trace-id -r 5
```

---

## 3. Web Server & Access Log Simulation

```bash
# HTTP simulator access logs (status 200/500, GET/POST durations, methods, URLs)
python3 fuzzy-train.py -f http --failure-rate 0.05 -r 10

# Apache combined format (host, ident, auth, request, status, referer, User-Agent)
python3 fuzzy-train.py -f apache-combined -r 5 -z utc

# Apache common format with 10% 500 error rate
python3 fuzzy-train.py -f apache-common --failure-rate 0.1 -r 5

# Apache error logs
python3 fuzzy-train.py -f apache-error -r 2
```

---

## 4. Syslog Formats (RFC 3164 & RFC 5424)

```bash
# BSD Syslog (RFC 3164) with PRI facility/severity tags
python3 fuzzy-train.py -f rfc3164 -r 5

# Structured Syslog (RFC 5424) with host, app-name, proc-id, msg-id
python3 fuzzy-train.py -f rfc5424 -r 5 -z utc
```

---

## 5. Bounded Batches (Testing Ingestion Caps & Log Rotation)

```bash
# Generate exactly 1,000 lines at high speed (1000 lines/sec) then exit
python3 fuzzy-train.py -n 1000 -r 1000

# Generate ~5MB of JSON logs into a file, split into 1MB chunks
python3 fuzzy-train.py -f json -b 5mb -p 1mb -r 1000 -o app.log

# Generate gzip-compressed logs directly
python3 fuzzy-train.py -n 500 -r 1000 -c -o logs.gz

# Deterministic / reproducible logs using a seed (great for regression tests)
python3 fuzzy-train.py --seed 42 -n 100 -r 1000
```

---

## 6. Power Combinations (Real-World Observability Scenarios)

These multi-flag combinations model specific operational and testing workflows:

### A. Fast Historical Backfill (Fill Grafana / Kibana Dashboards Instantly)
Generate hours of past timeline in seconds using synthetic time-stepping without real waiting:
```bash
# 10,000 logs stamped 1s apart (~2.7 hours of history) generated in ~5s
python3 fuzzy-train.py -f json -n 10000 -s 1s -r 2000 -z utc -o historical.log
```

### B. Rotating Gzip Chunks for Log Forwarder File-Watchers
Test if Vector, Fluent Bit, or Promtail correctly tracks inode rotations and reads gzipped chunks:
```bash
# Generate 20MB of logs rotated into 5MB gzipped files (app.log.gz, app1.log.gz, ...)
python3 fuzzy-train.py -f json -b 20mb -p 5mb -c -r 2000 -o /tmp/logs/app.log
```

### C. Multi-Line Stack Traces Embedded in Structured JSON
Simulate modern structured logging libraries (e.g. Logback Logstash Encoder, Winston) where stack traces are fields inside JSON:
```bash
# Java stack traces embedded inside JSON objects emitted every 30 seconds
python3 fuzzy-train.py --stack java -f json -e 30s -r 5 -z utc
```

### D. Realistic Web Traffic Latency Profile
Simulate realistic API traffic with 85% fast GETs, 15% slow POSTs, and 5% server errors:
```bash
python3 fuzzy-train.py -f http \
  --get-post-ratio 0.85 \
  --get-duration-ms 150 \
  --post-duration-ms 1200 \
  --failure-rate 0.05 \
  -r 25
```

### E. Bursty Traffic Spikes (Poisson / Exponential Pacing)
Simulate realistic variable traffic instead of a fixed metronome sleep:
```bash
python3 fuzzy-train.py -f json --arrival exponential -r 20 --failure-rate 0.05
```

### F. Collector Benchmark Test (Apples-to-Apples Comparison)
Run deterministic, fixed-size workloads across collectors (e.g., Fluent Bit vs. Vector):
```bash
python3 fuzzy-train.py --seed 12345 -f json -n 50000 -r 5000 \
  --min-log-length 250 --max-log-length 350 -o benchmark.log
```

### G. Target Volume Cap & Steady Throughput (0.5 MB/s, 1.0 MB/s, 1 GB, 10 GB)
Generate a fixed volume of logs at a targeted MB/sec rate and exit automatically:
```bash
# 1.0 MB/sec stream (~4000 lines/sec) until exactly 1 GB is written:
python3 fuzzy-train.py -f json -r 4000 -b 1gb -o file --file run-1gb.log

# 0.5 MB/sec stream (~2000 lines/sec) until exactly 10 GB is written:
python3 fuzzy-train.py -f json -r 2000 -b 10gb -o file --file run-10gb.log

# Split a 10 GB generation into ten 1 GB chunks:
python3 fuzzy-train.py -f json -r 5000 -b 10gb -p 1gb -o file --file run-10gb.log
```

