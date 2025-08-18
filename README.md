# fuzzy-train

[![Docker Hub](https://img.shields.io/docker/pulls/sagarnikam123/fuzzy-train)](https://hub.docker.com/r/sagarnikam123/fuzzy-train)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A versatile fake log generator for testing and development - runs anywhere.

## Overview

fuzzy-train generates realistic fake logs in multiple formats, perfect for:

### Testing Log Systems
- **Log Storage**: Loki, Elastic Stack, Graylog, Splunk, Datadog, SigNoz
- **Log Collectors**: Fluent-bit, Vector.dev, Grafana Alloy, Promtail, Filebeat
- **Performance Testing**: Verify ingestion rates and query performance
- **Scalability Testing**: Test system behavior under high log volumes

### Development & Operations
- **Parser Development**: Test regex patterns and log parsing rules
- **Alert Testing**: Generate specific patterns to trigger monitoring alerts
- **Dashboard Development**: Create realistic data for visualization
- **Training & Demos**: Provide realistic data for learning environments

## Features

- **Multiple Log Formats**: JSON, logfmt, Apache (common/combined/error), BSD syslog (RFC3164), Syslog (RFC5424)
- **Configurable Output**: Customizable log length, generation rate, and output destination
- **Timezone Support**: Local timezone or UTC timestamps
- **Flexible Deployment**: Python script, Docker container, or Kubernetes (Deployment/DaemonSet)
- **Process Tracking**: trace_id with either PID/Container ID or incremental integer for multi-instance tracking
- **Realistic Data**: Random log levels (INFO, WARN, DEBUG, ERROR) and varied content
- **Output Options**: stdout, file, or both simultaneously
- **Smart File Handling**: Accepts file paths or directory paths (auto-creates directories and default filename)

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

#### Output to both stdout and file
```bash
python3 fuzzy-train.py --output stdout --file fuzzy-train.log
```

#### Output to directory (auto-creates fuzzy-train.log)
```bash
python3 fuzzy-train.py --file /path/to/logs/
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
docker run --rm -d --name fuzzy-train-logs sagarnikam123/fuzzy-train:latest
```

### Kubernetes Deployment

#### Deploy to Kubernetes
```bash
kubectl apply -f fuzzy-train-file.yaml
kubectl apply -f fuzzy-train-stdout.yaml
```

> **Note**: Edit parameters in the `args` section of the YAML files to customize log generation.

## Important Notes

### Container Behavior
When running in containers (Docker, Podman, Kubernetes), the trace_id uses the container/pod identifier instead of PID for better tracking across multiple instances:
- **Local execution**: Uses actual PID (e.g., `15432-00000001`)
- **Docker/Podman**: Uses container hostname (e.g., `a1b2c3d4e5f6-00000001`)
- **Kubernetes**: Uses pod hash from pod name (e.g., `abc123def456-00000001`)

Use `--no-trace-id` to exclude trace_id field, or `--trace-id-type integer` for incremental integers instead of PID/Container ID.

## Parameters

### Basic Options
| Parameter            | Description                                    | Default     |
|----------------------|------------------------------------------------|-------------|
| `-v, --version`      | Show version and exit                          | -           |
| `--log-format`       | JSON, logfmt, 'apache common', 'apache combined', <br>'apache error', 'bsd syslog', syslog | `JSON`      |
| `--lines-per-second` | Log lines generated per second                 | `1`         |
| `--output`           | Output destination: stdout or file             | `stdout`    |
| `--file`             | File or directory path for log output <br>(auto-creates directories and default filename) | `fuzzy-train.log` |

### Log Content
| Parameter            | Description                                    | Default     |
|----------------------|------------------------------------------------|-------------|
| `--min-log-length`   | Minimum message length in characters          | `90`        |
| `--max-log-length`   | Maximum message length in characters          | `100`       |
| `--time-zone`        | Timestamp timezone: local or UTC              | `local`     |

### Field Control
| Parameter            | Description                                    | Default     |
|----------------------|------------------------------------------------|-------------|
| `--no-trace-id`      | Exclude trace_id field                         | `false`     |
| `--trace-id-type`    | pid (uses PID/Container ID) or <br>integer (simple counter) | `pid`       |
| `--no-timestamp`     | Exclude timestamp field                        | `false`     |
| `--no-log-level`     | Exclude log level field                        | `false`     |
| `--no-length`        | Exclude message length field                   | `false`     |

## Development

### Build locally
```bash
docker build -t sagarnikam123/fuzzy-train:2.1.1 .
docker tag sagarnikam123/fuzzy-train:2.1.1 sagarnikam123/fuzzy-train:latest
```

### Push to Docker Hub
```bash
docker login
docker push sagarnikam123/fuzzy-train:2.1.1
docker push sagarnikam123/fuzzy-train:latest
```

### Test locally
```bash
docker run --rm sagarnikam123/fuzzy-train:2.1.1
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT](LICENSE) - see the LICENSE file for details.
