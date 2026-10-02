#!/usr/bin/env python3
"""fuzzy-train: a versatile fake log generator for testing and development.

Streams or batch-generates fake logs in multiple formats (JSON, logfmt, HTTP
access, Apache common/combined/error, BSD RFC3164 and RFC5424 syslog). Log
content and format fields are enriched with realistic data via the optional
`faker` package when installed, and fall back to a built-in zero-dependency
generator otherwise.

Output control (all opt-in; infinite real-time streaming is the default):
bounded generation by line count or byte size, file overwrite, gzip output,
file splitting/rotation, and fake-time timestamp stepping.

HTTP access simulation (all opt-in; default JSON/logfmt/Apache behavior is
unchanged): --failure-rate, --get-post-ratio, --get-duration-ms,
--post-duration-ms, --arrival exponential, and --log-format http.

Language styles (opt-in): --style java|python loads real multiline stack
traces from styles/*.yaml for Fluent Bit / Vector multiline parser testing.
Pair with --log-format plain and --error-every / --error-interval /
--failure-rate to control how often full error blocks are emitted.
"""

import argparse
import math
import random
import time
import string
import os
import json
import socket
import sys
import gzip
import re
import itertools
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Optional faker enrichment: when installed, logs use broad realistic data;
# when absent, the script falls back to the built-in zero-dependency generator
# so the instant fast path keeps working byte-compatibly.
# ponytail: one shared module-scope Faker() instance — faker calls are the
# hot-path cost at high line rates (e.g. 2000 lines/sec), so we never create
# per-line instances. Not seeded, to preserve current run-to-run randomness.
try:
    from faker import Faker
    fake = Faker()
    FAKER_AVAILABLE = True
except ImportError:
    fake = None
    FAKER_AVAILABLE = False

try:
    import yaml  # PyYAML — required only for --style
    YAML_AVAILABLE = True
except ImportError:
    yaml = None
    YAML_AVAILABLE = False

# Log levels and example sentences
LOG_LEVELS = ["INFO", "ERROR", "DEBUG", "WARN"]
NON_ERROR_LEVELS = [lvl for lvl in LOG_LEVELS if lvl != "ERROR"]
DEFAULT_HTTP_STATUSES = [200, 404, 500, 302]
SENTENCES = [
    "Processing request from client.",
    "Database connection established successfully.",
    "Cache hit ratio is below threshold.",
    "User authentication completed.",
    "API request processing time exceeded limits.",
    "Memory usage is within normal parameters.",
    "Disk I/O operations completed.",
    "Network latency detected on primary interface.",
    "Configuration loaded from environment variables.",
    "Background task scheduler initiated.",
    "Garbage collection cycle completed.",
    "Service health check passed.",
    "Rate limiting applied to incoming requests.",
    "Thread pool resources allocated.",
    "Security policy validation completed.",
    "Data synchronization process started.",
    "Backup procedure executed successfully.",
    "Input validation performed on user data.",
    "Rendering engine initialized with default parameters.",
    "Encryption key rotation completed."
]

# Constants
__version__ = "2.6.0"
DETAIL_PROBABILITY = 0.3
# Trace ID sequence (itertools.count avoids a mutable module global + `global` stmt)
TRACE_ID_SEQ = itertools.count(1)

# Banner constant
BANNER = """┌─ FUZZY TRAIN ─────────────────────────────────────────────────────┐
│                                                                   │
│   ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄   │
│   █                                                           █   │
│   █  LOG GENERATION & TESTING FRAMEWORK                       █   │
│   █  Version {version} | Multi-format Support | Container Ready █   │
│   █                                                           █   │
│   ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀   │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘"""

def get_banner() -> str:
    """Return formatted banner with version number.

    Returns:
        str: Formatted banner with version number
    """
    version_padded = f"{__version__:<7}"  # Pad to 7 chars for alignment
    return BANNER.format(version=version_padded)

# Default configuration constants
DEFAULT_MIN_LOG_LENGTH = 90
DEFAULT_MAX_LOG_LENGTH = 100
DEFAULT_LINES_PER_SECOND = 1
DEFAULT_TRACE_ID_TYPE = "pid"
DEFAULT_TIME_ZONE = "local"
DEFAULT_LOG_FORMAT = "JSON"
DEFAULT_OUTPUT = "stdout"
DEFAULT_FILE = "fuzzy-train.log"

# Output-control defaults (flog-inspired). 0/None = feature off, preserving
# the infinite real-time streaming default.
DEFAULT_COUNT = 0        # 0 = infinite streaming (today's default)
DEFAULT_MAX_BYTES = 0    # 0 = no byte cap
DEFAULT_SPLIT_BY = 0     # 0 = no file splitting
DEFAULT_TIME_STEP = None  # None = real wall-clock timestamps

# HTTP / failure-rate defaults (all opt-in). None = legacy random mix unchanged.
DEFAULT_FAILURE_RATE = None
DEFAULT_GET_POST_RATIO = None  # None: unused except http format (uses 0.9)
DEFAULT_HTTP_GET_POST_RATIO = 0.9
DEFAULT_GET_DURATION_MS = 500
DEFAULT_POST_DURATION_MS = 2000
DEFAULT_ARRIVAL = "fixed"  # fixed | exponential

# Language style defaults (opt-in). None = legacy generator unchanged.
DEFAULT_STYLE = None
DEFAULT_ERROR_EVERY = 0       # 0 = off
DEFAULT_ERROR_INTERVAL = None  # None = off
STYLES_DIR = Path(__file__).resolve().parent / "styles"
# Friendly aliases -> styles/<name>.yaml stem
STYLE_ALIASES = {
    "node": "javascript",
    "nodejs": "javascript",
    "js": "javascript",
    "c#": "csharp",
    "cs": "csharp",
    "dotnet": "csharp",
    ".net": "csharp",
}

# Default {timestamp} formats per language (%3f = milliseconds).
# Override in YAML with timestamp_format: "..."
STYLE_TIMESTAMP_FORMATS = {
    "java": "%Y-%m-%d %H:%M:%S,%3f",
    "python": "%Y-%m-%d %H:%M:%S,%3f",
    "go": "%Y-%m-%dT%H:%M:%SZ",
    "rust": "%Y-%m-%dT%H:%M:%S.%3fZ",
    "csharp": "%Y-%m-%d %H:%M:%S.%3f +00:00",
    "ruby": "%Y-%m-%dT%H:%M:%S.%6f",
    "javascript": "%Y-%m-%dT%H:%M:%S.%3fZ",
}

