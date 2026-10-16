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
unchanged): --failure-rate, --error-interval, --get-post-ratio,
--get-duration-ms, --post-duration-ms, --arrival exponential, and
--log-format http.
"""

import argparse
from datetime import datetime, timedelta, timezone
import gzip
import itertools
import json
import math
import os
import random
import re
import socket
import string
import sys
import time
from typing import Any, Dict, Optional, Tuple, Union

# Reconfigure standard streams on Windows to UTF-8 if available to prevent
# UnicodeEncodeError on console output with default non-UTF-8 code pages (e.g. cp1252).
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

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
    "Encryption key rotation completed.",
]

# Constants
__version__ = "3.0.0"
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

ASCII_BANNER = """+-- FUZZY TRAIN -----------------------------------------------------+
|                                                                   |
|   LOG GENERATION & TESTING FRAMEWORK                              |
|   Version {version} | Multi-format Support | Container Ready        |
|                                                                   |
+-------------------------------------------------------------------+"""


def get_banner() -> str:
    """Return formatted banner with version number.

    Falls back to an ASCII banner if stdout's encoding or the system's preferred
    encoding cannot represent the Unicode box-drawing characters.

    Returns:
        str: Formatted banner with version number
    """
    version_padded = f"{__version__:<7}"  # Pad to 7 chars for alignment
    banner_str = BANNER.format(version=version_padded)
    preferred = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        import locale

        system_enc = locale.getpreferredencoding(False) or preferred
    except Exception:
        system_enc = preferred

    for enc in (preferred, system_enc):
        try:
            banner_str.encode(enc)
        except (UnicodeEncodeError, LookupError):
            return ASCII_BANNER.format(version=version_padded)

    return banner_str


# Default configuration constants
DEFAULT_MIN_LOG_LENGTH = 90
DEFAULT_MAX_LOG_LENGTH = 100
DEFAULT_LINES_PER_SECOND = 1
DEFAULT_TRACE_ID_TYPE = "pid"
DEFAULT_TIME_ZONE = "local"
DEFAULT_LOG_FORMAT = "json"
DEFAULT_OUTPUT = "stdout"
DEFAULT_FILE = "fuzzy-train.log"

# Output-control defaults (flog-inspired). 0/None = feature off, preserving
# the infinite real-time streaming default.
DEFAULT_COUNT = 0  # 0 = infinite streaming (today's default)
DEFAULT_MAX_BYTES = 0  # 0 = no byte cap
DEFAULT_SPLIT_BY = 0  # 0 = no file splitting
DEFAULT_TIME_STEP = None  # None = real wall-clock timestamps
DEFAULT_DURATION = None  # None = no time bound
DEFAULT_SEED = None  # None = non-deterministic randomness

VALID_FORMATS = [
    "json",
    "logfmt",
    "http",
    "apache-common",
    "apache_common",
    "apache-combined",
    "apache_combined",
    "apache-error",
    "apache_error",
    "bsd-syslog",
    "bsd_syslog",
    "rfc3164",
    "syslog",
    "rfc5424",
]

CANONICAL_STACKS = (
    "java",
    "python",
    "go",
    "nodejs",
    "dotnet",
    "ruby",
    "rust",
    "php",
)
STACK_ALIASES = {
    "py": "python",
    "golang": "go",
    "node": "nodejs",
    "javascript": "nodejs",
    "js": "nodejs",
    "csharp": "dotnet",
    "cs": "dotnet",
    "rb": "ruby",
    "rs": "rust",
}
VALID_STACKS = list(CANONICAL_STACKS) + list(STACK_ALIASES.keys())
DEFAULT_STACK = None

# HTTP / failure-rate defaults (all opt-in). None = legacy random mix unchanged.
DEFAULT_FAILURE_RATE = None
DEFAULT_ERROR_INTERVAL = None  # None = off (e.g. '5s', '30s', '1m')
DEFAULT_GET_POST_RATIO = None  # None: unused except http format (uses 0.9)
DEFAULT_HTTP_GET_POST_RATIO = 0.9
DEFAULT_GET_DURATION_MS = 500
DEFAULT_POST_DURATION_MS = 2000
DEFAULT_ARRIVAL = "fixed"  # fixed | exponential


def get_process_id() -> str:
    """Get process identifier based on environment (PID for local, container ID for containers).

    Returns:
        str: Process identifier string
    """
    # Check if running in any container
    if (
        os.path.exists("/.dockerenv")
        or os.path.exists("/proc/1/cgroup")
        or os.environ.get("container")
        or os.path.exists("/run/.containerenv")
    ):  # Podman

        hostname = socket.gethostname()

        # For Kubernetes pods, extract the hash suffix
        if "-" in hostname:
            parts = hostname.split("-")
            if len(parts) >= 2:
                # Use last part (pod hash) + second-to-last if available
                return (
                    f"{parts[-2]}-{parts[-1]}"[:12]
                    if len(parts) > 2
                    else parts[-1][:12]
                )

        # Fallback to truncated hostname for Docker/Podman
        return hostname[:12]
    else:
        return str(os.getpid())


PID = get_process_id()
ALPHANUM = string.ascii_letters + string.digits

if FAKER_AVAILABLE and fake is not None:
    _FAKER_MESSAGE_BUILDERS = (
        fake.sentence,
        lambda: f"user {fake.user_name()} from {fake.ipv4()} accessed {fake.uri_path()}",
        lambda: f"{fake.company()} processed request for {fake.email()}",
        lambda: f"{fake.http_method()} {fake.url()} completed",
        lambda: f"host {fake.hostname()} reported {fake.word()} event",
    )
else:
    _FAKER_MESSAGE_BUILDERS = ()


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
    parts = []
    total_len = 0
    while total_len < length:
        if FAKER_AVAILABLE:
            sentence = random.choice(_FAKER_MESSAGE_BUILDERS)()
        else:
            sentence = random.choice(SENTENCES)
            if random.random() < DETAIL_PROBABILITY:
                detail = "".join(random.choices(ALPHANUM, k=random.randint(10, 30)))
                sentence = f"{sentence} Details: {detail}"
        parts.append(sentence)
        total_len += len(sentence) if not total_len else (1 + len(sentence))
    return " ".join(parts)[:length]


def generate_timestamp(time_zone: str, base: Optional[datetime] = None) -> str:
    """Generate ISO 8601 timestamp in specified timezone.

    Args:
        time_zone: 'local' or 'utc'
        base: Optional synthetic UTC datetime to use instead of the wall clock
              (used by --time-step to generate time-spread logs instantly)

    Returns:
        str: ISO 8601 formatted timestamp
    """
    now = base if base is not None else datetime.now(timezone.utc)
    if time_zone.lower() == "local":
        now = now.astimezone()
    # ISO 8601 with microseconds and Z for UTC
    if time_zone.lower() == "utc":
        return now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        offset = now.strftime("%z")
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


def choose_log_level(
    failure_rate: Optional[float], failed: Optional[bool] = None
) -> str:
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


def choose_http_status(
    failure_rate: Optional[float], failed: Optional[bool] = None
) -> int:
    """Pick an HTTP status code.

    When failure_rate is None, preserves the legacy uniform mix.
    When set, 500 on failure and 200 on success (simulator-style).
    """
    if failure_rate is None:
        return random.choice(DEFAULT_HTTP_STATUSES)
    if failed is None:
        failed = random.random() < failure_rate
    return 500 if failed else 200


def should_emit_interval_error(
    error_interval: float,
    last_error_at: Optional[datetime],
    now: datetime,
) -> Tuple[bool, datetime]:
    """Decide whether to emit an error on this tick based on --error-interval.

    Starts the interval timer on the first log line (last_error_at is None) and
    emits an error each time at least `error_interval` seconds have elapsed.

    Returns:
        Tuple[bool, datetime]: (is_error, updated_last_error_at)
    """
    if last_error_at is None:
        return False, now
    if (now - last_error_at).total_seconds() >= error_interval:
        return True, now
    return False, last_error_at


def choose_http_method(
    get_post_ratio: Optional[float], default_ratio: float = DEFAULT_HTTP_GET_POST_RATIO
) -> str:
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


def parse_entry_timestamp(
    entry: Dict[str, Any], dt: Optional[datetime] = None
) -> datetime:
    """Return a datetime for log formatting, using `dt` directly when provided
    to avoid a redundant format-then-parse round-trip in the hot loop.

    Args:
        entry: Log entry dict; may contain a 'timestamp' string
        dt: Optional precomputed datetime from the caller

    Returns:
        datetime: Parsed timestamp, or current time if absent/unparseable
    """
    if dt is not None:
        return dt
    ts = entry.get("timestamp")
    if not ts:
        return datetime.now()
    try:
        # Normalize a trailing 'Z' (UTC) which older fromisoformat rejects.
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return datetime.now()


def format_json_log(entry: Dict[str, Any], dt: Optional[datetime] = None) -> str:
    """Format log entry as JSON."""
    return json.dumps(entry)


def format_logfmt_log(entry: Dict[str, Any], dt: Optional[datetime] = None) -> str:
    """Format log entry as logfmt."""
    def _escape_val(v: Any) -> str:
        s = (
            str(v)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
        return s

    return " ".join(f'{k}="{_escape_val(v)}"' for k, v in entry.items())


def format_apache_common_log(
    entry: Dict[str, Any], dt: Optional[datetime] = None
) -> str:
    """Format log entry as Apache Common Log Format."""
    host = fake.ipv4() if FAKER_AVAILABLE else "127.0.0.1"
    ident = "-"
    user = "-"
    dt_obj = parse_entry_timestamp(entry, dt)
    tz_offset = dt_obj.strftime("%z")
    tz_str = tz_offset if tz_offset else "+0000"
    tstr = dt_obj.strftime(f"[%d/%b/%Y:%H:%M:%S {tz_str}]")
    method = entry.get("method")
    if method is None:
        method = fake.http_method() if FAKER_AVAILABLE else "GET"
    path = entry.get("url") or (
        ("/" + fake.uri_path()) if FAKER_AVAILABLE else "/index.html"
    )
    request = f"{method} {path} HTTP/1.1"
    status = entry.get("status")
    if status is None:
        status = random.choice(DEFAULT_HTTP_STATUSES)
    size = len(entry.get("message", ""))
    return f'{host} {ident} {user} {tstr} "{request}" {status} {size}'


def format_apache_combined_log(
    entry: Dict[str, Any], dt: Optional[datetime] = None
) -> str:
    """Format log entry as Apache Combined Log Format."""
    host = fake.ipv4() if FAKER_AVAILABLE else "127.0.0.1"
    ident = "-"
    user = "-"
    dt_obj = parse_entry_timestamp(entry, dt)
    tz_offset = dt_obj.strftime("%z")
    tz_str = tz_offset if tz_offset else "+0000"
    tstr = dt_obj.strftime(f"[%d/%b/%Y:%H:%M:%S {tz_str}]")
    method = entry.get("method")
    if method is None:
        method = fake.http_method() if FAKER_AVAILABLE else "GET"
    path = entry.get("url") or (
        ("/" + fake.uri_path()) if FAKER_AVAILABLE else "/index.html"
    )
    request = f"{method} {path} HTTP/1.1"
    status = entry.get("status")
    if status is None:
        status = random.choice(DEFAULT_HTTP_STATUSES)
    size = len(entry.get("message", ""))
    referer = fake.url() if FAKER_AVAILABLE else "https://example.com/"
    ua = (
        fake.user_agent()
        if FAKER_AVAILABLE
        else "Mozilla/5.0 (compatible; FakeBot/1.0)"
    )
    return (
        f'{host} {ident} {user} {tstr} "{request}" {status} {size} "{referer}" "{ua}"'
    )


def format_apache_error_log(
    entry: Dict[str, Any], dt: Optional[datetime] = None
) -> str:
    """Format log entry as Apache Error Log Format."""
    dt_obj = parse_entry_timestamp(entry, dt)
    tstr = dt_obj.strftime("%a %b %d %H:%M:%S.%f %Y")
    pid = random.randint(1000, 99999)
    client_ip = fake.ipv4() if FAKER_AVAILABLE else "127.0.0.1"
    client = f"{client_ip}:{random.randint(1000, 65535)}"
    level = entry.get("level", "info").lower()
    return f'[{tstr}] [core:{level}] [pid {pid}] [client {client}] {entry["message"]}'


# Syslog severity codes (RFC 3164 / RFC 5424): 3=err, 4=warning, 6=info, 7=debug
SYSLOG_SEVERITY_MAP = {
    "ERROR": 3,
    "WARN": 4,
    "INFO": 6,
    "DEBUG": 7,
}
SYSLOG_FACILITIES = (1, 3, 16, 17, 18, 19, 20, 21, 22, 23)


def compute_syslog_pri(entry: Dict[str, Any]) -> str:
    """Compute RFC 3164 / RFC 5424 <PRI> from facility (0-23) and entry log level.

    Severity follows entry['level'] when present (so --failure-rate and
    --error-interval produce severity 3 / err); facility varies across standard
    syslog facilities (1=user, 3=daemon, 16-23=local0-local7) when Faker is
    available, or defaults to facility 1 (user) in zero-dependency fallback mode.
    """
    level = str(entry.get("level", "INFO")).upper()
    severity = SYSLOG_SEVERITY_MAP.get(level, 5)
    facility = random.choice(SYSLOG_FACILITIES) if FAKER_AVAILABLE else 1
    return f"<{facility * 8 + severity}>"


def format_bsd_syslog_log(entry: Dict[str, Any], dt: Optional[datetime] = None) -> str:
    """Format log entry as BSD Syslog (RFC3164)."""
    dt_obj = parse_entry_timestamp(entry, dt)
    tstr = dt_obj.strftime("%b %d %H:%M:%S")
    host = fake.hostname() if FAKER_AVAILABLE else "localhost"
    tag = fake.user_name() if FAKER_AVAILABLE else "fuzzy-train"
    pid = random.randint(100, 9999)
    pri = compute_syslog_pri(entry)
    if FAKER_AVAILABLE:
        return f'{pri}{tstr} {host} {tag}[{pid}]: {entry["message"]}'
    return f'{pri}{tstr} {host} {tag}: {entry["message"]}'


def format_rfc5424_syslog_log(
    entry: Dict[str, Any], dt: Optional[datetime] = None
) -> str:
    """Format log entry as RFC5424 Syslog."""
    dt_obj = parse_entry_timestamp(entry, dt)
    tz_offset = dt_obj.strftime("%z")
    if tz_offset:
        tz_formatted = f"{tz_offset[:3]}:{tz_offset[3:]}"
    else:
        tz_formatted = "Z"
    tstr = dt_obj.strftime(f"%Y-%m-%dT%H:%M:%S.%f{tz_formatted}")
    host = fake.hostname() if FAKER_AVAILABLE else "localhost"
    app = fake.user_name() if FAKER_AVAILABLE else "fuzzy-train"
    proc_id = str(random.randint(100, 9999))
    msg_id = f"ID{random.randint(1, 999)}"
    pri = compute_syslog_pri(entry)
    return f'{pri}1 {tstr} {host} {app} {proc_id} {msg_id} - {entry["message"]}'


def format_http_log(entry: Dict[str, Any], dt: Optional[datetime] = None) -> str:
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
    body = (
        f"level={level} method={method} url={url} status={status} duration={duration}ms"
    )
    # Leading timestamp (no key=) matches the reference simulator for drop-in familiarity.
    return f"{ts} {body}" if ts else body


def normalize_log_format(log_format: str) -> str:
    """Normalize log format name to its canonical hyphenated slug."""
    fmt = log_format.strip().lower().replace("_", "-")
    if fmt == "rfc3164":
        return "bsd-syslog"
    if fmt == "rfc5424":
        return "syslog"
    return fmt


def normalize_stack(stack: Optional[str]) -> Optional[str]:
    """Normalize language stack name (e.g. 'py' -> 'python', 'js' -> 'nodejs')."""
    if not stack:
        return None
    s = stack.strip().lower()
    return STACK_ALIASES.get(s, s)


_DOTNET_LEVEL_MAP = {
    "INFO": "INF",
    "DEBUG": "DBG",
    "WARN": "WRN",
    "ERROR": "ERR",
}


def _stack_context(entry: Dict[str, Any]) -> Tuple[str, int, str, int, int, int]:
    """Generate lightweight per-event runtime context values for stack logs."""
    req_id = entry.get("trace_id") or f"req-{random.randint(0x1000, 0xFFFF):04x}"
    user_id = random.randint(1000, 9999)
    order_id = f"ord-{random.randint(1000, 9999)}"
    latency_ms = random.randint(2, 185)
    pid = random.randint(1000, 9999)
    thread_num = random.randint(1, 16)
    return req_id, user_id, order_id, latency_ms, pid, thread_num


def generate_stack_event(
    stack: str,
    level: str,
    dt: datetime,
    include_timestamp: bool = True,
    tz: str = "local",
    entry: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, Optional[str]]:
    """Build a realistic language-specific log line and optional multi-line stacktrace.

    Returns:
        Tuple[str, str, Optional[str]]:
            (formatted_full_log, single_line_summary_message, stacktrace_or_none)
    """
    lang = normalize_stack(stack) or "java"
    lvl = level.upper()
    is_err = lvl == "ERROR"
    req_id, user_id, order_id, latency_ms, pid, thread_num = _stack_context(entry or {})
    ms = dt.microsecond // 1000
    tz_suffix = "Z" if tz.lower() == "utc" else (dt.strftime("%z") or "Z")
    if len(tz_suffix) == 5 and tz_suffix[0] in "+-":
        tz_iso = f"{tz_suffix[:3]}:{tz_suffix[3:]}"
    else:
        tz_iso = tz_suffix

    if lang == "java":
        ts = (
            f"{dt.strftime('%Y-%m-%d %H:%M:%S')}.{ms:03d} " if include_timestamp else ""
        )
        thread = f"http-nio-8080-exec-{thread_num}"
        if not is_err:
            choices = (
                (
                    "com.example.order.OrderController",
                    f"Processed order orderId={order_id} userId={user_id} status=COMPLETED durationMs={latency_ms} traceId={req_id}",
                ),
                (
                    "com.example.auth.JwtTokenFilter",
                    f"Authenticated principal userId={user_id} scope=read:orders,write:orders latencyMs={latency_ms}",
                ),
                (
                    "com.example.cache.RedisCacheManager",
                    f"Cache lookup hit key=session:{user_id} ttlSec=1800 traceId={req_id}",
                ),
                (
                    "com.example.payment.PaymentClient",
                    f"Authorized payment orderId={order_id} amount=149.99 currency=USD latencyMs={latency_ms}",
                ),
            )
            logger, msg = random.choice(choices)
            return f"{ts}{lvl:<5} [{thread}] {logger} - {msg}", msg, None

        err_choices = (
            (
                "com.example.order.OrderController",
                f"Unhandled exception processing order orderId={order_id} userId={user_id} traceId={req_id}",
                f'java.lang.NullPointerException: Cannot invoke "com.example.order.Order.getItems()" because "order" is null\n'
                f"\tat com.example.order.OrderService.calculateTotal(OrderService.java:142)\n"
                f"\tat com.example.order.OrderController.placeOrder(OrderController.java:87)\n"
                f"\tat java.base/jdk.internal.reflect.NativeMethodAccessorImpl.invoke0(Native Method)\n"
                f"\tat java.base/jdk.internal.reflect.NativeMethodAccessorImpl.invoke(NativeMethodAccessorImpl.java:77)\n"
                f"\tat org.springframework.web.method.support.InvocableHandlerMethod.doInvoke(InvocableHandlerMethod.java:205)\n"
                f"\tat org.springframework.web.servlet.FrameworkServlet.service(FrameworkServlet.java:897)\n"
                f"\t... 38 more\n"
                f"Caused by: java.lang.IllegalStateException: Cart snapshot missing for orderId={order_id}\n"
                f"\tat com.example.cart.CartRepository.requireSnapshot(CartRepository.java:64)\n"
                f"\tat com.example.order.OrderService.calculateTotal(OrderService.java:138)\n"
                f"\t... 43 more",
            ),
            (
                "com.example.db.OrderRepository",
                f"Database query failed for orderId={order_id} traceId={req_id}",
                f"org.springframework.dao.DataAccessResourceFailureException: Unable to acquire JDBC Connection\n"
                f"\tat org.springframework.jdbc.datasource.DataSourceUtils.getConnection(DataSourceUtils.java:82)\n"
                f"\tat org.springframework.jdbc.core.JdbcTemplate.execute(JdbcTemplate.java:646)\n"
                f"\tat com.example.db.OrderRepository.findById(OrderRepository.java:93)\n"
                f"\tat com.example.order.OrderService.getOrder(OrderService.java:58)\n"
                f"Caused by: java.sql.SQLTransientConnectionException: HikariPool-1 - Connection is not available, request timed out after 30000ms.\n"
                f"\tat com.zaxxer.hikari.pool.HikariPool.createTimeoutException(HikariPool.java:696)\n"
                f"\tat com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:181)\n"
                f"\tat com.zaxxer.hikari.HikariDataSource.getConnection(HikariDataSource.java:112)\n"
                f"\t... 27 more",
            ),
            (
                "com.example.payment.PaymentClient",
                f"Upstream payment gateway timed out orderId={order_id} elapsedMs=5002",
                f"java.net.SocketTimeoutException: Read timed out\n"
                f"\tat java.base/sun.nio.ch.NioSocketImpl.timedRead(NioSocketImpl.java:288)\n"
                f"\tat java.base/sun.nio.ch.NioSocketImpl.read(NioSocketImpl.java:355)\n"
                f"\tat java.base/java.net.SocketInputStream.read(SocketInputStream.java:177)\n"
                f"\tat okhttp3.internal.http1.Http1ExchangeCodec.readResponseHeaders(Http1ExchangeCodec.java:196)\n"
                f"\tat com.example.payment.PaymentClient.charge(PaymentClient.java:119)\n"
                f"\tat com.example.order.OrderService.checkout(OrderService.java:204)",
            ),
        )
        logger, msg, trace = random.choice(err_choices)
        header = f"{ts}ERROR [{thread}] {logger} - {msg}"
        return f"{header}\n{trace}", msg, trace

    if lang == "python":
        ts = (
            f"{dt.strftime('%Y-%m-%d %H:%M:%S')},{ms:03d} " if include_timestamp else ""
        )
        if not is_err:
            choices = (
                (
                    "app.services.checkout:142",
                    f"Checkout completed user_id={user_id} order_id={order_id} duration_ms={latency_ms} request_id={req_id}",
                ),
                (
                    "app.api.middleware:58",
                    f"GET /api/v1/orders/{order_id} status=200 latency_ms={latency_ms} request_id={req_id}",
                ),
                (
                    "app.workers.tasks:91",
                    f"Celery task send_order_receipt[{req_id}] succeeded in {latency_ms}ms",
                ),
                (
                    "app.db.session:74",
                    f"Connection pool stats checked_in=14 checked_out=2 overflow=0",
                ),
            )
            loc, msg = random.choice(choices)
            return f"{ts}{lvl:<5} [{loc}] [pid:{pid}] {msg}", msg, None

        err_choices = (
            (
                "app.api.routes:88",
                f"Unhandled exception in POST /api/v1/checkout request_id={req_id}",
                f"Traceback (most recent call last):\n"
                f'  File "/usr/local/lib/python3.11/site-packages/uvicorn/protocols/http/h11_impl.py", line 408, in run_asgi\n'
                f"    result = await app(self.scope, self.receive, self.send)\n"
                f'  File "/app/src/api/routes.py", line 88, in checkout\n'
                f"    receipt = await payment_service.charge(order_id={order_id!r}, user_id={user_id})\n"
                f'  File "/app/src/services/payment.py", line 134, in charge\n'
                f'    raise ConnectionError("Payment gateway timeout after 5000ms")\n'
                f"ConnectionError: Payment gateway timeout after 5000ms",
            ),
            (
                "app.repositories.orders:63",
                f"Database operational error fetching order_id={order_id} request_id={req_id}",
                f"Traceback (most recent call last):\n"
                f'  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/engine/base.py", line 1969, in _exec_single_context\n'
                f"    self.dialect.do_execute(cursor, str_statement, effective_parameters, context)\n"
                f'  File "/app/src/repositories/orders.py", line 63, in get_by_id\n'
                f"    result = await self.session.execute(stmt)\n"
                f"sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) server closed the connection unexpectedly",
            ),
            (
                "app.services.inventory:115",
                f"Failed to reserve inventory for order_id={order_id} user_id={user_id}",
                f"Traceback (most recent call last):\n"
                f'  File "/app/src/services/inventory.py", line 115, in reserve_items\n'
                f'    sku_count = payload["items"][0]["quantity"]\n'
                f"KeyError: 'quantity'",
            ),
        )
        loc, msg, trace = random.choice(err_choices)
        header = f"{ts}ERROR [{loc}] [pid:{pid}] {msg}"
        return f"{header}\n{trace}", msg, trace

    if lang == "go":
        ts = f"{dt.strftime('%Y/%m/%d %H:%M:%S.%f')} " if include_timestamp else ""
        if not is_err:
            choices = (
                (
                    "internal/order/service.go:84",
                    f"request processed method=GET path=/api/v1/orders/{order_id} status=200 latency={latency_ms}ms req_id={req_id}",
                ),
                (
                    "internal/db/postgres.go:119",
                    f"query executed table=orders rows=1 duration={latency_ms}ms req_id={req_id}",
                ),
                (
                    "internal/worker/dispatcher.go:52",
                    f"worker={thread_num} dispatched event=order.created order_id={order_id}",
                ),
                (
                    "pkg/http/middleware.go:41",
                    f"healthz check passed goroutines=24 heap_alloc_mb=48",
                ),
            )
            caller, msg = random.choice(choices)
            return f"{ts}{lvl:<5} {caller} {msg}", msg, None

        err_choices = (
            (
                "pkg/http/recovery.go:64",
                f"panic recovered in HTTP handler req_id={req_id} order_id={order_id}",
                f"panic: runtime error: invalid memory address or nil pointer dereference\n"
                f"[signal SIGSEGV: segmentation violation code=0x1 addr=0x0 pc=0x7a4b2c]\n\n"
                f"goroutine {thread_num + 16} [running]:\n"
                f"github.com/example/order-service/internal/order.(*Service).GetOrder(0x0, {{0xc00012c040, 0x10}})\n"
                f"\t/workspace/internal/order/service.go:89 +0x14c\n"
                f"github.com/example/order-service/internal/api.(*Handler).HandleGetOrder(0xc000110240, 0xc000234000)\n"
                f"\t/workspace/internal/api/handler.go:54 +0x9b\n"
                f"net/http.HandlerFunc.ServeHTTP(0xc0001800f0?, {{0x9d4bc0?, 0xc0001a20e0?}}, 0x7f8b10?)\n"
                f"\t/usr/local/go/src/net/http/server.go:2166 +0x29",
            ),
            (
                "internal/cache/shard.go:108",
                f"fatal concurrent map access detected req_id={req_id}",
                f"fatal error: concurrent map writes\n\n"
                f"goroutine {thread_num + 32} [running]:\n"
                f"github.com/example/order-service/internal/cache.(*Shard).Set(0xc00009a000, {{0xc000214000, 0xc}}, {{0xc000310000, 0x40}})\n"
                f"\t/workspace/internal/cache/shard.go:108 +0x85\n"
                f"github.com/example/order-service/internal/order.(*Service).CacheOrder(0xc000148000, 0xc000280120)\n"
                f"\t/workspace/internal/order/service.go:152 +0x112",
            ),
            (
                "internal/payment/client.go:77",
                f'upstream RPC failed order_id={order_id} err="context deadline exceeded"',
                f"goroutine {thread_num + 8} [running]:\n"
                f"runtime/debug.Stack()\n"
                f"\t/usr/local/go/src/runtime/debug/stack.go:24 +0x5e\n"
                f"github.com/example/order-service/internal/payment.(*Client).Charge(0xc000104080, {{0x9d8120, 0xc0002a4000}}, 0xc0001f2000)\n"
                f"\t/workspace/internal/payment/client.go:77 +0x214\n"
                f"github.com/example/order-service/internal/order.(*Service).Checkout(0xc000148000, {{0x9d8120, 0xc0002a4000}}, 0xc0001f2000)\n"
                f"\t/workspace/internal/order/service.go:203 +0x18a",
            ),
        )
        caller, msg, trace = random.choice(err_choices)
        header = f"{ts}ERROR {caller} {msg}"
        return f"{header}\n{trace}", msg, trace

    if lang == "nodejs":
        ts = (
            f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{ms:03d}{tz_iso} "
            if include_timestamp
            else ""
        )
        if not is_err:
            choices = (
                (
                    "OrderController",
                    f"GET /api/v1/orders/{order_id} 200 {latency_ms}ms - reqId={req_id} userId={user_id}",
                ),
                (
                    "PrismaClient",
                    f"prisma:query SELECT id, status, total FROM orders WHERE id = '{order_id}' ({latency_ms}ms)",
                ),
                (
                    "AuthMiddleware",
                    f"Verified session token for userId={user_id} reqId={req_id}",
                ),
                (
                    "BullMQWorker",
                    f"Job invoice-render#{order_id} completed in {latency_ms}ms",
                ),
            )
            comp, msg = random.choice(choices)
            return f"{ts}{lvl:<5} [pid:{pid}] [{comp}] {msg}", msg, None

        err_choices = (
            (
                "OrderController",
                f"Unhandled error in request reqId={req_id} orderId={order_id}",
                f"TypeError: Cannot read properties of undefined (reading 'billingAddress')\n"
                f"    at OrderService.validateAddress (/app/src/services/order.service.ts:64:23)\n"
                f"    at OrderService.createOrder (/app/src/services/order.service.ts:41:18)\n"
                f"    at OrderController.postOrder (/app/src/controllers/order.controller.ts:29:31)\n"
                f"    at process.processTicksAndRejections (node:internal/process/task_queues:95:5)",
            ),
            (
                "DatabasePool",
                f"Connection failed while executing query reqId={req_id}",
                f"Error: connect ECONNREFUSED 10.0.14.22:5432\n"
                f"    at TCPConnectWrap.afterConnect [as oncomplete] (node:net:1595:16)\n"
                f"    at Pool._acquireClient (/app/node_modules/pg-pool/index.js:284:19)\n"
                f"    at OrderRepository.findById (/app/src/repositories/order.repository.ts:52:20)\n"
                f"    at async OrderController.getOrder (/app/src/controllers/order.controller.ts:18:14)",
            ),
        )
        comp, msg, trace = random.choice(err_choices)
        header = f"{ts}ERROR [pid:{pid}] [{comp}] {msg}"
        return f"{header}\n{trace}", msg, trace

    if lang == "dotnet":
        ts = (
            f"{dt.strftime('%Y-%m-%d %H:%M:%S')}.{ms:03d} " if include_timestamp else ""
        )
        short_lvl = _DOTNET_LEVEL_MAP.get(lvl, "INF")
        if not is_err:
            choices = (
                (
                    "MyCompany.Orders.Api.Controllers.OrdersController",
                    f"Processed order {order_id} for user {user_id} in {latency_ms}ms (TraceId={req_id})",
                ),
                (
                    "Microsoft.AspNetCore.Hosting.Diagnostics",
                    f"Request finished HTTP/1.1 GET /api/orders/{order_id} - 200 in {latency_ms}.4ms",
                ),
                (
                    "Microsoft.EntityFrameworkCore.Database.Command",
                    f"Executed DbCommand ({latency_ms}ms) [Parameters=[@p0='{order_id}'], CommandType='Text']",
                ),
            )
            cat, msg = random.choice(choices)
            return f"{ts}[{short_lvl}] [{cat}] {msg}", msg, None

        err_choices = (
            (
                "Microsoft.AspNetCore.Diagnostics.ExceptionHandlerMiddleware",
                f"An unhandled exception has occurred while executing the request (TraceId={req_id}, OrderId={order_id})",
                f"System.InvalidOperationException: Timeout expired. The timeout period elapsed prior to obtaining a connection from the pool.\n"
                f" ---> Microsoft.Data.SqlClient.SqlException (0x80131904): Connection Timeout Expired.\n"
                f"   at Microsoft.Data.ProviderBase.DbConnectionPool.TryGetConnection(DbConnection owningObject, UInt32 waitForMultipleObjectsTimeout)\n"
                f"   at Microsoft.EntityFrameworkCore.Storage.RelationalConnection.OpenAsync(CancellationToken cancellationToken)\n"
                f"   --- End of inner exception stack trace ---\n"
                f"   at MyCompany.Orders.Infrastructure.OrderRepository.GetByIdAsync(String orderId) in /src/Orders.Infrastructure/OrderRepository.cs:line 74\n"
                f"   at MyCompany.Orders.Api.Controllers.OrdersController.Get(String orderId) in /src/Orders.Api/Controllers/OrdersController.cs:line 42\n"
                f"   at Microsoft.AspNetCore.Mvc.Infrastructure.ActionMethodExecutor.TaskOfIActionResultExecutor.Execute(ActionContext actionContext)",
            ),
            (
                "MyCompany.Orders.Application.CheckoutHandler",
                f"Failed to complete checkout for OrderId={order_id} UserId={user_id}",
                f"System.NullReferenceException: Object reference not set to an instance of an object.\n"
                f"   at MyCompany.Orders.Domain.Order.ApplyDiscount(Coupon coupon) in /src/Orders.Domain/Order.cs:line 118\n"
                f"   at MyCompany.Orders.Application.CheckoutHandler.HandleAsync(CheckoutCommand cmd, CancellationToken ct) in /src/Orders.Application/CheckoutHandler.cs:line 63\n"
                f"   at MyCompany.Orders.Api.Endpoints.OrderEndpoints.Checkout(CheckoutRequest req) in /src/Orders.Api/Endpoints/OrderEndpoints.cs:line 29",
            ),
        )
        cat, msg, trace = random.choice(err_choices)
        header = f"{ts}[ERR] [{cat}] {msg}"
        return f"{header}\n{trace}", msg, trace

    if lang == "ruby":
        sev_char = lvl[0]
        ts = (
            f"{sev_char}, [{dt.strftime('%Y-%m-%dT%H:%M:%S.%f')} #{pid}] "
            if include_timestamp
            else ""
        )
        if not is_err:
            choices = (
                (
                    "OrdersController",
                    f"Completed 200 OK in {latency_ms}ms (Views: 3.2ms | ActiveRecord: 5.1ms) order_id={order_id} request_id={req_id}",
                ),
                (
                    "Sidekiq::JobRetry",
                    f"Processed OrderFulfillmentWorker jid={req_id} user_id={user_id} elapsed={latency_ms}ms",
                ),
                (
                    "ActiveRecord::Base",
                    f'Order Load ({latency_ms}.1ms) SELECT "orders".* FROM "orders" WHERE "orders"."id" = \'{order_id}\' LIMIT 1',
                ),
            )
            prog, msg = random.choice(choices)
            return f"{ts}{lvl:>5} -- [{prog}]: {msg}", msg, None

        err_choices = (
            (
                "OrdersController",
                f"ActiveRecord::ConnectionTimeoutError (could not obtain a connection from the pool within 5.000 seconds) request_id={req_id}",
                f"\tfrom /gems/ruby/3.2.0/gems/activerecord-7.1.2/lib/active_record/connection_adapters/abstract/connection_pool.rb:218:in `block in wait_poll'\n"
                f"\tfrom /gems/ruby/3.2.0/gems/activerecord-7.1.2/lib/active_record/connection_adapters/abstract/connection_pool.rb:197:in `checkout'\n"
                f"\tfrom /app/repositories/order_repository.rb:44:in `find_order!'\n"
                f"\tfrom /app/controllers/orders_controller.rb:58:in `confirm'\n"
                f"\tfrom /gems/ruby/3.2.0/gems/actionpack-7.1.2/lib/action_controller/metal/basic_implicit_render.rb:6:in `send_action'",
            ),
            (
                "CheckoutService",
                f"NoMethodError (undefined method `total_cents' for nil:NilClass) order_id={order_id}",
                f"\tfrom /app/services/checkout_service.rb:79:in `charge_customer!'\n"
                f"\tfrom /app/services/checkout_service.rb:34:in `call'\n"
                f"\tfrom /app/controllers/checkout_controller.rb:27:in `create'\n"
                f"\tfrom /gems/ruby/3.2.0/gems/puma-6.4.0/lib/puma/request.rb:100:in `handle_request'",
            ),
        )
        prog, msg, trace = random.choice(err_choices)
        header = f"{ts}ERROR -- [{prog}]: {msg}"
        return f"{header}\n{trace}", msg, trace

    if lang == "rust":
        ts = (
            f"{dt.strftime('%Y-%m-%dT%H:%M:%S.%f')}{tz_iso} "
            if include_timestamp
            else ""
        )
        if not is_err:
            choices = (
                (
                    "order_service::handlers::orders",
                    f"request completed method=GET path=/api/v1/orders/{order_id} status=200 latency_ms={latency_ms} req_id={req_id}",
                ),
                (
                    "order_service::db::pool",
                    f"acquired postgres connection user_id={user_id} wait_us=142 active=6 idle=10",
                ),
                (
                    "order_service::worker::consumer",
                    f"committed kafka offset partition=2 offset={user_id * 10} order_id={order_id}",
                ),
            )
            target, msg = random.choice(choices)
            return f"{ts}{lvl:>5} {target}: {msg}", msg, None

        err_choices = (
            (
                "order_service::handlers::orders",
                f"thread 'tokio-runtime-worker' panicked at src/handlers/orders.rs:112:34: called `Result::unwrap()` on an `Err` value: PoolTimedOut(order_id={order_id})",
                f"stack backtrace:\n"
                f"   0: rust_begin_unwind\n"
                f"             at /rustc/07dca489ac2d933c78d3c5158e3f43beefeb02ce/library/std/src/panicking.rs:645:5\n"
                f"   1: core::panicking::panic_fmt\n"
                f"             at /rustc/07dca489ac2d933c78d3c5158e3f43beefeb02ce/library/core/src/panicking.rs:72:14\n"
                f"   2: core::result::unwrap_failed\n"
                f"             at /rustc/07dca489ac2d933c78d3c5158e3f43beefeb02ce/library/core/src/result.rs:1649:5\n"
                f"   3: order_service::handlers::orders::fetch_order\n"
                f"             at ./src/handlers/orders.rs:112:34\n"
                f"   4: tokio::runtime::task::core::Core<T,S>::poll\n"
                f"             at /cargo/registry/src/index.crates.io/tokio-1.36.0/src/runtime/task/core.rs:328:17\n"
                f"note: Some details are omitted, run with `RUST_BACKTRACE=full` for a verbose backtrace.",
            ),
        )
        target, msg, trace = random.choice(err_choices)
        header = f"{ts}ERROR {target}: {msg}"
        return f"{header}\n{trace}", msg, trace

    # Default / php
    ts = f"[{dt.strftime('%Y-%m-%d %H:%M:%S')}.{ms:03d}] " if include_timestamp else ""
    if not is_err:
        choices = (
            f'Order processed successfully {{"order_id":"{order_id}","user_id":{user_id},"duration_ms":{latency_ms},"request_id":"{req_id}"}}',
            f'Cache hit for user profile {{"user_id":{user_id},"ttl":3600,"request_id":"{req_id}"}}',
            f'Dispatched queued job App\\Jobs\\SendOrderInvoice {{"order_id":"{order_id}","queue":"default"}}',
        )
        msg = random.choice(choices)
        return f"{ts}production.{lvl}: {msg}", msg, None

    msg = f"PDOException: SQLSTATE[HY000] [2002] Connection timed out (order_id={order_id}, request_id={req_id}) in /var/www/html/vendor/laravel/framework/src/Illuminate/Database/Connectors/Connector.php:65"
    trace = (
        f"Stack trace:\n"
        f"#0 /var/www/html/vendor/laravel/framework/src/Illuminate/Database/Connectors/Connector.php(65): PDO->__construct('mysql:host=10.0...', 'app_user', Object(SensitiveParameterValue), Array)\n"
        f"#1 /var/www/html/app/Repositories/OrderRepository.php(84): Illuminate\\Database\\Connection->select('SELECT * FROM o...', Array)\n"
        f"#2 /var/www/html/app/Http/Controllers/OrderController.php(51): App\\Repositories\\OrderRepository->findOrFail('{order_id}')\n"
        f"#3 /var/www/html/public/index.php(52): Illuminate\\Foundation\\Http\\Kernel->handle(Object(Illuminate\\Http\\Request))\n"
        f"#4 {{main}}"
    )
    header = f"{ts}production.ERROR: {msg}"
    return f"{header}\n{trace}", msg, trace


_FORMATTERS = {
    "json": format_json_log,
    "logfmt": format_logfmt_log,
    "http": format_http_log,
    "apache-common": format_apache_common_log,
    "apache-combined": format_apache_combined_log,
    "apache-error": format_apache_error_log,
    "bsd-syslog": format_bsd_syslog_log,
    "syslog": format_rfc5424_syslog_log,
}


def format_log(
    entry: Dict[str, Any], log_format: str, dt: Optional[datetime] = None
) -> str:
    """Format log entry according to specified format.

    Args:
        entry: Log entry dictionary
        log_format: Target format (json, logfmt, http, apache-common, apache-combined,
                    apache-error, bsd-syslog/rfc3164, syslog/rfc5424)
        dt: Optional precomputed datetime to skip timestamp string re-parsing

    Returns:
        str: Formatted log line
    """
    formatter = _FORMATTERS.get(normalize_log_format(log_format), format_json_log)
    return formatter(entry, dt)


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

    def __init__(
        self,
        file_path: str,
        overwrite: bool = False,
        compress: bool = False,
        split_by: int = 0,
        split_unit: str = "lines",
    ) -> None:
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
            self.fh = gzip.open(
                path, self.mode_char + "t", encoding="utf-8", compresslevel=6
            )
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

    def write(self, line: str, line_bytes: Optional[int] = None) -> None:
        """Write a single line (newline appended), rotating first if the split
        threshold for the current part has been reached.

        Args:
            line: Log line to write (without trailing newline)
            line_bytes: Optional precomputed UTF-8 byte length (including newline)
        """
        if self._should_rotate():
            self.close()
            self.part += 1
            self._open()
        self.fh.write(line + "\n")
        self.lines_in_part += 1
        # ponytail: byte-based split counts uncompressed UTF-8 payload, not the
        # on-disk compressed size (unknown until flush). For .gz output the
        # physical part files will be smaller than the --split-by threshold.
        if self.split_by > 0 and self.split_unit == "bytes":
            if line_bytes is None:
                line_bytes = (
                    len(line) if line.isascii() else len(line.encode("utf-8"))
                ) + 1
            self.bytes_in_part += line_bytes

    def close(self) -> None:
        """Close the current file handle if open (safe to call more than once)."""
        if self.fh:
            self.fh.close()
            self.fh = None


_DURATION_RE = re.compile(r"\s*([0-9]*\.?[0-9]+)\s*([a-zA-Z]+)?\s*")
_DURATION_FACTORS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
_SIZE_RE = re.compile(r"([0-9]*\.?[0-9]+)\s*(b|kb|mb|gb)?")
_SIZE_FACTORS = {"": 1, "b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}


def parse_duration(value: str, flag: str = "--time-step") -> float:
    """Parse a duration string into seconds (flog-style).

    Accepts a plain number (seconds) or a suffixed value: ms, s, m, h (case-insensitive).
    ponytail: supported units are ms/s/m/h; a bare number means seconds.

    Args:
        value: Duration string, e.g. '10', '20ms', '5s', '1m'
        flag: CLI flag name used in the error message (e.g. --error-interval)

    Returns:
        float: Duration in seconds

    Raises:
        SystemExit: If the value cannot be parsed
    """
    m = _DURATION_RE.fullmatch(value)
    if not m:
        print(f"Error: invalid {flag} duration '{value}' (use e.g. 10, 20ms, 5s, 1m)")
        raise SystemExit(1)
    num = float(m.group(1))
    unit = (m.group(2) or "s").lower()
    if unit not in _DURATION_FACTORS:
        print(f"Error: invalid {flag} duration '{value}' (use e.g. 10, 20ms, 5s, 1m)")
        raise SystemExit(1)
    return num * _DURATION_FACTORS[unit]


def parse_size(value: Union[str, int], flag: str = "--max-bytes") -> int:
    """Parse a count or human-readable byte size into an integer.

    Accepts plain integers (e.g. '1000', 1048576) or byte sizes:
    b, kb, mb, gb (case-insensitive, 1024-based).

    Args:
        value: Integer or size string (e.g. '500', '10kb', '5mb', '1gb')
        flag: CLI flag name used in the error message

    Returns:
        int: Parsed value in bytes (or lines when unitless)

    Raises:
        SystemExit: If the value cannot be parsed or is negative
    """
    if isinstance(value, int):
        if value < 0:
            print(f"Error: {flag} cannot be negative")
            raise SystemExit(1)
        return value
    s = str(value).strip()
    if s.startswith("-"):
        print(f"Error: {flag} cannot be negative")
        raise SystemExit(1)
    m = _SIZE_RE.fullmatch(s)
    if not m:
        print(
            f"Error: invalid {flag} value '{value}' (use an integer or lowercase size: b, kb, mb, gb — e.g. 10kb, 5mb, 1gb)"
        )
        raise SystemExit(1)
    num = float(m.group(1))
    unit = m.group(2) or ""
    return int(num * _SIZE_FACTORS[unit])


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments
    """
    description = f"""{get_banner()}

fuzzy-train: A versatile fake log generator for testing and development (drop-in flog compatible)."""

    epilog = """Examples:
  Basics (short forms: -f -r -d -t -o -e -z -n -b -w -c -p -s -l):
    python3 fuzzy-train.py                                             # Default json logs to stdout
    python3 fuzzy-train.py -r 5 -z utc                                 # 5 lines/sec, UTC timestamps
    python3 fuzzy-train.py -f logfmt -n 100 -r 1000                    # Short: logfmt, 100 lines then exit

  Formats (json, logfmt, http, apache-common/apache_common, apache-combined/apache_combined, apache-error/apache_error, bsd-syslog/rfc3164, syslog/rfc5424):
    python3 fuzzy-train.py -f apache-common -o file                    # Apache logs to a file
    python3 fuzzy-train.py -f syslog --trace-id-type integer           # Syslog (rfc5424) with integer trace IDs
    python3 fuzzy-train.py -f http --failure-rate 0.05                 # HTTP access logs (simulator-style)

  Drop-in flog compatibility (same flags work out of the box):
    python3 fuzzy-train.py -f apache_common -t log -o app.log -n 100   # flog-style file output
    python3 fuzzy-train.py -f rfc5424 -t gz -o logs.gz -b 1mb -w       # flog-style gzip + byte bound
    python3 fuzzy-train.py -f json -d 200ms -l                         # flog-style 200ms delay in infinite loop

  Language-specific & multi-line stack traces (java, python, go, nodejs, dotnet, ruby, rust, php):
    python3 fuzzy-train.py --stack java --failure-rate 0.2 -r 10       # Java logs with 20% multi-line stack traces
    python3 fuzzy-train.py --stack python -e 5s -r 2                   # Python logs with multi-line Traceback every 5s
    python3 fuzzy-train.py --multiline go --failure-rate 0.1 -n 50     # Go logs with panic/goroutine stack traces

  Error & HTTP simulation (opt-in; defaults unchanged without these flags):
    python3 fuzzy-train.py --failure-rate 0.1 -n 100 -r 1000           # 10% random ERROR probability
    python3 fuzzy-train.py -e 5s -r 2                                  # Emit ERROR every 5s
    python3 fuzzy-train.py -f http --get-post-ratio 0.9 --get-duration-ms 500 --post-duration-ms 2000
    python3 fuzzy-train.py --arrival exponential -r 2

  Field control & reproducibility:
    python3 fuzzy-train.py --min-log-length 200 --max-log-length 300   # Custom message lengths
    python3 fuzzy-train.py --no-timestamp --no-trace-id                # Minimal logs (message only)
    python3 fuzzy-train.py --seed 42 -n 10 -r 1000                     # Deterministic / reproducible output

  Output control (bounded runs use a high rate so they finish fast):
    python3 fuzzy-train.py -n 1000 -r 1000 -o file                     # 1000 lines then exit
    python3 fuzzy-train.py -b 1mb -r 1000 -o file                      # ~1MB then exit (accepts b/kb/mb/gb)
    python3 fuzzy-train.py --duration 30s -r 10                        # Run for 30 seconds then exit
    python3 fuzzy-train.py -c --file logs.log -n 500 -r 1000           # Gzip-compressed output (-c or -t gz)
    python3 fuzzy-train.py --file app.log -n 1000 -p 200 -r 1000       # Split into 200-line files
    python3 fuzzy-train.py -n 100 -s 1m -r 1000                        # Timestamps 1 min apart
"""

    parser = argparse.ArgumentParser(
        usage="%(prog)s [options]",
        description=description,
        epilog=epilog,
        formatter_class=lambda prog: argparse.RawDescriptionHelpFormatter(
            prog, max_help_position=34, width=105
        ),
    )

    parser.add_argument(
        "-v", "--version", action="version", version=f"fuzzy-train {__version__}"
    )

    # Basic Options
    basic = parser.add_argument_group("Basic Options")
    basic.add_argument(
        "-f",
        "--log-format",
        "--format",
        dest="log_format",
        type=str,
        default=DEFAULT_LOG_FORMAT,
        metavar="FORMAT",
        choices=VALID_FORMATS,
        help=f"Output format: json, logfmt, http, apache-common (apache_common), apache-combined (apache_combined), apache-error (apache_error), bsd-syslog (rfc3164), syslog (rfc5424) (default: {DEFAULT_LOG_FORMAT})",
    )
    basic.add_argument(
        "--stack",
        "--multiline",
        dest="stack",
        type=str,
        default=DEFAULT_STACK,
        metavar="LANG",
        choices=VALID_STACKS,
        help="Language-specific logs with realistic multi-line ERROR stack traces: java, python (py), go (golang), nodejs (node/js), dotnet (csharp/cs), ruby (rb), rust (rs), php",
    )
    speed_group = basic.add_mutually_exclusive_group()
    speed_group.add_argument(
        "-r",
        "--lines-per-second",
        dest="lines_per_second",
        type=float,
        default=DEFAULT_LINES_PER_SECOND,
        metavar="RATE",
        help=f"Generation rate in lines/sec (default: {DEFAULT_LINES_PER_SECOND})",
    )
    speed_group.add_argument(
        "-d",
        "--delay",
        dest="delay",
        type=str,
        default=None,
        metavar="DURATION",
        help="Delay between log lines, e.g. 200ms, 1s (flog-compatible; mutually exclusive with -r)",
    )
    basic.add_argument(
        "--arrival",
        type=str,
        default=DEFAULT_ARRIVAL,
        metavar="MODE",
        choices=["fixed", "exponential"],
        help=f"Inter-arrival pacing: fixed (sleep 1/rate) or exponential (default: {DEFAULT_ARRIVAL})",
    )
    basic.add_argument(
        "-t",
        "--type",
        dest="output_type",
        type=str,
        default=None,
        metavar="TYPE",
        choices=["stdout", "log", "gz", "file"],
        help="Output type: stdout, log (file), or gz (gzipped file) (flog-compatible)",
    )
    basic.add_argument(
        "-o",
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        metavar="TARGET",
        help=f"Output destination ('stdout', 'file') or file path (flog-compatible; default: {DEFAULT_OUTPUT})",
    )
    basic.add_argument(
        "--file",
        type=str,
        metavar="PATH",
        help=f"File path for log output (default when writing to file: {DEFAULT_FILE})",
    )

    # Log Content
    content = parser.add_argument_group("Log Content")
    content.add_argument(
        "--min-log-length",
        type=int,
        default=DEFAULT_MIN_LOG_LENGTH,
        metavar="LENGTH",
        help=f"Minimum message length in characters (default: {DEFAULT_MIN_LOG_LENGTH})",
    )
    content.add_argument(
        "--max-log-length",
        type=int,
        default=DEFAULT_MAX_LOG_LENGTH,
        metavar="LENGTH",
        help=f"Maximum message length in characters (default: {DEFAULT_MAX_LOG_LENGTH})",
    )
    content.add_argument(
        "-z",
        "--time-zone",
        type=str,
        default=DEFAULT_TIME_ZONE,
        metavar="ZONE",
        choices=["local", "utc"],
        help=f"Timestamp timezone: local or utc (default: {DEFAULT_TIME_ZONE})",
    )
    content.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        metavar="INT",
        help="Random seed for deterministic/reproducible log generation",
    )

    # Error & HTTP Simulation
    sim = parser.add_argument_group("Error & HTTP Simulation")
    err_group = sim.add_mutually_exclusive_group()
    err_group.add_argument(
        "--failure-rate",
        type=float,
        default=DEFAULT_FAILURE_RATE,
        metavar="RATE",
        help="Probability of ERROR / HTTP 500 (0.0-1.0; mutually exclusive with -e)",
    )
    err_group.add_argument(
        "-e",
        "--error-interval",
        type=str,
        default=DEFAULT_ERROR_INTERVAL,
        metavar="DURATION",
        help="Emit an ERROR / HTTP 500 every DURATION, e.g. 5s, 30s, 1m (mutually exclusive with --failure-rate)",
    )
    sim.add_argument(
        "--get-post-ratio",
        type=float,
        default=DEFAULT_GET_POST_RATIO,
        metavar="RATIO",
        help="P(GET) vs POST for http/apache (0.0-1.0; http defaults to 0.9 when unset)",
    )
    sim.add_argument(
        "--get-duration-ms",
        type=float,
        default=DEFAULT_GET_DURATION_MS,
        metavar="MS",
        help=f"Mean GET duration in ms for http format (default: {DEFAULT_GET_DURATION_MS})",
    )
    sim.add_argument(
        "--post-duration-ms",
        type=float,
        default=DEFAULT_POST_DURATION_MS,
        metavar="MS",
        help=f"Mean POST duration in ms for http format (default: {DEFAULT_POST_DURATION_MS})",
    )

    # Field Control
    fields = parser.add_argument_group("Field Control (use --no-* to exclude fields)")
    fields.add_argument(
        "--no-trace-id", action="store_true", help="Exclude trace_id field"
    )
    fields.add_argument(
        "--trace-id-type",
        type=str,
        default=DEFAULT_TRACE_ID_TYPE,
        metavar="TYPE",
        choices=["pid", "integer"],
        help=f"Trace ID type: pid (PID/Container) or integer (incremental) (default: {DEFAULT_TRACE_ID_TYPE})",
    )
    fields.add_argument(
        "--no-timestamp", action="store_true", help="Exclude timestamp field"
    )
    fields.add_argument(
        "--no-log-level", action="store_true", help="Exclude log level field"
    )
    fields.add_argument(
        "--no-length", action="store_true", help="Exclude message length field"
    )

    # Output Control (flog-compatible; all opt-in, streaming stays the default)
    outctl = parser.add_argument_group("Output Control")
    outctl.add_argument(
        "-n",
        "--count",
        "--number",
        dest="count",
        type=int,
        default=DEFAULT_COUNT,
        metavar="N",
        help="Generate N lines then exit (default: 0 = infinite streaming)",
    )
    outctl.add_argument(
        "-b",
        "--max-bytes",
        "--bytes",
        dest="max_bytes",
        type=str,
        default=str(DEFAULT_MAX_BYTES),
        metavar="SIZE",
        help="Generate until >= SIZE bytes then exit, e.g. 1048576, 10kb, 5mb, 1gb (ignored when -n is set)",
    )
    outctl.add_argument(
        "--duration",
        type=str,
        default=DEFAULT_DURATION,
        metavar="DURATION",
        help="Run for DURATION then exit (e.g. 10s, 5m, 1h)",
    )
    outctl.add_argument(
        "-l",
        "--loop",
        action="store_true",
        help="Loop output forever until killed (flog-compatible; default when -n/-b/--duration unset)",
    )
    outctl.add_argument(
        "-w",
        "--overwrite",
        action="store_true",
        help="Truncate the output file before writing instead of appending",
    )
    outctl.add_argument(
        "-c",
        "--compress",
        action="store_true",
        help="Gzip file output (also auto-enabled with -t gz or when file ends with .gz)",
    )
    outctl.add_argument(
        "-p",
        "--split-by",
        type=str,
        default=str(DEFAULT_SPLIT_BY),
        metavar="SIZE",
        help="Rotate output file every N lines (or SIZE bytes like 10mb when -b is used)",
    )
    outctl.add_argument(
        "-s",
        "--time-step",
        "--sleep",
        dest="time_step",
        type=str,
        default=DEFAULT_TIME_STEP,
        metavar="DURATION",
        help="Advance each log's timestamp by DURATION without real waiting (e.g. 10, 20ms, 5s, 1m)",
    )
    return parser.parse_args()


