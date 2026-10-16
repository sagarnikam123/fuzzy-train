# fuzzy-train Observability Examples & Recipes

Ready-to-use recipes and copy-paste examples for developers, SREs, and observability engineers testing log pipelines (**Fluent Bit**, **Vector.dev**, **Promtail / Loki**, **Logstash / Elasticsearch**, **SigNoz / OpenTelemetry**, and **Datadog**).

---

## Quick Navigation

| Target | Description | Path |
| :--- | :--- | :--- |
| 💻 **[Standalone Python](standalone/README.md)** | Run locally with zero dependencies or with Faker | [`examples/standalone/`](standalone/README.md) |
| 🐳 **[Docker & Compose](docker/README.md)** | Docker run one-liners and multi-service Docker Compose | [`examples/docker/`](docker/README.md) |
| ☸️ **[Kubernetes Manifests](k8s/README.md)** | Deployments & DaemonSets for Minikube, Kind, and EKS/GKE | [`examples/k8s/`](k8s/README.md) |

---

## Common Observability Scenarios At A Glance

### 1. Per-Node DaemonSets with Periodic Errors (1m / 3m)
Run on every node in the cluster (including control-plane nodes) to verify node-level collectors tailing `/var/log/pods`:
```bash
# Per-node multi-line stack traces with an error every 1 minute (-e 1m)
kubectl apply -f examples/k8s/daemonset-per-node-multiline.yaml

# Per-node structured JSON logs with an error every 1 minute (-e 1m)
kubectl apply -f examples/k8s/daemonset-per-node-json.yaml
```

### 2. Multi-Line Stack Trace Parsing (Fluent Bit / Vector evaluation)
Test whether your collector correctly aggregates multi-line exceptions into a single event instead of splitting each line:
```bash
# Standalone
python3 fuzzy-train.py --stack java --failure-rate 0.2 -r 5

# Standalone with 1m periodic error interval
python3 fuzzy-train.py --stack python -e 1m -r 2

# Docker
docker run --rm sagarnikam123/fuzzy-train:latest --stack python --failure-rate 0.3 -r 2

# Kubernetes Deployment
kubectl apply -f examples/k8s/multiline-stacktrace.yaml
```

### 3. Standard Continuous JSON Streaming (Loki / Elasticsearch / Datadog)
Generate structured JSON logs with trace IDs, log levels, and timestamps:
```bash
# Standalone
python3 fuzzy-train.py -f json -r 10 -z utc

# Docker
docker run --rm sagarnikam123/fuzzy-train:latest -f json -r 10 -z utc

# Kubernetes Deployment
kubectl apply -f examples/k8s/infinite-json-stdout.yaml
```

### 4. HTTP Access Log & Alert Rule Simulation (Prometheus / Grafana alerts)
Simulate realistic web server access logs with periodic 500 errors to verify alerting rules:
```bash
# Standalone: 10% 500 errors
python3 fuzzy-train.py -f http --failure-rate 0.1 -r 5

# Standalone: emit an error every 1 minute
python3 fuzzy-train.py -f http -e 1m -r 2

# Docker
docker run --rm sagarnikam123/fuzzy-train:latest -f http --failure-rate 0.1 -r 5

# Kubernetes Deployment
kubectl apply -f examples/k8s/http-access-simulator.yaml
```

### 5. High-Throughput / Pipeline Stress Testing
Benchmark ingestion rates, test rate limiters, or test backpressure handling:
```bash
# Standalone: 2,000 lines/sec
python3 fuzzy-train.py -r 2000 -f json

# Docker
docker run --rm sagarnikam123/fuzzy-train:latest -r 2000 -f json

# Kubernetes Deployment
kubectl apply -f examples/k8s/high-throughput-load.yaml
```

### 6. Multi-Service Environment Simulation
Spin up a multi-container environment generating mixed log formats (JSON, logfmt, Apache, and Java stack traces) simultaneously:
```bash
docker compose -f examples/docker/docker-compose-observability.yml up
```

### 7. Fixed-Volume & Throughput Benchmarking (0.5 MB/s, 1.0 MB/s, 1 GB, 10 GB)
Generate a precise volume of logs at a steady throughput rate, then cleanly exit:
```bash
# Standalone: 1.0 MB/sec until 1 GB is reached, then stop
python3 fuzzy-train.py -f json -r 4000 -b 1gb -o file --file test-1gb.log

# Standalone: 0.5 MB/sec until 10 GB is reached, then stop
python3 fuzzy-train.py -f json -r 2000 -b 10gb -o file --file test-10gb.log

# Docker: 1.0 MB/sec until 1 GB is reached, then stop
docker run --rm -v "$(pwd)/logs":/logs sagarnikam123/fuzzy-train:latest \
  -f json -r 4000 -b 1gb -o file --file /logs/benchmark-1gb.log

# Kubernetes Job (runs in 'fuzzy-train' namespace and stops at 1 GB):
kubectl apply -f examples/k8s/volume-benchmark-job.yaml
```

### 8. Advanced Multi-Argument Combinations
Looking to test backfills, bursty exponential traffic, or rotating gzip archives? See **[Standalone Power Combinations](standalone/README.md#6-power-combinations-real-world-observability-scenarios)** for recipes combining 4–7 CLI flags.