def get_process_id() -> str:
    """Get process identifier based on environment (PID for local, container ID for containers).

    Returns:
        str: Process identifier string
    """
    # Check if running in any container
    if (os.path.exists('/.dockerenv') or
        os.path.exists('/proc/1/cgroup') or
        os.environ.get('container') or
        os.path.exists('/run/.containerenv')):  # Podman

        hostname = socket.gethostname()

        # For Kubernetes pods, extract the hash suffix
        if '-' in hostname:
            parts = hostname.split('-')
            if len(parts) >= 2:
                # Use last part (pod hash) + second-to-last if available
                return f"{parts[-2]}-{parts[-1]}"[:12] if len(parts) > 2 else parts[-1][:12]

        # Fallback to truncated hostname for Docker/Podman
        return hostname[:12]
    else:
        return str(os.getpid())

PID = get_process_id()

def generate_random_message(length: int) -> str:
    """Generate a random log message of specified length.

    When faker is available, the message is composed from varied faker providers
    (sentences plus contextual tokens like usernames, IPs, companies, URLs);
    otherwise it falls back to the built-in SENTENCES list with optional random
    detail suffixes. Either way the result is filled to at least `length` and
    truncated to exactly `length` characters.

    Args:
        length: Target message length in characters

    Returns:
        str: Generated message truncated to specified length
    """
    message = ""
    while len(message) < length:
        if FAKER_AVAILABLE:
            # Broad, contextual variety from many faker providers.
            sentence = random.choice([
                fake.sentence,
                lambda: f"user {fake.user_name()} from {fake.ipv4()} accessed {fake.uri_path()}",
                lambda: f"{fake.company()} processed request for {fake.email()}",
                lambda: f"{fake.http_method()} {fake.url()} completed",
                lambda: f"host {fake.hostname()} reported {fake.word()} event",
            ])()
        else:
            sentence = random.choice(SENTENCES)
            if random.random() < DETAIL_PROBABILITY:
                detail = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(10, 30)))
                sentence += f" Details: {detail}"
        message += sentence + " "
    return message[:length]

def generate_timestamp(time_zone: str, base: Optional[datetime] = None) -> str:
    """Generate ISO 8601 timestamp in specified timezone.

    Args:
        time_zone: 'local', 'UTC', 'utc', or 'LOCAL'
        base: Optional synthetic UTC datetime to use instead of the wall clock
              (used by --time-step to generate time-spread logs instantly)

    Returns:
        str: ISO 8601 formatted timestamp
    """
    now = base if base is not None else datetime.now(timezone.utc)
    if time_zone.lower() == "local":
        now = now.astimezone()
    # ISO 8601 with microseconds and Z for UTC
    if time_zone.upper() == "UTC":
        return now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        offset = now.strftime('%z')
        offset_fmt = f"{offset[:3]}:{offset[3:]}" if offset else ""
        return now.strftime(f"%Y-%m-%dT%H:%M:%S.%f{offset_fmt}")

def generate_trace_id(include_trace_id: bool, trace_id_type: str) -> Optional[str]:
    """Generate trace ID for log correlation.

    Args:
        include_trace_id: Whether to include trace ID
        trace_id_type: 'pid' for PID-based or 'integer' for simple counter

    Returns:
        Optional[str]: Generated trace ID or None
    """
    if not include_trace_id:
        return None

    counter = next(TRACE_ID_SEQ)
    if trace_id_type == "pid":
        return f"{PID}-{counter:08d}"
    else:  # integer
        return f"{counter:08d}"


def choose_log_level(failure_rate: Optional[float], failed: Optional[bool] = None) -> str:
    """Pick a log level.

    When failure_rate is None, preserves the legacy uniform mix over LOG_LEVELS.
    When set, ERROR is emitted with that probability; otherwise a non-ERROR level.
    Pass `failed` to keep level and HTTP status in sync for one line.
    """
    if failure_rate is None:
        return random.choice(LOG_LEVELS)
    if failed is None:
        failed = random.random() < failure_rate
    return "ERROR" if failed else random.choice(NON_ERROR_LEVELS)


def choose_http_status(failure_rate: Optional[float], failed: Optional[bool] = None) -> int:
    """Pick an HTTP status code.

    When failure_rate is None, preserves the legacy uniform mix.
    When set, 500 on failure and 200 on success (simulator-style).
    """
    if failure_rate is None:
        return random.choice(DEFAULT_HTTP_STATUSES)
    if failed is None:
        failed = random.random() < failure_rate
    return 500 if failed else 200


def choose_http_method(get_post_ratio: Optional[float],
                       default_ratio: float = DEFAULT_HTTP_GET_POST_RATIO) -> str:
    """Pick GET vs POST from a ratio (default 0.9 GET, matching the web simulator)."""
    ratio = default_ratio if get_post_ratio is None else get_post_ratio
    return "GET" if random.random() < ratio else "POST"


def choose_duration_ms(method: str, get_avg_ms: float, post_avg_ms: float) -> int:
    """Exponential duration (ms) with mean matching the method's average."""
    avg = get_avg_ms if method.upper() == "GET" else post_avg_ms
    if avg <= 0:
        return 0
    return int(math.floor(random.expovariate(1.0 / avg)))


def choose_http_url() -> str:
    """Pick a request path for HTTP access logs."""
    if FAKER_AVAILABLE:
        return "/" + fake.uri_path()
    return "/"



