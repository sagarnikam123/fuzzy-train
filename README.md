![Fuzzy Train Banner](./assets/fuzzy-train-github-banner-1280-640.png)

# fuzzy-train

[![Docker Hub](https://img.shields.io/docker/pulls/sagarnikam123/fuzzy-train)](https://hub.docker.com/repository/docker/sagarnikam123/fuzzy-train)
[![GitHub](https://img.shields.io/github/stars/sagarnikam123/fuzzy-train?style=social)](https://github.com/sagarnikam123/fuzzy-train)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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

## Features

- **Multiple Log Formats**: JSON, logfmt, Apache (common/combined/error), BSD syslog (RFC3164), Syslog (RFC5424)
- **Configurable Output**: Customizable log length, generation rate, and output destination
- **Timezone Support**: Local timezone or UTC timestamps
- **Flexible Deployment**: Python script, Docker container, or Kubernetes (Deployment/DaemonSet)
- **Process Tracking**: trace_id with either PID/Container ID or incremental integer for multi-instance tracking
- **Realistic Data**: Random log levels (INFO, WARN, DEBUG, ERROR) and varied content; optional [faker](https://pypi.org/project/Faker/)-powered enrichment (IPs, HTTP methods/paths, user-agents, hostnames, usernames, companies) auto-enabled when installed, with zero-dependency fallback
- **Output Options**: stdout, file, or both simultaneously
- **Smart File Handling**: Accepts file paths or directory paths (auto-creates directories and default filename)
- **Bounded Generation**: Generate an exact number of lines (`--count`) or up to a byte size (`--max-bytes`) then exit — ideal for reproducible fixtures
- **Gzip Output**: Write compressed logs directly (`--compress` or a `.gz` filename)
- **File Splitting**: Rotate output into multiple files by line count or bytes (`--split-by`) for log-rotation testing
- **Fake Time Stepping**: Spread timestamps across a synthetic time range instantly (`--time-step`) without real waiting

## Important Notes

### Container Behavior
When running in containers (Docker, Podman, Kubernetes), the trace_id uses the container/pod identifier instead of PID for better tracking across multiple instances:
- **Local execution**: Uses actual PID (e.g., `15432-00000001`)
- **Docker/Podman**: Uses container hostname (e.g., `a1b2c3d4e5f6-00000001`)
- **Kubernetes**: Uses truncated pod hash from pod name (12 chars, e.g., `abc123def456-00000001`)

Use `--no-trace-id` to exclude trace_id field, or `--trace-id-type integer` for incremental integers instead of PID/Container ID.

## Usage

### Python Script Usage

#### Get help and version
```bash
python3 fuzzy-train.py --help
python3 fuzzy-train.py --version  # or -v
```

#### Default usage
Generates JSON logs to stdout with 90-100 character length, local timezone, trace_id=PID, 1 line per second:
```bash
python3 fuzzy-train.py
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

#### Bounded & file output
Generate a fixed amount then exit, overwrite instead of append, or gzip the output. These are opt-in — the default remains infinite streaming. Bounded runs use a high `--lines-per-second` so they finish fast (default rate is 1 line/second). See [Output Control](#output-control) for all options.
```bash
# Exactly 1000 lines then exit
python3 fuzzy-train.py --count 1000 --lines-per-second 1000 --output file

# Truncate (overwrite) the file instead of appending
python3 fuzzy-train.py --count 500 --lines-per-second 1000 --output file --overwrite

# Gzip output explicitly with --compress (or just use a .gz filename)
python3 fuzzy-train.py --count 500 --lines-per-second 1000 --file app.log --compress
```

### Docker Usage

#### Quick start
```bash
docker pull sagarnikam123/fuzzy-train:latest
docker run --rm sagarnikam123/fuzzy-train:latest
```

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

#### Bounded / gzip / split output (works in-container too)
```bash
# Generate 1000 lines to a mounted volume, then exit
docker run --rm -v "$(pwd)":/logs sagarnikam123/fuzzy-train:latest \
    --count 1000 --lines-per-second 1000 --file /logs/app.log

# Gzip + split into 200-line parts (app.log.gz, app1.log.gz, ...)
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
| `-f, --log-format` | Output format: `JSON`, `logfmt`, `apache common`, `apache combined`, `apache error`, `bsd syslog`, `syslog` | `JSON` |
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

Quick ways to run the generator and confirm it produced what you expect.

> **Tip:** the default rate is 1 line/second, so a bounded run like `--count 1000` would take ~1000s. Add a high `--lines-per-second` (e.g. `1000`) to finish bounded runs quickly.

### Eyeball logs on stdout
```bash
# Generate a few JSON logs and read them
python3 fuzzy-train.py --count 3

# Pretty-print each JSON line
python3 fuzzy-train.py --count 3 --no-trace-id | while read -r l; do echo "$l" | python3 -m json.tool; done

# Try another format
python3 fuzzy-train.py --count 3 --log-format "apache combined"
```

### Generate to a file and read it
```bash
python3 fuzzy-train.py --count 100 --lines-per-second 1000 --output file --file out.log
tail -f out.log        # follow live
wc -l out.log          # expect: 100 lines
```

### Decompress and read gzip output
```bash
python3 fuzzy-train.py --count 50 --lines-per-second 1000 --file out.log.gz
gzip -dc out.log.gz | head        # read without unzipping to disk
gzip -dc out.log.gz | wc -l       # expect: 50
```

### Validate --count and --split-by produced the right files
```bash
# 1000 lines split into 200-line files -> app.log, app1.log, app2.log, app3.log, app4.log
python3 fuzzy-train.py --count 1000 --lines-per-second 1000 --file app.log --split-by 200
ls app*.log            # expect: 5 files
wc -l app*.log         # each 200 lines, total 1000

# Confirm exact line count for a bounded run
python3 fuzzy-train.py --count 250 --lines-per-second 1000 --output file --file exact.log
test "$(wc -l < exact.log)" -eq 250 && echo "OK: 250 lines"
```

### Run the automated test suite
See [docs/BUILD.md](docs/BUILD.md#running-the-test-suite) for the pytest suite that covers every argument and their interacting combinations.

## Development

For building the image (single- and multi-platform), pushing, and testing the container, see [docs/BUILD.md](docs/BUILD.md).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT](LICENSE) - see the LICENSE file for details.
