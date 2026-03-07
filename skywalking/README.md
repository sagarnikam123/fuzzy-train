# fuzzy-train-skywalking

Fake log generators with SkyWalking integration. Generates realistic fake logs and sends them to SkyWalking via native log reporters.

Based on [fuzzy-train](https://github.com/sagarnikam123/fuzzy-train) - uses the same message generation logic.

## Variants

| Variant | Language | Agent | Log Reporter |
|---------|----------|-------|--------------|
| `fuzzy-train-skywalking-python` | Python 3.12 | apache-skywalking | Built-in log reporter |
| `fuzzy-train-skywalking-java` | Java 21 | SkyWalking Java Agent | Logback gRPC appender |

## Run Locally (Without SkyWalking)

For local testing without a SkyWalking backend:

### Python

```bash
# Install dependencies
pip3 install apache-skywalking

# Run with agent disabled (for local testing)
SW_AGENT_DISABLE=true python3 python/fuzzy-train-skywalking.py --lines-per-second 2

# Show help
SW_AGENT_DISABLE=true python3 python/fuzzy-train-skywalking.py --help

# Custom options
SW_AGENT_DISABLE=true python3 python/fuzzy-train-skywalking.py \
  --lines-per-second 5 \
  --min-log-length 120 \
  --max-log-length 150 \
  --trace-id-type integer
```

### Java

```bash
# Build the JAR
cd java
mvn clean package -DskipTests

# Run without SkyWalking agent (logs go to stdout only)
java -jar target/fuzzy-train-skywalking-1.0.0.jar --lines-per-second 2

# Show help
java -jar target/fuzzy-train-skywalking-1.0.0.jar --help

# Custom options
java -jar target/fuzzy-train-skywalking-1.0.0.jar \
  --lines-per-second 5 \
  --min-log-length 120 \
  --max-log-length 150 \
  --no-trace-id
```

## Quick Start (With SkyWalking)

### Docker

```bash
# Python version
docker run --rm sagarnikam123/fuzzy-train-skywalking-python:latest \
  --lines-per-second 2

# Java version
docker run --rm sagarnikam123/fuzzy-train-skywalking-java:latest \
  --lines-per-second 2
```

### Kubernetes

```bash
# Deploy both variants
kubectl apply -f k8s/

# Or deploy individually
kubectl apply -f k8s/python-deployment.yaml
kubectl apply -f k8s/java-deployment.yaml

# Check logs
kubectl logs -n skywalking-test -l app=fuzzy-train-python --tail=20
kubectl logs -n skywalking-test -l app=fuzzy-train-java --tail=20
```

## Build & Push

### Python

```bash
cd python
docker build -t sagarnikam123/fuzzy-train-skywalking-python:1.0.0 .
docker tag sagarnikam123/fuzzy-train-skywalking-python:1.0.0 sagarnikam123/fuzzy-train-skywalking-python:latest
docker push sagarnikam123/fuzzy-train-skywalking-python:1.0.0
docker push sagarnikam123/fuzzy-train-skywalking-python:latest
```

### Java

```bash
cd java
docker build -t sagarnikam123/fuzzy-train-skywalking-java:1.0.0 .
docker tag sagarnikam123/fuzzy-train-skywalking-java:1.0.0 sagarnikam123/fuzzy-train-skywalking-java:latest
docker push sagarnikam123/fuzzy-train-skywalking-java:1.0.0
docker push sagarnikam123/fuzzy-train-skywalking-java:latest
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SW_AGENT_NAME` | Service name in SkyWalking | `skywalking-test::fuzzy-train-*` |
| `SW_AGENT_COLLECTOR_BACKEND_SERVICES` | Satellite/OAP endpoint | `skywalking-satellite.skywalking.svc:11800` |
| `SW_AGENT_LOG_REPORTER_ACTIVE` | Enable log reporter (Python) | `true` |
| `SW_GRPC_LOG_SERVER_HOST` | Log server host (Java) | `skywalking-satellite.skywalking.svc` |
| `SW_GRPC_LOG_SERVER_PORT` | Log server port (Java) | `11800` |

### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--lines-per-second` | Log generation rate | `1` |
| `--log-levels` | Comma-separated levels (Python) | `INFO,WARN,ERROR,DEBUG` |
| `--level-weights` | Weights for each level (Python) | `60,20,10,10` |

## Verify in SkyWalking UI

1. Open SkyWalking UI
2. Select "General Service" layer
3. Find `skywalking-test::fuzzy-train-python` or `skywalking-test::fuzzy-train-java`
4. Go to "Log" tab to see generated logs

## Log Output

Both variants generate realistic application logs:

```
2026-03-06 14:30:15.123 [INFO] fuzzy-train - User alice logged in successfully from IP 192.168.1.45
2026-03-06 14:30:16.456 [WARN] fuzzy-train - High memory usage detected: 78% of heap used
2026-03-06 14:30:17.789 [ERROR] fuzzy-train - Failed to connect to database: Connection refused
2026-03-06 14:30:18.012 [DEBUG] fuzzy-train - Entering method processRequest with params: [id=abc123]
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  skywalking-test namespace                                                  │
│                                                                             │
│  ┌─────────────────────────┐    ┌─────────────────────────┐                 │
│  │  fuzzy-train-python     │    │  fuzzy-train-java       │                 │
│  │  + Python Agent         │    │  + Java Agent           │                 │
│  │  + Log Reporter         │    │  + Logback gRPC         │                 │
│  └───────────┬─────────────┘    └───────────┬─────────────┘                 │
│              │                              │                               │
│              │ gRPC :11800                  │ gRPC :11800                   │
│              │ (logs)                       │ (traces + logs)               │
│              │                              │                               │
└──────────────┼──────────────────────────────┼───────────────────────────────┘
               │                              │
               ▼                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  skywalking namespace                                                       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Satellite → OAP → BanyanDB → UI (Log tab)                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## License

MIT
