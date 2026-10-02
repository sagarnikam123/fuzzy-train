# Language style fixtures

YAML files consumed by `fuzzy-train.py --style <name>`.

## Built-in styles

| `--style` | Aliases | Stack shape |
|-----------|---------|-------------|
| `java` | | JVM / log4j + `Caused by` (~100 SE8 Exception/Error fixtures) |
| `python` | | CPython `Traceback` (~50 built-in Exception/OSError fixtures) |
| `go` | | panics + wrapped/sentinel errors (~40 fixtures) |
| `rust` | | `panicked at` + backtrace |
| `csharp` | `c#`, `cs`, `dotnet` | .NET `Exception` + `at ...` |
| `ruby` | | Rails / Ruby backtrace |
| `javascript` | `node`, `nodejs`, `js` | Node.js `Error` / `TypeError` |

## Schema

- `info_messages`: one-line normal logs
- `errors`: list of `{name, body}` multiline stacks (or `{name, file}` pointing at a `.log` fixture)
- `timestamp_format`: optional strftime pattern for `{timestamp}` (supports `%3f` = millis, `%6f` = micros)

### Live timestamps

Hard-coded dates go stale. Use placeholders instead — substituted at emit time from the generator clock (respects `--time-step`):

| Placeholder | Meaning |
|-------------|---------|
| `{timestamp}` | Formatted with `timestamp_format` (language default if omitted) |
| `{iso}` | UTC ISO-8601 with millis + `Z` |
| `{date}` / `{time}` | `YYYY-MM-DD` / `HH:MM:SS` |
| `{epoch}` / `{epoch_ms}` | Unix seconds / milliseconds |

Example (`styles/java.yaml`):

```yaml
timestamp_format: "%Y-%m-%d %H:%M:%S,%3f"
info_messages:
  - "{timestamp} INFO  [http-nio-8080-exec-2] com.example.api.HealthController - health check ok"
errors:
  - name: null-pointer
    body: |
      {timestamp} ERROR [http-nio-8080-exec-1] com.example.api.OrderController - Failed to place order
      java.lang.NullPointerException: ...
```

## Examples

```bash
python3 fuzzy-train.py --style java --error-every 1000 --lines-per-second 5
python3 fuzzy-train.py --style python --error-interval 5m
python3 fuzzy-train.py --style go --failure-rate 0.05 -n 40
python3 fuzzy-train.py --style node --error-every 100   # alias for javascript
python3 fuzzy-train.py --style c# --error-every 50      # alias for csharp
```

`--style` defaults to `--log-format plain` so Fluent Bit / Vector can practice multiline parsers on real newlines.
Incompatible with `-f http` / apache access formats. Each error emit picks a random fixture from that style’s pool.
