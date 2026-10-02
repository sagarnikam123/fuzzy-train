![Fuzzy Train Banner](./assets/fuzzy-train-github-banner-1280-640.png)

# fuzzy-train

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tested with: pytest](https://img.shields.io/badge/tested%20with-pytest-0A9EDC.svg?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Docker Pulls](https://img.shields.io/docker/pulls/sagarnikam123/fuzzy-train.svg?logo=docker&logoColor=white)](https://hub.docker.com/r/sagarnikam123/fuzzy-train)
[![Deploy: Kubernetes](https://img.shields.io/badge/deploy-Kubernetes-326CE5.svg?logo=kubernetes&logoColor=white)](k8s/)
[![Integration: SkyWalking](https://img.shields.io/badge/integration-Apache%20SkyWalking-E97E25.svg)](skywalking/README.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/sagarnikam123/fuzzy-train/pulls)


A versatile fake log generator for testing and development - runs anywhere.

## Overview

fuzzy-train generates realistic fake logs in multiple formats, perfect for:

### Testing Log Systems
- **Log Storage**: Loki, Elastic Stack, Graylog, Splunk, Datadog, SigNoz
- **Log Collectors**: Fluent-bit, Vector.dev, Grafana Alloy, Promtail, Filebeat
- **APM & Tracing Integrations**: Apache SkyWalking (see [skywalking/](skywalking/README.md))
- **Performance Testing**: Verify ingestion rates and query performance
- **Scalability Testing**: Test system behavior under high log volumes

### Development & Operations
- **Parser Development**: Test regex patterns and log parsing rules
- **Alert Testing**: Generate specific patterns to trigger monitoring alerts
- **Dashboard Development**: Create realistic data for visualization
- **Training & Demos**: Provide realistic data for learning environments

## Quick Start

### Python (default)
```bash
# Optional: install faker for broad, realistic log data (enabled automatically when present)
pip install -r requirements.txt

python3 fuzzy-train.py
```

> **Realistic data:** When the [`faker`](https://pypi.org/project/Faker/) package is installed, logs are automatically enriched with realistic contextual data (IPs, HTTP methods/paths, user-agents, hostnames, usernames, companies, etc.) across all formats. Docker/Kubernetes images ship with faker included, so they are always enriched. If faker is not installed, fuzzy-train gracefully falls back to its built-in generator — the instant, zero-dependency fast path is unchanged. No CLI flags changed.

### Docker (default)
```bash
docker pull sagarnikam123/fuzzy-train:latest
docker run --rm sagarnikam123/fuzzy-train:latest
```


## Sample output

What the logs look like (varies each run). Commands are shown once here; flag details live in [Parameters](#parameters).

### Default JSON — `python3 fuzzy-train.py`

```text
{"timestamp": "2026-10-02T12:55:10.660305+05:30", "level": "DEBUG", "message": "Crawford, Mueller and Valentine processed request for jnelson@example.org host web-44.perez.info r", "trace_id": "85483-00000001", "length": 98}
{"timestamp": "2026-10-02T12:55:11.672904+05:30", "level": "ERROR", "message": "CONNECT https://roach.com/ completed user lesliechristensen from 190.55.58.76 accessed sea", "trace_id": "85483-00000002", "length": 90}
{"timestamp": "2026-10-02T12:55:12.679090+05:30", "level": "WARN", "message": "user crystaldavis from 144.51.226.255 accessed app/category Heavy grow ever good. Smith, Peterson an", "trace_id": "85483-00000003", "length": 100}
{"timestamp": "2026-10-02T12:55:13.683817+05:30", "level": "INFO", "message": "Should lose each make represent short movement loss. PUT https://lee.net/ completed Gilbert, Ber", "trace_id": "85483-00000004", "length": 96}
```

### HTTP access — `python3 fuzzy-train.py -f http --failure-rate 0.3 -n 4 --lines-per-second 1000`

```text
2026-10-02T12:59:23.680914+05:30 level=error method=GET url=/wp-content/tag status=500 duration=120ms
2026-10-02T12:59:23.685397+05:30 level=info method=GET url=/wp-content status=200 duration=181ms
2026-10-02T12:59:23.686981+05:30 level=error method=POST url=/main/explore status=500 duration=5302ms
2026-10-02T12:59:23.688670+05:30 level=info method=GET url=/tags/tags/posts status=200 duration=55ms
```

### Apache combined — `python3 fuzzy-train.py -f "apache combined" --failure-rate 0.5 -n 2 --lines-per-second 1000`

```text
122.137.13.94 - - [02/Oct/2026:12:59:54 +0000] "POST /categories/category HTTP/1.1" 200 98 "http://www.martinez.com/" "Opera/8.35.(X11; Linux x86_64; fil-PH) Presto/2.9.168 Version/10.00"
135.104.18.192 - - [02/Oct/2026:12:59:54 +0000] "POST /app/wp-content HTTP/1.1" 200 91 "http://www.jones.org/" "Mozilla/5.0 (Windows; U; Windows 98; Win 9x 4.90) AppleWebKit/535.40.4 (KHTML, like Gecko) Version/4.1 Safari/535.40.4"
```

## Features

- **Formats**: JSON, logfmt, HTTP access, Apache (common/combined/error), BSD syslog (RFC3164), Syslog (RFC5424)
- **Rate & content**: `--lines-per-second`, message length, `local`/`UTC` timestamps
- **Deploy anywhere**: Python, Docker, Kubernetes (Deployment/DaemonSet)
- **trace_id**: PID/container ID or integer; omit with `--no-trace-id` (see [Important Notes](#important-notes))
- **Realistic data**: optional [faker](https://pypi.org/project/Faker/) enrichment (see [Quick Start](#quick-start)); zero-dependency fallback
- **Output**: stdout, file, or both; directory paths auto-create `fuzzy-train.log`
- **Opt-in controls**: `--count` / `--max-bytes`, `--compress`, `--split-by`, `--time-step`, `--failure-rate`, `--arrival` (see [Parameters](#parameters))

## Important Notes

### Container Behavior
When running in containers (Docker, Podman, Kubernetes), the trace_id uses the container/pod identifier instead of PID for better tracking across multiple instances:
- **Local execution**: Uses actual PID (e.g., `15432-00000001`)
- **Docker/Podman**: Uses container hostname (e.g., `a1b2c3d4e5f6-00000001`)
- **Kubernetes**: Uses truncated pod hash from pod name (12 chars, e.g., `abc123def456-00000001`)

Use `--no-trace-id` to exclude trace_id field, or `--trace-id-type integer` for incremental integers instead of PID/Container ID.

## Usage

### Python Script Usage

Default JSON run is in [Quick Start](#quick-start); sample lines are in [Sample output](#sample-output).

#### Get help and version
```bash
python3 fuzzy-train.py --help
python3 fuzzy-train.py --version  # or -v
```

#### Apache common logs
Generates Apache common logs with custom length, high rate, UTC timezone, output to file:
```bash
python3 fuzzy-train.py \
    --min-log-length 100 \
    --max-log-length 200 \
    --lines-per-second 5 \
    --log-format "apache common" \
    --time-zone UTC \
    --output file \
    --file fuzzy-train.log
```

#### High-volume syslog
Generates syslog logs at high rate for load testing:
```bash
python3 fuzzy-train.py \
    --lines-per-second 10 \
    --log-format syslog \
    --time-zone UTC \
    --output file
```

#### Logfmt with simple trace IDs
Generates logfmt logs with incremental integer trace IDs:
```bash
python3 fuzzy-train.py \
    --log-format logfmt \
    --trace-id-type integer
```

#### Clean logs (no trace_id)
Generates logs without trace_id field for cleaner output:
```bash
python3 fuzzy-train.py --no-trace-id
```

#### Minimal logs (message only)
Generates logs with only the message field:
```bash
python3 fuzzy-train.py \
    --no-timestamp \
    --no-log-level \
    --no-length \
    --no-trace-id
```

#### Output to directory (auto-creates fuzzy-train.log)
```bash
python3 fuzzy-train.py --file /path/to/logs/
```

#### Output to both stdout and file
Passing `--file` alongside `--output stdout` writes to both destinations at once:
```bash
python3 fuzzy-train.py --output stdout --file fuzzy-train.log
```

#### Bounded, gzip, HTTP / failure-rate
See [Output Control](#output-control) for `--count` / `--max-bytes` / `--compress` / `--split-by` / `--time-step`, and [Log Content](#log-content) for `--failure-rate`, `--get-post-ratio`, durations, and `--arrival`. Shapes: [Sample output](#sample-output).

```bash
# Full HTTP simulator-style knobs (opt-in; defaults elsewhere unchanged)
python3 fuzzy-train.py -f http --failure-rate 0.05 --get-post-ratio 0.9 \
    --get-duration-ms 500 --post-duration-ms 2000 --arrival exponential \
    --lines-per-second 2 -n 20

# Bias ERROR/5xx on JSON without switching format
python3 fuzzy-train.py --failure-rate 0.2 -n 50 --lines-per-second 1000
```

### Docker Usage

Same image as [Quick Start](#quick-start). Pass CLI flags after the image name.

#### Run with custom parameters
```bash
docker run --rm -v "$(pwd)":/logs sagarnikam123/fuzzy-train:latest \
    --min-log-length 180 \
    --max-log-length 200 \
    --lines-per-second 2 \
    --time-zone UTC \
    --log-format logfmt \
    --output file \
    --file /logs/fuzzy-train.log
```

#### Run in background
```bash
docker run -d --name fuzzy-train-log-generator sagarnikam123/fuzzy-train:latest \
    --lines-per-second 2 --log-format JSON
```

#### Bounded file output (volume mount)

Same flags as [Output Control](#output-control); mount a host directory for `--file`:

```bash
docker run --rm -v "$(pwd)":/logs sagarnikam123/fuzzy-train:latest \
    --count 1000 --lines-per-second 1000 --split-by 200 --file /logs/app.log.gz
```

### Docker Compose Usage

#### File output (default)
Generates logs to `./logs/` directory - useful for testing log file scrapers:
```bash
# Start services
docker-compose up -d

# View generated log files
ls -lh logs/
tail -f logs/auth-service.log

# Stop services
docker-compose down
```

#### Stdout output
Generates logs to stdout - useful for testing log collectors (Fluent-bit, Vector, Promtail):
```bash
# Start services
docker-compose -f docker-compose-stdout.yml up -d

# View logs
docker-compose -f docker-compose-stdout.yml logs -f auth-service

# Stop services
docker-compose -f docker-compose-stdout.yml down
```

> **Note**: Edit parameters in the `command` section of docker-compose files to customize log generation rates and formats.

### Kubernetes Deployment

#### Deploy to Kubernetes
```bash
# Deploy all manifests
kubectl apply -f k8s/

# Or deploy individually
kubectl apply -f k8s/deployment-file.yaml      # Writes logs to file
kubectl apply -f k8s/deployment-stdout.yaml    # Writes logs to stdout
kubectl apply -f k8s/daemonset-stdout.yaml     # DaemonSet - one pod per node
```

#### Check deployment status
```bash
# View all fuzzy-train resources
kubectl get deployments,daemonsets | grep fuzzy-train

# Check pod status
kubectl get pods -l app=fuzzy-train
kubectl get pods -l app=fuzzy-train-daemonset

# View logs from stdout deployment
kubectl logs -l app=fuzzy-train,output=stdout --tail=20

# View logs from daemonset
kubectl logs -l app=fuzzy-train-daemonset --tail=10 --prefix=true

# Check file logs (exec into container)
kubectl exec -it <pod-name> -- tail -f /logs/fuzzy-train.log
```

> **Note**: Edit parameters in the `args` section of the YAML files in `k8s/` directory to customize log generation.

## Parameters

Common options have short forms: `-f` (`--log-format`), `-o` (`--output`), `-n` (`--count`), `-b` (`--max-bytes`), `-w` (`--overwrite`), `-p` (`--split-by`), `-s` (`--time-step`).

### Basic Options
| Parameter | Description | Default |
|-----------|-------------|---------|
| `-h, --help` | Show help message and exit | - |
| `-v, --version` | Show version and exit | - |
| `-f, --log-format` | Output format: `JSON`, `logfmt`, `http`, `apache common`, `apache combined`, `apache error`, `bsd syslog`, `syslog` | `JSON` |
| `--lines-per-second` | Log lines generated per second | `1` |
| `-o, --output` | Output destination: `stdout` or `file` | `stdout` |
| `--file` | File or directory path for log output (auto-creates directories and default filename) | `fuzzy-train.log`* |

`*` Default filename is used only when writing to file (e.g., `--output file` or a directory passed to `--file`); the plain default run writes to stdout.

### Log Content
| Parameter | Description | Default |
|-----------|-------------|---------|
| `--min-log-length` | Minimum message length in characters | `90` |
| `--max-log-length` | Maximum message length in characters | `100` |
| `--time-zone` | Timestamp timezone: `local` or `UTC` | `local` |
| `--failure-rate` | Probability of `ERROR` / HTTP `500` (`0.0`–`1.0`). Unset = legacy mix; for `http` format unset means `0.0` (all 200) | `-` (unset) |
| `--get-post-ratio` | P(GET) vs POST for `http` / apache when set (`0.0`–`1.0`). `http` uses `0.9` if unset | `-` (unset) |
| `--get-duration-ms` | Mean GET duration (ms) for `--log-format http` | `500` |
| `--post-duration-ms` | Mean POST duration (ms) for `--log-format http` | `2000` |
| `--arrival` | Inter-arrival pacing: `fixed` or `exponential` | `fixed` |

### Field Control
| Parameter | Description | Default |
|-----------|-------------|---------|
| `--no-trace-id` | Exclude `trace_id` field | `false` |
| `--trace-id-type` | `pid` (uses PID/Container ID) or `integer` (simple counter) | `pid` |
| `--no-timestamp` | Exclude `timestamp` field | `false` |
| `--no-log-level` | Exclude log `level` field | `false` |
| `--no-length` | Exclude message `length` field | `false` |

### Output Control
All opt-in — the default remains infinite real-time streaming.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `-n, --count` | Generate exactly N lines then exit | `0` (infinite) |
| `-b, --max-bytes` | Generate until ≥ N bytes then exit (ignored when `--count` is set) | `0` (no cap) |
| `-w, --overwrite` | Truncate the output file before writing instead of appending | `false` |
| `--compress` | Gzip file output (auto-enabled when `--file` ends with `.gz`) | `false` |
| `-p, --split-by` | Rotate output file every N lines (or N bytes when `--max-bytes` is used) | `0` (no split) |
| `-s, --time-step` | Advance each log's timestamp by DURATION without real waiting (e.g. `10`, `20ms`, `5s`, `1m`) | `-` (real time) |

#### Bounded output examples
> Bounded runs use a high `--lines-per-second` so they finish fast (the default rate is 1 line/second).

```bash
# Generate exactly 1000 lines to a file, then exit
python3 fuzzy-train.py --count 1000 --lines-per-second 1000 --output file

# Generate ~1MB of logs then exit
python3 fuzzy-train.py --max-bytes 1048576 --lines-per-second 1000 --output file

# Gzip-compressed output (500 lines)
python3 fuzzy-train.py --file logs.gz --count 500 --lines-per-second 1000

# Split a 1000-line run into 200-line files (app.log, app1.log, ...)
python3 fuzzy-train.py --file app.log --count 1000 --split-by 200 --lines-per-second 1000

# 100 logs with timestamps spaced 1 minute apart, generated instantly
python3 fuzzy-train.py --count 100 --time-step 1m --time-zone UTC --lines-per-second 1000
```

## Verifying Output

Assert what you got (shapes live in [Sample output](#sample-output); flags in [Parameters](#parameters)). Use a high `--lines-per-second` on bounded runs so they finish quickly.

```bash
# Pretty-print a few JSON lines
python3 fuzzy-train.py -n 3 --no-trace-id --lines-per-second 1000 \
  | while read -r l; do echo "$l" | python3 -m json.tool; done

# Exact line count
python3 fuzzy-train.py -n 250 --lines-per-second 1000 -o file --file exact.log
test "$(wc -l < exact.log)" -eq 250 && echo "OK: 250 lines"

# Split + gzip
python3 fuzzy-train.py -n 1000 --lines-per-second 1000 --split-by 200 --file app.log.gz
ls app*.log.gz && gzip -dc app.log.gz | wc -l   # expect parts; first part readable
```

Automated coverage: [docs/BUILD.md](docs/BUILD.md#running-the-test-suite) (`pytest tests/ -q`).

## Development

For building the image (single- and multi-platform), pushing, and testing the container, see [docs/BUILD.md](docs/BUILD.md).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT](LICENSE) - see the LICENSE file for details.
