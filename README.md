# fuzzy-train
a fake log generator

A flexible, containerized fake log generator 
- for testing log pipelines (Loki, Fluent Bit, vector, etc.)
- for generating customized random logs

## Features
- Customizable log length, format, rate, and output file.
- Supports JSON, logfmt, Apache, syslog, and more.
- Timezone-aware timestamps.
- Runs as Python script, Docker container or Kubernetes Deployment or Daemonset.
- Incremental trace_id with PID for tracking purpose when multiple instances runs

## Support
- Formats: Logfmt, JSON, Apache common, Apache combined, Apache error, BSD syslog (rfc3164), Syslog (rfc5424)
- Time zone: Local, UTC

## Usage

#### Default usage (JSON logs to stdout)
```
python3 fake-log-generator.py
```

#### Custom log length, x lines/sec, Apache combined format, UTC, to file
```
python3 fake-log-generator.py --min_log_length 90 --max_log_length 100 --lines_per_second 5 
--log_format "Apache combined" --time_zone UTC --output file --file fake.log
```

#### Both stdout and file
```
python3 fake-log-generator.py --output stdout --file fake.log
```

### Pull and Run from Docker Hub
```
docker pull sagarnikam123/fake-log-generator:latest
docker run --rm -d sagarnikam123/fake-log-generator:latest
```

### Run with Custom Parameters as container
```
docker run --rm -v "$(pwd)":/logs sagarnikam123/fake-log-generator:latest
--min_log_length 180
--max_log_length 200
--lines_per_second 2
--time_zone UTC
--log_format logfmt
--output file
--file /logs/fake.log
```

### Kubernetes Deployment
```
kubectl apply -f fake-log-generator-file.yaml
kubectl apply -f fake-log-generator-stdout.yaml
```

Edit parameters in the `args` section.

## Parameters
| Parameter            | Description                                    | Default     |
|----------------------|------------------------------------------------|-------------|
| `--min_log_length`   | Minimum log line length (chars)                | `90`        |
| `--max_log_length`   | Maximum log line length (chars)                | `100`       |
| `--lines_per_second` | Log lines generated per second                 | `1`         |
| `--pid`              | PID (process id to include in trace_id)        | `true`      |
| `--time_zone`        | `local` or `UTC`                               | `local`     |
| `--log_format`       | JSON, logfmt, Apache, syslog, etc.             | `JSON`      |
| `--output`           | stdout, file                                   | `stdout`    |
| `--file`             | Full file path (can include folders+file name) | `fake.log`  |

---

### Build Locally
```
docker build -t sagarnikam123/fake-log-generator:latest .
```

### Push to Docker Hub
```
docker login
docker push sagarnikam123/fake-log-generator:latest
```

---

## License

MIT