def load_style(name: str) -> Dict[str, Any]:
    """Load a language style YAML from styles/<name>.yaml.

    Supports inline error bodies and optional `file:` references relative to
    the styles directory (or absolute paths).
    """
    if not YAML_AVAILABLE:
        print("Error: --style requires PyYAML. Install with: pip install pyyaml")
        raise SystemExit(1)

    style_name = name.strip().lower()
    style_name = STYLE_ALIASES.get(style_name, style_name)
    path = STYLES_DIR / f"{style_name}.yaml"
    if not path.is_file():
        path = STYLES_DIR / f"{style_name}.yml"
    if not path.is_file():
        available = sorted({
            p.stem for p in (
                list(STYLES_DIR.glob("*.yaml")) + list(STYLES_DIR.glob("*.yml"))
            )
        }) if STYLES_DIR.is_dir() else []
        print(f"Error: style '{style_name}' not found under {STYLES_DIR}")
        if available:
            print(f"Available styles: {', '.join(available)}")
        raise SystemExit(1)

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    info = list(data.get("info_messages") or [])
    errors_raw = list(data.get("errors") or [])
    if not info and not errors_raw:
        print(f"Error: style '{style_name}' has no info_messages or errors")
        raise SystemExit(1)

    errors: List[Dict[str, str]] = []
    for err in errors_raw:
        if not isinstance(err, dict):
            continue
        body = err.get("body")
        rel = err.get("file")
        if body is None and rel:
            fpath = Path(rel)
            if not fpath.is_absolute():
                fpath = STYLES_DIR / fpath
            if not fpath.is_file():
                print(f"Error: style '{style_name}' error file not found: {fpath}")
                raise SystemExit(1)
            body = fpath.read_text(encoding="utf-8")
        if body is None:
            continue
        body = str(body).rstrip("\n")
        errors.append({"name": str(err.get("name") or "error"), "body": body})

    if errors_raw and not errors:
        print(f"Error: style '{style_name}' errors[] entries missing body/file")
        raise SystemExit(1)

    language = data.get("language") or style_name
    ts_fmt = data.get("timestamp_format") or STYLE_TIMESTAMP_FORMATS.get(
        str(language).lower(), "%Y-%m-%dT%H:%M:%S.%3fZ"
    )
    return {
        "language": language,
        "description": data.get("description") or "",
        "info_messages": info,
        "errors": errors,
        "timestamp_format": ts_fmt,
        "path": str(path),
    }


def format_style_timestamp(now: datetime, fmt: str) -> str:
    """Format `now` using a style timestamp_format.

    Supports printf-like extras beyond strftime:
      %3f  -> milliseconds (000-999)
      %6f  -> microseconds (000000-999999)
    """
    ms = f"{int(now.microsecond / 1000):03d}"
    us = f"{now.microsecond:06d}"
    # Substitute custom tokens before strftime (so %f is not double-expanded).
    prepared = fmt.replace("%3f", ms).replace("%6f", us)
    # Ensure timezone-aware UTC display for %z / Zulu styles.
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.strftime(prepared)


def style_template_vars(now: datetime, style: Dict[str, Any]) -> Dict[str, str]:
    """Placeholders available inside info_messages / error bodies."""
    fmt = style.get("timestamp_format") or STYLE_TIMESTAMP_FORMATS.get(
        str(style.get("language", "")).lower(), "%Y-%m-%dT%H:%M:%S.%3fZ"
    )
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ts = format_style_timestamp(now, fmt)
    # ISO: Z for UTC, numeric offset otherwise (respects --time-zone via caller).
    if now.utcoffset() == timezone.utc.utcoffset(now):
        iso = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    else:
        off = now.strftime("%z")
        iso = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + (
            f"{off[:3]}:{off[3:]}" if off else ""
        )
    return {
        "timestamp": ts,
        "ts": ts,
        "iso": iso,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "epoch": str(int(now.timestamp())),
        "epoch_ms": str(int(now.timestamp() * 1000)),
    }


_STYLE_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def render_style_text(template: str, now: datetime, style: Dict[str, Any]) -> str:
    """Substitute {timestamp} / {iso} / … in a style template string.

    Only replaces `{identifier}` tokens. Literal braces in stack fixtures
    (Rust `PoisonError { .. }`, JS object dumps, etc.) are left untouched —
    unlike str.format_map, which treats them as format fields and crashes.
    """
    vars_ = style_template_vars(now, style)

    def _repl(match: re.Match) -> str:
        key = match.group(1)
        return vars_[key] if key in vars_ else match.group(0)

    return _STYLE_PLACEHOLDER_RE.sub(_repl, str(template))



def resolve_style_clock(base: Optional[datetime], time_zone: str) -> datetime:
    """Wall/synthetic clock for style placeholders, honoring --time-zone."""
    now = base if base is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if time_zone.lower() == "local":
        return now.astimezone()
    return now.astimezone(timezone.utc)


def choose_style_info(style: Dict[str, Any], now: datetime) -> str:
    """Pick a one-line info message from the style (fallback if list empty)."""
    msgs = style.get("info_messages") or []
    if not msgs:
        return f"{style.get('language', 'app')}: ok"
    return render_style_text(str(random.choice(msgs)), now, style)


def choose_style_error(style: Dict[str, Any], now: datetime) -> str:
    """Pick a multiline error body from the style."""
    errors = style.get("errors") or []
    if not errors:
        return f"{style.get('language', 'app')}: error"
    return render_style_text(random.choice(errors)["body"], now, style)


def should_emit_style_error(
    lines_written: int,
    failure_rate: Optional[float],
    error_every: int,
    error_interval: Optional[float],
    last_error_at: Optional[datetime],
    now: datetime,
) -> Tuple[bool, Optional[datetime]]:
    """Decide whether this event is a full style error block.

    Precedence: --error-every, then --error-interval, then --failure-rate.
    --error-interval emits on the first event (last_error_at is None), then
    every DURATION thereafter — intentional for quick multiline smoke tests.
    Returns (is_error, updated_last_error_at).
    """
    if error_every and error_every > 0:
        return ((lines_written + 1) % error_every == 0), last_error_at

    if error_interval is not None and error_interval > 0:
        if last_error_at is None or (now - last_error_at).total_seconds() >= error_interval:
            return True, now
        return False, last_error_at

    if failure_rate is not None:
        return (random.random() < failure_rate), last_error_at

    return False, last_error_at


def format_plain_log(entry: Dict[str, Any]) -> str:
    """Emit message as-is (may contain embedded newlines for multiline stacks)."""
    return str(entry.get("message", ""))


def parse_entry_timestamp(entry: Dict[str, Any]) -> datetime:
    """Parse an entry's timestamp into a datetime for reformatting.

    Tries ISO 8601 (datetime.fromisoformat, tolerant of a trailing 'Z' and
    timezone offsets) and falls back to the fixed second-precision prefix.
    Robust to custom timestamp formats a future extension might introduce.

    Args:
        entry: Log entry dict; may contain a 'timestamp' string

    Returns:
        datetime: Parsed timestamp (tz-aware when the source includes an offset/Z)
    """
    ts = entry.get('timestamp')
    if not ts:
        return datetime.now(timezone.utc)
    try:
        # Normalize a trailing 'Z' (UTC) which older fromisoformat rejects.
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)