def get_arg_value(args: argparse.Namespace, name: str) -> Any:
    """Get argument value handling both underscore and hyphen variants.

    Args:
        args: Parsed arguments namespace
        name: Argument name (with hyphens)

    Returns:
        Any: Argument value
    """
    underscore_name = name.replace("-", "_")
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
        print(
            f"Error: min-log-length ({min_len}) cannot be greater than max-log-length ({max_len})"
        )
        print(
            "Please provide valid length parameters where min-log-length <= max-log-length"
        )
        raise SystemExit(1)

    return min_len, max_len


def build_log_entry(
    timestamp: str,
    log_level: str,
    message: str,
    trace_id: Optional[str],
    include_timestamp: bool,
    include_log_level: bool,
    include_length: bool,
) -> Dict[str, Any]:
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
    min_len = get_arg_value(args, "min-log-length")
    max_len = get_arg_value(args, "max-log-length")
    min_len, max_len = validate_length_params(min_len, max_len)

    lps = get_arg_value(args, "lines-per-second")
    delay_raw = get_arg_value(args, "delay")
    include_trace_id = not (get_arg_value(args, "no-trace-id") or False)
    trace_id_type = get_arg_value(args, "trace-id-type").lower()
    include_timestamp = not (get_arg_value(args, "no-timestamp") or False)
    include_log_level = not (get_arg_value(args, "no-log-level") or False)
    include_length = not (get_arg_value(args, "no-length") or False)
    tz = get_arg_value(args, "time-zone")
    log_format = args.log_format
    stack = normalize_stack(get_arg_value(args, "stack"))
    explicit_format = any(
        arg in ("-f", "--log-format", "--format")
        or arg.startswith(("--log-format=", "--format="))
        for arg in sys.argv[1:]
    )
    raw_output = args.output
    output_type = get_arg_value(args, "output_type")
    file_path = args.file
    failure_rate = get_arg_value(args, "failure-rate")
    error_interval_raw = get_arg_value(args, "error-interval")
    get_post_ratio = get_arg_value(args, "get-post-ratio")
    get_duration_ms = get_arg_value(args, "get-duration-ms")
    post_duration_ms = get_arg_value(args, "post-duration-ms")
    arrival = (get_arg_value(args, "arrival") or DEFAULT_ARRIVAL).lower()
    seed = get_arg_value(args, "seed")

    if seed is not None:
        random.seed(seed)
        if FAKER_AVAILABLE and fake is not None:
            Faker.seed(seed)
            fake.seed_instance(seed)

    # Output-control parameters (argparse supplies defaults, so values are never None)
    count = get_arg_value(args, "count")
    max_bytes_raw = get_arg_value(args, "max-bytes")
    duration_raw = get_arg_value(args, "duration")
    overwrite = bool(get_arg_value(args, "overwrite"))
    compress = bool(get_arg_value(args, "compress"))
    split_by_raw = get_arg_value(args, "split-by")
    time_step_raw = get_arg_value(args, "time-step")

    if count < 0:
        print("Error: --count cannot be negative")
        raise SystemExit(1)
    max_bytes = (
        parse_size(max_bytes_raw, "--max-bytes") if max_bytes_raw is not None else 0
    )
    split_by = parse_size(split_by_raw, "--split-by") if split_by_raw is not None else 0

    # flog -d/--delay support: convert per-line delay to lines-per-second
    if delay_raw is not None:
        delay_sec = parse_duration(delay_raw, "--delay")
        if delay_sec < 0:
            print("Error: --delay cannot be negative")
            raise SystemExit(1)
        lps = (1.0 / delay_sec) if delay_sec > 0 else 1_000_000.0

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

    # --count/-n takes precedence over --max-bytes/-b (flog parity: "bytes" ignored when "number" is set)
    if count > 0:
        max_bytes = 0

    error_interval = (
        parse_duration(error_interval_raw, "--error-interval")
        if error_interval_raw is not None
        else None
    )
    if error_interval is not None and error_interval <= 0:
        print("Error: --error-interval must be greater than 0")
        raise SystemExit(1)

    run_duration = (
        parse_duration(duration_raw, "--duration") if duration_raw is not None else None
    )
    if run_duration is not None and run_duration <= 0:
        print("Error: --duration must be greater than 0")
        raise SystemExit(1)

    # Parse fake-time step (seconds); None = real wall-clock
    time_step = (
        parse_duration(time_step_raw, "--time-step")
        if time_step_raw is not None
        else None
    )

    # split-by unit follows the active bound: bytes when byte-bounded (or when a byte suffix like mb is given), else lines
    has_byte_suffix = isinstance(split_by_raw, str) and bool(
        re.search(r"(?:kb|mb|gb|b)$", split_by_raw.strip(), re.IGNORECASE)
    )
    split_unit = (
        "bytes" if ((max_bytes > 0 and count == 0) or has_byte_suffix) else "lines"
    )

    # Resolve -o/--output and -t/--type (supports both fuzzy-train `-o file` and flog `-t log -o /path/to/file.log`)
    if raw_output.lower() in ("stdout", "file"):
        output = raw_output.lower()
    else:
        # flog-style: -o <filepath>
        if not file_path:
            file_path = raw_output
        output = "stdout" if output_type == "stdout" else "file"

    if output_type is not None:
        if output_type == "stdout":
            output = "stdout"
        elif output_type in ("log", "file"):
            output = "file"
        elif output_type == "gz":
            output = "file"
            compress = True

    # gzip/overwrite/split are file-only; auto-enable file output if requested
    # (these can't apply to stdout, so file output is implied).
    file_features = compress or overwrite or split_by > 0
    if file_features and output != "file" and not file_path:
        output = "file"
        print(
            f"Note: --compress/--overwrite/--split-by imply file output; writing to {DEFAULT_FILE}",
            file=sys.stderr,
        )

    # Output logic
    to_stdout = (output == "stdout") or (output == "" and not file_path)
    to_file = (output == "file") or (file_path is not None and output_type != "stdout")
    if to_file and not file_path:
        file_path = DEFAULT_FILE

    handler = None
    if to_file:
        handler = OutputHandler(
            file_path,
            overwrite=overwrite,
            compress=compress,
            split_by=split_by,
            split_unit=split_unit,
        )

    # Synthetic clock base for --time-step
    synthetic_time = datetime.now(timezone.utc) if time_step is not None else None
    step_delta = timedelta(seconds=time_step) if time_step is not None else None
    start_clock = (
        synthetic_time if synthetic_time is not None else datetime.now(timezone.utc)
    )

    format_lower = normalize_log_format(log_format)
    formatter = _FORMATTERS.get(format_lower, format_json_log)
    is_native_stack = (stack is not None) and (not explicit_format)
    is_http = (not is_native_stack) and (format_lower == "http")
    is_apache_access = (not is_native_stack) and (
        format_lower in ("apache-common", "apache-combined")
    )
    needs_iso_timestamp = (not is_native_stack) and (
        format_lower in ("json", "logfmt", "http")
    )
    needs_byte_count = (max_bytes > 0) or (split_by > 0 and split_unit == "bytes")
    is_exp_arrival = arrival == "exponential"
    fixed_interval = 1.0 / lps
    should_sleep_fixed = (not is_exp_arrival) and (fixed_interval >= 0.001)

    # http format mirrors the simulator: unset --failure-rate means 0% failures
    # (always 200), not the legacy apache multi-status mix.
    effective_failure_rate = 0.0 if (is_http and failure_rate is None) else failure_rate

    # When --error-interval is set, it drives periodic errors (and non-errors in between).
    has_failure_control = (effective_failure_rate is not None) or (
        error_interval is not None
    )
    effective_rate_for_choice = (
        0.0
        if (error_interval is not None and effective_failure_rate is None)
        else effective_failure_rate
    )

    lines_written = 0
    bytes_written = 0
    last_error_at: Optional[datetime] = None
    try:
        while True:
            now_clock = (
                synthetic_time
                if synthetic_time is not None
                else datetime.now(timezone.utc)
            )
            # Stop conditions (bounded batch mode); count beats bytes
            if count > 0 and lines_written >= count:
                break
            if max_bytes > 0 and bytes_written >= max_bytes:
                break
            if (
                run_duration is not None
                and (now_clock - start_clock).total_seconds() >= run_duration
            ):
                break
            if error_interval is not None:
                failed, last_error_at = should_emit_interval_error(
                    error_interval, last_error_at, now_clock
                )
            else:
                # One roll drives level + status when a failure rate applies.
                failed = (
                    None
                    if effective_failure_rate is None
                    else (random.random() < effective_failure_rate)
                )
            log_level = choose_log_level(effective_rate_for_choice, failed)
            trace_id = generate_trace_id(include_trace_id, trace_id_type)
            dt_local_or_utc = now_clock.astimezone() if tz == "local" else now_clock

            if is_native_stack:
                line, _, _ = generate_stack_event(
                    stack,
                    log_level,
                    dt_local_or_utc,
                    include_timestamp=include_timestamp,
                    tz=tz,
                    entry={"trace_id": trace_id},
                )
            else:
                stack_trace = None
                if stack is not None:
                    _, message, stack_trace = generate_stack_event(
                        stack,
                        log_level,
                        dt_local_or_utc,
                        include_timestamp=include_timestamp,
                        tz=tz,
                        entry={"trace_id": trace_id},
                    )
                elif is_http:
                    message = ""
                else:
                    message_length = (
                        min_len
                        if min_len == max_len
                        else random.randint(min_len, max_len)
                    )
                    message = generate_random_message(message_length)

                if needs_iso_timestamp and (include_timestamp or is_http):
                    timestamp = generate_timestamp(tz, base=now_clock)
                else:
                    timestamp = ""

                # Build log entry with optimal field ordering for UX
                log_entry = build_log_entry(
                    timestamp,
                    log_level,
                    message,
                    trace_id,
                    include_timestamp,
                    include_log_level,
                    include_length,
                )
                if stack is not None:
                    log_entry["stack"] = stack
                    if stack_trace is not None:
                        log_entry["stacktrace"] = stack_trace

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
                    log_entry["status"] = choose_http_status(
                        effective_rate_for_choice, failed
                    )
                    log_entry["duration_ms"] = choose_duration_ms(
                        method, get_duration_ms, post_duration_ms
                    )
                elif is_apache_access:
                    # Apache lines have no level field; --failure-rate / --error-interval drives status.
                    if has_failure_control:
                        log_entry["status"] = choose_http_status(
                            effective_rate_for_choice, failed
                        )
                    if get_post_ratio is not None:
                        log_entry["method"] = choose_http_method(get_post_ratio)

                dt_for_format = dt_local_or_utc if not needs_iso_timestamp else None
                line = formatter(log_entry, dt_for_format)
            if to_stdout:
                print(line, flush=should_sleep_fixed or is_exp_arrival)
            if needs_byte_count:
                line_bytes = (
                    len(line) if line.isascii() else len(line.encode("utf-8"))
                ) + 1
                bytes_written += line_bytes
            else:
                line_bytes = None
            if handler:
                handler.write(line, line_bytes)

            lines_written += 1
            if step_delta is not None:
                synthetic_time += step_delta

            # ponytail: fixed mode skips sub-millisecond sleeps — OS timer granularity
            # (~1ms) would throttle throughput at high rates (e.g. 2000+ lines/sec).
            # Exponential always sleeps the drawn gap so mean rate stays ~lps
            # (matches the web-server simulator). Ceiling: best-effort pacing.
            if is_exp_arrival:
                # Mean inter-arrival = 1/lps (same mean as fixed mode).
                time.sleep(random.expovariate(lps))
            elif should_sleep_fixed:
                time.sleep(fixed_interval)
    except KeyboardInterrupt:
        print("\nLog generation stopped.")
    except BrokenPipeError:
        # Piped to a consumer that exited (e.g. head, grep, restarted shipper).
        # Suppress Python's noisy unhandled exception output on exit.
        try:
            sys.stderr.close()
        except Exception:
            pass
    finally:
        if handler:
            handler.close()


if __name__ == "__main__":
    main()
