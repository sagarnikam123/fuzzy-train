# fuzzy-train

[![Docker Hub](https://img.shields.io/docker/pulls/sagarnikam123/fuzzy-train)](https://hub.docker.com/r/sagarnikam123/fuzzy-train)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A flexible, containerized fake log generator for testing and development.

## Overview

fuzzy-train generates realistic fake logs in multiple formats, perfect for:
- Testing log pipelines (Loki, Fluent Bit, Vector, etc.)
- Load testing logging infrastructure
- Development and debugging of log processing systems
- Generating sample data for demonstrations

## Features

- **Multiple Log Formats**: JSON, logfmt, Apache (common/combined/error), BSD syslog (RFC3164), Syslog (RFC5424)
- **Configurable Output**: Customizable log length, generation rate, and output destination
- **Timezone Support**: Local timezone or UTC timestamps
- **Flexible Deployment**: Python script, Docker container, or Kubernetes (Deployment/DaemonSet)
- **Process Tracking**: trace_id with either PID/Container ID or incremental integer for multi-instance tracking
- **Realistic Data**: Random log levels (INFO, WARN, DEBUG, ERROR) and varied content
- **Output Options**: stdout, file, or both simultaneously

## Usage

### Python Script Usage

#### Get help
```bash
python3 fuzzy-train.py --help
```

#### Default usage
Generates JSON logs to stdout with 90-100 character length, local timezone, trace_id=PID, 1 line per second:
```bash
python3 fuzzy-train.py
```

#### Apache common
Generates Apache common logs with 100-200 characters length, trace_id=PID, 5 lines per second, UTC timezone, output to file (fuzzy-train.log)
```bash
python3 fuzzy-train.py \
    --min_log_length 100 \
    --max_log_length 200 \
    --lines_per_second 5 \
    --log_format "Apache common" \
    --time_zone UTC \
    --output file \
    --file fuzzy-train.log
```

#### Syslog (rfc5424)
Generates syslog logs, 90-100 characters length, 10 lines per second, trace_id=PID, local timezone, output to file (fuzzy-train.log)
```bash
python3 fuzzy-train.py \
    --lines_per_second 10 \
    --log_format "syslog" \
    --time_zone local \
    --output file
```

#### Logfmt (with no pid)
Generates logfmt logs, 90-100 characters length, trace_id=incremental integer, 1 line per second, local timezone, output to stdout
```bash
python3 fuzzy-train.py \
    --log_format logfmt \
    --pid false \
    --output stdout
```

#### Output to both stdout and file
```bash
python3 fuzzy-train.py --output stdout --file fuzzy-train.log
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
    --min_log_length 180 \
    --max_log_length 200 \
    --lines_per_second 2 \
    --time_zone UTC \
    --log_format logfmt \
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
- **Docker/Podman**: Uses container ID (e.g., `a1b2c3d4e5f6-00000001`)
- **Kubernetes**: Uses pod hash from pod name (e.g., `abc123def456-00000001`)

Use `--pid false` to generate simple incremental integers instead.

## Parameters
| Parameter            | Description                                    | Default     |
|----------------------|------------------------------------------------|-------------|
| `--min_log_length`   | Minimum log line length (chars)                | `90`        |
| `--max_log_length`   | Maximum log line length (chars)                | `100`       |
| `--lines_per_second` | Log lines generated per second                 | `1`         |
| `--pid`              | Include PID/Container ID in trace_id | `true`      |
| `--time_zone`        | `local` or `UTC`                               | `local`     |
| `--log_format`       | JSON, logfmt, syslog (rfc5424), bsd syslog (rfc3164), apache (common/error/combined), etc.             | `JSON`      |
| `--output`           | stdout, file                                   | `stdout`    |
| `--file`             | Full file path (can include folders+file name) | `fuzzy-train.log`  |

## Development

### Build locally
```bash
docker build -t sagarnikam123/fuzzy-train:2.1.0 .
docker tag sagarnikam123/fuzzy-train:2.1.0 sagarnikam123/fuzzy-train:latest
```

### Push to Docker Hub
```bash
docker login
docker push sagarnikam123/fuzzy-train:2.1.0
docker push sagarnikam123/fuzzy-train:latest
```

### Test locally
```bash
docker run --rm sagarnikam123/fuzzy-train:2.1.0
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT](LICENSE) - see the LICENSE file for details.