def format_json_log(entry: Dict[str, Any]) -> str:
    """Format log entry as JSON."""
    return json.dumps(entry)

def format_logfmt_log(entry: Dict[str, Any]) -> str:
    """Format log entry as logfmt.

    Escapes backslashes, quotes, and newlines so multiline --style stacks stay
    on one logical logfmt record.
    """
    parts = []
    for k, v in entry.items():
        s = (
            str(v)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
        parts.append(f'{k}="{s}"')
    return " ".join(parts)

def format_apache_common_log(entry: Dict[str, Any]) -> str:
    """Format log entry as Apache Common Log Format."""
    host = fake.ipv4() if FAKER_AVAILABLE else "127.0.0.1"
    ident = "-"
    user = "-"
    dt = parse_entry_timestamp(entry)
    if dt.tzinfo is None:
        tstr = dt.strftime("[%d/%b/%Y:%H:%M:%S +0000]")
    else:
        off = dt.strftime("%z") or "+0000"
        tstr = dt.strftime(f"[%d/%b/%Y:%H:%M:%S {off}]")
    method = entry.get("method")
    if method is None:
        method = fake.http_method() if FAKER_AVAILABLE else "GET"
    path = entry.get("url") or (("/" + fake.uri_path()) if FAKER_AVAILABLE else "/index.html")
    request = f"{method} {path} HTTP/1.1"
    status = entry.get("status")
    if status is None:
        status = random.choice(DEFAULT_HTTP_STATUSES)
    size = len(entry['message'])
    return f'{host} {ident} {user} {tstr} "{request}" {status} {size}'

def format_apache_combined_log(entry: Dict[str, Any]) -> str:
    """Format log entry as Apache Combined Log Format."""
    host = fake.ipv4() if FAKER_AVAILABLE else "127.0.0.1"
    ident = "-"
    user = "-"
    dt = parse_entry_timestamp(entry)
    if dt.tzinfo is None:
        tstr = dt.strftime("[%d/%b/%Y:%H:%M:%S +0000]")
    else:
        off = dt.strftime("%z") or "+0000"
        tstr = dt.strftime(f"[%d/%b/%Y:%H:%M:%S {off}]")
    method = entry.get("method")
    if method is None:
        method = fake.http_method() if FAKER_AVAILABLE else "GET"
    path = entry.get("url") or (("/" + fake.uri_path()) if FAKER_AVAILABLE else "/index.html")
    request = f"{method} {path} HTTP/1.1"
    status = entry.get("status")
    if status is None:
        status = random.choice(DEFAULT_HTTP_STATUSES)
    size = len(entry['message'])
    referer = fake.url() if FAKER_AVAILABLE else "https://example.com/"
    ua = fake.user_agent() if FAKER_AVAILABLE else "Mozilla/5.0 (compatible; FakeBot/1.0)"
    return f'{host} {ident} {user} {tstr} "{request}" {status} {size} "{referer}" "{ua}"'

def format_apache_error_log(entry: Dict[str, Any]) -> str:
    """Format log entry as Apache Error Log Format."""
    dt = parse_entry_timestamp(entry)
    tstr = dt.strftime("%a %b %d %H:%M:%S.%f %Y")
    pid = random.randint(1000, 99999)
    client_ip = fake.ipv4() if FAKER_AVAILABLE else "127.0.0.1"
    client = f"{client_ip}:{random.randint(1000, 65535)}"
    level = entry.get('level', 'info').lower()
    return f'[{tstr}] [core:{level}] [pid {pid}] [client {client}] {entry["message"]}'

def format_bsd_syslog_log(entry: Dict[str, Any]) -> str:
    """Format log entry as BSD Syslog (RFC3164)."""
    dt = parse_entry_timestamp(entry)
    tstr = dt.strftime("%b %d %H:%M:%S")
    # ponytail: enrich host only; PRI/tag/structure stay fixed (RFC3164 shape).
    host = fake.hostname() if FAKER_AVAILABLE else "localhost"
    tag = "fuzzy-train"
    pri = "<13>"  # user.notice
    return f'{pri}{tstr} {host} {tag}: {entry["message"]}'

def format_rfc5424_syslog_log(entry: Dict[str, Any]) -> str:
    """Format log entry as RFC5424 Syslog."""
    dt = parse_entry_timestamp(entry)
    tstr = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    # ponytail: enrich host only; PRI/app/proc_id/msg_id structure stays fixed (RFC5424 shape).
    host = fake.hostname() if FAKER_AVAILABLE else "localhost"
    app = "fuzzy-train"
    proc_id = str(os.getpid())
    msg_id = "ID1"
    pri = "<13>"  # user.notice
    return f'{pri}1 {tstr} {host} {app} {proc_id} {msg_id} - {entry["message"]}'

def format_http_log(entry: Dict[str, Any]) -> str:
    """Format as HTTP access log (logfmt-style), matching other/web-server-logs-simulator.py.

    Shape: `<timestamp> level=... method=... url=... status=... duration=...ms`
    Only emitted when --log-format http is selected (opt-in).
    Timestamp is omitted (not left blank) when absent; level must be provided by
    the caller so it stays synced with status under --failure-rate.
    """
    ts = entry.get("timestamp")
    level = str(entry["level"]).lower() if "level" in entry else "info"
    method = entry.get("method", "GET")
    url = entry.get("url", "/")
    status = entry.get("status", 200)
    duration = entry.get("duration_ms", 0)
    body = f"level={level} method={method} url={url} status={status} duration={duration}ms"
    # Leading timestamp (no key=) matches the reference simulator for drop-in familiarity.
    return f"{ts} {body}" if ts else body


def format_log(entry: Dict[str, Any], log_format: str) -> str:
    """Format log entry according to specified format.

    Args:
        entry: Log entry dictionary
        log_format: Target format (JSON, logfmt, http, apache, syslog, etc.)

    Returns:
        str: Formatted log line
    """
    format_lower = log_format.lower()

    if format_lower == "json":
        return format_json_log(entry)
    elif format_lower == "logfmt":
        return format_logfmt_log(entry)
    elif format_lower == "plain":
        return format_plain_log(entry)
    elif format_lower == "http":
        return format_http_log(entry)
    elif format_lower == "apache common":
        return format_apache_common_log(entry)
    elif format_lower == "apache combined":
        return format_apache_combined_log(entry)
    elif format_lower == "apache error":
        return format_apache_error_log(entry)
    elif format_lower in ["bsd syslog", "rfc3164"]:
        return format_bsd_syslog_log(entry)
    elif format_lower in ["syslog", "rfc5424"]:
        return format_rfc5424_syslog_log(entry)
    else:
        # Default to JSON
        return format_json_log(entry)

def resolve_file_path(path: str) -> str:
    """Resolve and prepare file path for logging.

    Args:
        path: Input path (can be directory or file)

    Returns:
        str: Resolved file path ready for writing
    """
    if os.path.isdir(path):
        # If it's a directory, append default filename
        return os.path.join(path, DEFAULT_FILE)
    elif os.path.dirname(path):
        # If it has a directory component, ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path
    else:
        # If it's just a filename, use current directory
        return path

class OutputHandler:
    """Manages file output: plain/gzip, append/overwrite, and split rotation.

    ponytail: replaces the old per-line open(path, "a") reopen with a single
    persistent handle — needed for gzip streaming and split rotation, and much
    faster at high line rates. Split uses a simple line/byte counter (ceiling:
    no time-based rotation; upgrade path = add a timer trigger in write()).
    """

    def __init__(self, file_path: str, overwrite: bool = False, compress: bool = False,
                 split_by: int = 0, split_unit: str = "lines") -> None:
        """Open the output target and initialize rotation counters.

        Args:
            file_path: Output file or directory path (resolved via resolve_file_path)
            overwrite: Truncate the file ("w") instead of appending ("a")
            compress: Gzip output (also enabled automatically for a .gz path)
            split_by: Rotate to a new part file every N units; 0 disables splitting
            split_unit: "lines" or "bytes" — the unit `split_by` is counted in
        """
        self.base_path = resolve_file_path(file_path)
        self.mode_char = "w" if overwrite else "a"
        # .gz extension implies compression too (flog-style convenience).
        self.compress = compress or self.base_path.endswith(".gz")
        self.split_by = split_by  # 0 = no splitting
        self.split_unit = split_unit  # "lines" or "bytes"
        self.part = 0
        self.lines_in_part = 0
        self.bytes_in_part = 0
        self.fh = None
        self._open()

    def _current_path(self) -> str:
        """Path for the current split part (part 0 uses the base name)."""
        if self.split_by <= 0 or self.part == 0:
            return self.base_path
        # Insert part index before the extension: name.log -> name1.log
        root, ext = os.path.splitext(self.base_path)
        # Keep .gz paired with its real extension (e.g. name.log.gz)
        if ext == ".gz":
            root, inner = os.path.splitext(root)
            return f"{root}{self.part}{inner}{ext}"
        return f"{root}{self.part}{ext}"

    def _open(self) -> None:
        path = self._current_path()
        if self.compress:
            self.fh = gzip.open(path, self.mode_char + "t", encoding="utf-8")
        else:
            self.fh = open(path, self.mode_char, encoding="utf-8")
        self.lines_in_part = 0
        self.bytes_in_part = 0

    def _should_rotate(self) -> bool:
        if self.split_by <= 0:
            return False
        if self.split_unit == "bytes":
            return self.bytes_in_part >= self.split_by
        return self.lines_in_part >= self.split_by

    def write(self, line: str) -> None:
        """Write a single line (newline appended), rotating first if the split
        threshold for the current part has been reached.

        Args:
            line: Log line to write (without trailing newline)
        """
        if self._should_rotate():
            self.close()
            self.part += 1
            self._open()
        # Mirror stdout: do not append an extra NL when the payload already ends
        # with one (multiline --style stacks).
        payload = line if line.endswith("\n") else line + "\n"
        self.fh.write(payload)
        self.lines_in_part += 1
        # ponytail: byte-based split counts uncompressed UTF-8 payload, not the
        # on-disk compressed size (unknown until flush). For .gz output the
        # physical part files will be smaller than the --split-by threshold.
        self.bytes_in_part += len(payload.encode("utf-8"))

    def close(self) -> None:
        """Close the current file handle if open (safe to call more than once)."""
        if self.fh:
            self.fh.close()
            self.fh = None

def parse_duration(value: str, flag: str = "--time-step") -> float:
    """Parse a duration string into seconds (flog-style).

    Accepts a plain number (seconds) or a suffixed value: ms, s, m, h.
    ponytail: supported units are ms/s/m/h; a bare number means seconds.

    Args:
        value: Duration string, e.g. '10', '20ms', '5s', '1m'
        flag: CLI flag name used in the error message (e.g. --error-interval)

    Returns:
        float: Duration in seconds

    Raises:
        SystemExit: If the value cannot be parsed
    """
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*(ms|s|m|h)?\s*", value)
    if not m:
        print(f"Error: invalid {flag} duration '{value}' (use e.g. 10, 20ms, 5s, 1m)")
        raise SystemExit(1)
    num = float(m.group(1))
    unit = m.group(2) or "s"
    factor = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
    return num * factor

def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments
    """
    # Clean one-line description at the top; banner moved to the epilog (bottom)
    # so help opens with usage -> grouped options, and closes with banner + examples.
    description = "fuzzy-train: A versatile fake log generator for testing and development - runs anywhere."

    epilog = f"""{get_banner()}

Examples:
  Basics (short forms: -f -o -n -b -w -p -s):
    python3 fuzzy-train.py                                             # Default JSON logs to stdout
    python3 fuzzy-train.py --lines-per-second 5 --time-zone UTC        # Higher rate, UTC timestamps
    python3 fuzzy-train.py -f logfmt -n 100                            # Short: logfmt, 100 lines then exit

  Formats:
    python3 fuzzy-train.py --log-format 'apache common' --output file  # Apache logs to a file
    python3 fuzzy-train.py --log-format syslog --trace-id-type integer # Syslog with integer trace IDs
    python3 fuzzy-train.py --log-format http --failure-rate 0.05       # HTTP access logs (simulator-style)

  HTTP / failure simulation (opt-in; defaults unchanged without these flags):
    python3 fuzzy-train.py --failure-rate 0.1 -n 100 --lines-per-second 1000
    python3 fuzzy-train.py -f http --get-post-ratio 0.9 --get-duration-ms 500 --post-duration-ms 2000
    python3 fuzzy-train.py --arrival exponential --lines-per-second 2

  Language styles / multiline stacks (Fluent Bit & Vector multiline testing):
    python3 fuzzy-train.py --style java -f plain --error-every 1000
    python3 fuzzy-train.py --style python -f plain --error-interval 5m --lines-per-second 2
    python3 fuzzy-train.py --style java -f plain --failure-rate 0.05 -n 50

  Field control:
    python3 fuzzy-train.py --min-log-length 200 --max-log-length 300   # Custom message lengths
    python3 fuzzy-train.py --no-timestamp --no-trace-id                # Minimal logs (message only)

  Output control (bounded runs use a high rate so they finish fast):
    python3 fuzzy-train.py --count 1000 --lines-per-second 1000 --output file            # 1000 lines then exit
    python3 fuzzy-train.py --max-bytes 1048576 --lines-per-second 1000 --output file     # ~1MB then exit
    python3 fuzzy-train.py --file logs.gz --count 500 --lines-per-second 1000            # Gzip-compressed output
    python3 fuzzy-train.py --file app.log --count 1000 --split-by 200 --lines-per-second 1000  # Split into 200-line files
    python3 fuzzy-train.py --count 100 --time-step 1m --lines-per-second 1000            # Timestamps 1 min apart
"""

    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-v", "--version", action="version", version=f"fuzzy-train {__version__}")

    # Basic Options
    basic = parser.add_argument_group('Basic Options')
    basic.add_argument("-f", "--log-format", type=str, default=DEFAULT_LOG_FORMAT, metavar="FORMAT",
                       help=f"Output format: JSON, logfmt, plain, http, 'apache common', 'apache combined', 'apache error', 'bsd syslog', syslog (default: {DEFAULT_LOG_FORMAT})")
    basic.add_argument("--lines-per-second", type=float, default=DEFAULT_LINES_PER_SECOND, metavar="RATE",
                       help=f"Generation rate (default: {DEFAULT_LINES_PER_SECOND})")
    basic.add_argument("--arrival", type=str, default=DEFAULT_ARRIVAL, metavar="MODE",
                       choices=["fixed", "exponential"],
                       help=f"Inter-arrival pacing: fixed (sleep 1/rate) or exponential (default: {DEFAULT_ARRIVAL})")
    basic.add_argument("-o", "--output", type=str, default=DEFAULT_OUTPUT, metavar="TYPE",
                       help=f"Output destination: stdout or file (default: {DEFAULT_OUTPUT})")
    basic.add_argument("--file", type=str, metavar="PATH",
                       help="File path for log output (when output=file)")

    # Log Content
    content = parser.add_argument_group('Log Content')
    content.add_argument("--min-log-length", type=int, default=DEFAULT_MIN_LOG_LENGTH, metavar="LENGTH",
                         help=f"Minimum message length in characters (default: {DEFAULT_MIN_LOG_LENGTH})")
    content.add_argument("--max-log-length", type=int, default=DEFAULT_MAX_LOG_LENGTH, metavar="LENGTH",
                         help=f"Maximum message length in characters (default: {DEFAULT_MAX_LOG_LENGTH})")
    content.add_argument("--time-zone", type=str, default=DEFAULT_TIME_ZONE, metavar="ZONE",
                         choices=["local", "UTC", "utc", "LOCAL"],
                         help=f"Timestamp timezone: local or UTC (default: {DEFAULT_TIME_ZONE})")
    content.add_argument("--failure-rate", type=float, default=DEFAULT_FAILURE_RATE, metavar="RATE",
                         help="Probability of ERROR / HTTP 500 (0.0-1.0). Default: unset = legacy random mix")
    content.add_argument("--get-post-ratio", type=float, default=DEFAULT_GET_POST_RATIO, metavar="RATIO",
                         help="P(GET) vs POST for http/apache (0.0-1.0). http format defaults to 0.9 when unset")
    content.add_argument("--get-duration-ms", type=float, default=DEFAULT_GET_DURATION_MS, metavar="MS",
                         help=f"Mean GET duration in ms for http format (default: {DEFAULT_GET_DURATION_MS})")
    content.add_argument("--post-duration-ms", type=float, default=DEFAULT_POST_DURATION_MS, metavar="MS",
                         help=f"Mean POST duration in ms for http format (default: {DEFAULT_POST_DURATION_MS})")
    content.add_argument("--style", type=str, default=DEFAULT_STYLE, metavar="NAME",
                         help="Language style from styles/<NAME>.yaml (java, python, go, rust, csharp, ruby, javascript; aliases: node, c#). Defaults -f plain")
    content.add_argument("--error-every", type=int, default=DEFAULT_ERROR_EVERY, metavar="N",
                         help="With --style: emit a full multiline error every N events (0 = off)")
    content.add_argument("--error-interval", type=str, default=DEFAULT_ERROR_INTERVAL, metavar="DURATION",
                         help="With --style: emit a full multiline error every DURATION (e.g. 5m, 30s)")

    # Field Control
    fields = parser.add_argument_group('Field Control (use --no-* to exclude fields)')
    fields.add_argument("--no-trace-id", action="store_true",
                        help="Exclude trace_id field")
    fields.add_argument("--trace-id-type", type=str, default=DEFAULT_TRACE_ID_TYPE, metavar="TYPE",
                        choices=["pid", "integer"],
                        help=f"Trace ID type: pid (PID/Container) or integer (incremental) (default: {DEFAULT_TRACE_ID_TYPE})")
    fields.add_argument("--no-timestamp", action="store_true",
                        help="Exclude timestamp field from JSON/logfmt (plain --style still embeds {timestamp} from the YAML template)")
    fields.add_argument("--no-log-level", action="store_true",
                        help="Exclude level field from JSON/logfmt (plain --style still embeds level text from the YAML template)")
    fields.add_argument("--no-length", action="store_true",
                        help="Exclude message length field")

    # Output Control (flog-inspired; all opt-in, streaming stays the default)
    outctl = parser.add_argument_group('Output Control')
    outctl.add_argument("-n", "--count", type=int, default=DEFAULT_COUNT, metavar="N",
                        help="Generate exactly N events then exit (default: 0 = infinite). With --style, one event may be a multiline stack (not N physical lines)")
    outctl.add_argument("-b", "--max-bytes", type=int, default=DEFAULT_MAX_BYTES, metavar="N",
                        help="Generate until >= N bytes then exit (ignored when --count is set)")
    outctl.add_argument("-w", "--overwrite", action="store_true",
                        help="Truncate the output file before writing instead of appending")
    outctl.add_argument("--compress", action="store_true",
                        help="Gzip file output (also auto-enabled when --file ends with .gz)")
    outctl.add_argument("-p", "--split-by", type=int, default=DEFAULT_SPLIT_BY, metavar="N",
                        help="Rotate output file every N lines (or N bytes when --max-bytes is used)")
    outctl.add_argument("-s", "--time-step", type=str, default=DEFAULT_TIME_STEP, metavar="DURATION",
                        help="Advance each log's timestamp by DURATION without real waiting (e.g. 10, 20ms, 5s, 1m)")
    return parser.parse_args()

def get_arg_value(args: argparse.Namespace, name: str) -> Any:
    """Get argument value handling both underscore and hyphen variants.

    Args:
        args: Parsed arguments namespace
        name: Argument name (with hyphens)

    Returns:
        Any: Argument value
    """
    underscore_name = name.replace('-', '_')
    # Use hasattr rather than `or` so explicit falsy values (0, False, "")
    # are not masked by the fallback.
    if hasattr(args, underscore_name):
        return getattr(args, underscore_name)
    return getattr(args, name, None)

def validate_length_params(min_len: int, max_len: int) -> tuple[int, int]:
    """Validate and adjust min/max length parameters.

    Args:
        min_len: Minimum log length
        max_len: Maximum log length

    Returns:
        tuple[int, int]: Validated (min_len, max_len)

    Raises:
        SystemExit: If validation fails
    """
    # If only one length is provided and it's different from defaults, use it for both
    if min_len != DEFAULT_MIN_LOG_LENGTH and max_len == DEFAULT_MAX_LOG_LENGTH:
        max_len = min_len
    elif min_len == DEFAULT_MIN_LOG_LENGTH and max_len != DEFAULT_MAX_LOG_LENGTH:
        min_len = max_len

    # Validate min/max length after adjustment
    if min_len > max_len:
        print(f"Error: min-log-length ({min_len}) cannot be greater than max-log-length ({max_len})")
        print("Please provide valid length parameters where min-log-length <= max-log-length")
        raise SystemExit(1)

    return min_len, max_len

def build_log_entry(timestamp: str, log_level: str, message: str, trace_id: Optional[str],
                   include_timestamp: bool, include_log_level: bool, include_length: bool) -> Dict[str, Any]:
    """Build log entry dictionary with optimal field ordering.

    Args:
        timestamp: Log timestamp
        log_level: Log level (INFO, ERROR, etc.)
        message: Log message
        trace_id: Optional trace ID
        include_timestamp: Whether to include timestamp
        include_log_level: Whether to include log level
        include_length: Whether to include message length

    Returns:
        Dict[str, Any]: Log entry dictionary
    """
    # ponytail: JSON/logfmt schema deliberately unchanged — faker variety flows
    # through the `message` body (see generate_random_message) so key names and
    # order stay stable for existing parsers/dashboards. Ceiling: dedicated
    # structured faker fields would need new --fields flags + doc updates.
    log_entry = {}

    if include_timestamp:
        log_entry["timestamp"] = timestamp
    if include_log_level:
        log_entry["level"] = log_level
    log_entry["message"] = message
    if trace_id:
        log_entry["trace_id"] = trace_id
    if include_length:
        log_entry["length"] = len(message)

    return log_entry

def main() -> None:
    """Main function to run the log generator."""
    args = parse_args()

    # Extract and validate parameters
    min_len = get_arg_value(args, 'min-log-length')
    max_len = get_arg_value(args, 'max-log-length')
    min_len, max_len = validate_length_params(min_len, max_len)

    lps = get_arg_value(args, 'lines-per-second')
    include_trace_id = not (get_arg_value(args, 'no-trace-id') or False)
    trace_id_type = get_arg_value(args, 'trace-id-type').lower()
    include_timestamp = not (get_arg_value(args, 'no-timestamp') or False)
    include_log_level = not (get_arg_value(args, 'no-log-level') or False)
    include_length = not (get_arg_value(args, 'no-length') or False)
    tz = get_arg_value(args, 'time-zone')
    log_format = args.log_format
    output = args.output.lower()
    file_path = args.file
    failure_rate = get_arg_value(args, 'failure-rate')
    get_post_ratio = get_arg_value(args, 'get-post-ratio')
    get_duration_ms = get_arg_value(args, 'get-duration-ms')
    post_duration_ms = get_arg_value(args, 'post-duration-ms')
    arrival = (get_arg_value(args, 'arrival') or DEFAULT_ARRIVAL).lower()
    style_name = get_arg_value(args, 'style')
    error_every = get_arg_value(args, 'error-every') or 0
    error_interval_raw = get_arg_value(args, 'error-interval')

    # Output-control parameters (argparse supplies defaults, so values are never None)
    count = get_arg_value(args, 'count')
    max_bytes = get_arg_value(args, 'max-bytes')
    overwrite = bool(get_arg_value(args, 'overwrite'))
    compress = bool(get_arg_value(args, 'compress'))
    split_by = get_arg_value(args, 'split-by')
    time_step_raw = get_arg_value(args, 'time-step')

    # Validate non-negative integers
    for name, val in (("count", count), ("max-bytes", max_bytes), ("split-by", split_by)):
        if val < 0:
            print(f"Error: --{name} cannot be negative")
            raise SystemExit(1)

    # Rate must be positive (used as 1.0/lps for pacing)
    if lps <= 0:
        print("Error: --lines-per-second must be greater than 0")
        raise SystemExit(1)

    if failure_rate is not None and not (0.0 <= failure_rate <= 1.0):
        print("Error: --failure-rate must be between 0.0 and 1.0")
        raise SystemExit(1)
    if get_post_ratio is not None and not (0.0 <= get_post_ratio <= 1.0):
        print("Error: --get-post-ratio must be between 0.0 and 1.0")
        raise SystemExit(1)
    if get_duration_ms <= 0 or post_duration_ms <= 0:
        print("Error: --get-duration-ms and --post-duration-ms must be greater than 0")
        raise SystemExit(1)
    if error_every < 0:
        print("Error: --error-every cannot be negative")
        raise SystemExit(1)

    style = None
    if style_name:
        style = load_style(str(style_name))
        fmt_l = log_format.lower()
        if fmt_l in ("http", "apache common", "apache combined"):
            print("Error: --style is incompatible with --log-format "
                  f"'{log_format}' (access formats ignore the message field). "
                  "Use plain, json, or logfmt.",
                  file=sys.stderr)
            raise SystemExit(1)
        # Multiline stacks need plain emit; auto-select when user left the JSON default.
        if log_format == DEFAULT_LOG_FORMAT:
            log_format = "plain"
            print("Note: --style defaults to --log-format plain for multiline stacks "
                  "(override with -f json if you want stacks inside a JSON message field)",
                  file=sys.stderr)
        if not style.get("errors") and (error_every > 0 or error_interval_raw or failure_rate):
            print(f"Error: style '{style_name}' has no errors[] fixtures", file=sys.stderr)
            raise SystemExit(1)

    error_interval = parse_duration(error_interval_raw, "--error-interval") if error_interval_raw else None

    # --count takes precedence over --max-bytes (flog parity)
    if count > 0:
        max_bytes = 0

    # Parse fake-time step (seconds); None = real wall-clock
    time_step = parse_duration(time_step_raw, "--time-step") if time_step_raw is not None else None

    # split-by unit follows the active bound: bytes when byte-bounded, else lines
    split_unit = "bytes" if (max_bytes > 0 and count == 0) else "lines"

    # gzip/overwrite/split are file-only; auto-enable file output if requested
    # (these can't apply to stdout, so file output is implied).
    file_features = compress or overwrite or split_by > 0
    if file_features and output != "file" and not file_path:
        output = "file"
        print(f"Note: --compress/--overwrite/--split-by imply file output; writing to {DEFAULT_FILE}",
              file=sys.stderr)

    # Output logic
    to_stdout = (output == "stdout") or (output == "" and not file_path)
    to_file = (output == "file") or (file_path is not None)
    if to_file and not file_path:
        file_path = DEFAULT_FILE

    handler = None
    if to_file:
        handler = OutputHandler(file_path, overwrite=overwrite, compress=compress,
                                split_by=split_by, split_unit=split_unit)

    # Synthetic clock base for --time-step
    synthetic_time = datetime.now(timezone.utc) if time_step is not None else None

    format_lower = log_format.lower()
    is_http = format_lower == "http"
    is_apache_access = format_lower in ("apache common", "apache combined")
    # http format mirrors the simulator: unset --failure-rate means 0% failures
    # (always 200), not the legacy apache multi-status mix.
    effective_failure_rate = 0.0 if (is_http and failure_rate is None) else failure_rate

    lines_written = 0
    bytes_written = 0
    last_style_error_at = None  # for --error-interval with --style
    try:
        while True:
            # Stop conditions (bounded batch mode); count beats bytes
            if count > 0 and lines_written >= count:
                break
            if max_bytes > 0 and bytes_written >= max_bytes:
                break

            timestamp = generate_timestamp(tz, base=synthetic_time)
            clock_now = resolve_style_clock(synthetic_time, tz)

            if style is not None:
                is_err, last_style_error_at = should_emit_style_error(
                    lines_written, failure_rate, error_every, error_interval,
                    last_style_error_at, clock_now,
                )
                if is_err:
                    message = choose_style_error(style, clock_now)
                    log_level = "ERROR"
                else:
                    message = choose_style_info(style, clock_now)
                    log_level = "INFO"
                trace_id = generate_trace_id(include_trace_id, trace_id_type)
                log_entry = build_log_entry(
                    timestamp, log_level, message, trace_id,
                    include_timestamp, include_log_level, include_length
                )
            else:
                # One roll drives level + status when a failure rate applies.
                failed = None if effective_failure_rate is None else (
                    random.random() < effective_failure_rate
                )
                log_level = choose_log_level(effective_failure_rate, failed)
                trace_id = generate_trace_id(include_trace_id, trace_id_type)
                message_length = random.randint(min_len, max_len)
                message = generate_random_message(message_length)
                log_entry = build_log_entry(
                    timestamp, log_level, message, trace_id,
                    include_timestamp, include_log_level, include_length
                )

                # Opt-in HTTP fields: only for --log-format http, or when apache
                # knobs are explicitly set (legacy apache random mix otherwise).
                if is_http:
                    # Access-line shape always needs timestamp + level so status/level
                    # stay synced; --no-timestamp / --no-log-level only trim JSON/logfmt.
                    log_entry["timestamp"] = timestamp
                    log_entry["level"] = log_level
                    method = choose_http_method(get_post_ratio)
                    log_entry["method"] = method
                    log_entry["url"] = choose_http_url()
                    log_entry["status"] = choose_http_status(effective_failure_rate, failed)
                    log_entry["duration_ms"] = choose_duration_ms(
                        method, get_duration_ms, post_duration_ms
                    )
                elif is_apache_access:
                    # Apache lines have no level field; --failure-rate only drives status.
                    if failure_rate is not None:
                        log_entry["status"] = choose_http_status(failure_rate, failed)
                    if get_post_ratio is not None:
                        log_entry["method"] = choose_http_method(get_post_ratio)

            line = format_log(log_entry, log_format)
            if to_stdout:
                if line.endswith("\n"):
                    print(line, end="", flush=True)
                else:
                    print(line, flush=True)  # flush for real-time tailing in pipes/containers
            if handler:
                handler.write(line)

            lines_written += 1
            payload_for_bytes = line if line.endswith("\n") else line + "\n"
            bytes_written += len(payload_for_bytes.encode("utf-8"))
            if synthetic_time is not None:
                synthetic_time += timedelta(seconds=time_step)

            # ponytail: fixed mode skips sub-millisecond sleeps — OS timer granularity
            # (~1ms) would throttle throughput at high rates (e.g. 2000+ lines/sec).
            # Exponential always sleeps the drawn gap so mean rate stays ~lps
            # (matches the web-server simulator). Ceiling: best-effort pacing.
            if arrival == "exponential":
                # Mean inter-arrival = 1/lps (same mean as fixed mode).
                time.sleep(random.expovariate(lps))
            else:
                interval = 1.0 / lps
                if interval >= 0.001:
                    time.sleep(interval)
    except KeyboardInterrupt:
        print("\nLog generation stopped.")
    finally:
        if handler:
            handler.close()

if __name__ == "__main__":
    main()
