#!/usr/bin/env python3
"""fuzzy-train: a versatile fake log generator for testing and development.

Streams or batch-generates fake logs in multiple formats (JSON, logfmt, Apache
common/combined/error, BSD RFC3164 and RFC5424 syslog). Log content and format
fields are enriched with realistic data via the optional `faker` package when
installed, and fall back to a built-in zero-dependency generator otherwise.

Output control (all opt-in; infinite real-time streaming is the default):
bounded generation by line count or byte size, file overwrite, gzip output,
file splitting/rotation, and fake-time timestamp stepping.
"""

import argparse
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
from typing import Dict, Any, Optional

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
__version__ = "2.3.0"
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

def parse_entry_timestamp(entry: Dict[str, Any]) -> datetime:
    """Parse an entry's timestamp into a datetime for reformatting.

    Tries ISO 8601 (datetime.fromisoformat, tolerant of a trailing 'Z' and
    timezone offsets) and falls back to the fixed second-precision prefix.
    Robust to custom timestamp formats a future extension might introduce.

    Args:
        entry: Log entry dict; may contain a 'timestamp' string

    Returns:
        datetime: Parsed timestamp (naive), or current time if absent/unparseable
    """
    ts = entry.get('timestamp')
    if not ts:
        return datetime.now()
    try:
        # Normalize a trailing 'Z' (UTC) which older fromisoformat rejects.
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return datetime.now()

def format_json_log(entry: Dict[str, Any]) -> str:
    """Format log entry as JSON."""
    return json.dumps(entry)

def format_logfmt_log(entry: Dict[str, Any]) -> str:
    """Format log entry as logfmt."""
    return ' '.join(f'{k}="{str(v).replace("\"", "\\\"")}"' for k, v in entry.items())

def format_apache_common_log(entry: Dict[str, Any]) -> str:
    """Format log entry as Apache Common Log Format."""
    host = fake.ipv4() if FAKER_AVAILABLE else "127.0.0.1"
    ident = "-"
    user = "-"
    dt = parse_entry_timestamp(entry)
    tstr = dt.strftime("[%d/%b/%Y:%H:%M:%S +0000]")
    request = f"{fake.http_method()} /{fake.uri_path()} HTTP/1.1" if FAKER_AVAILABLE else "GET /index.html HTTP/1.1"
    status = random.choice([200, 404, 500, 302])
    size = len(entry['message'])
    return f'{host} {ident} {user} {tstr} "{request}" {status} {size}'

def format_apache_combined_log(entry: Dict[str, Any]) -> str:
    """Format log entry as Apache Combined Log Format."""
    host = fake.ipv4() if FAKER_AVAILABLE else "127.0.0.1"
    ident = "-"
    user = "-"
    dt = parse_entry_timestamp(entry)
    tstr = dt.strftime("[%d/%b/%Y:%H:%M:%S +0000]")
    request = f"{fake.http_method()} /{fake.uri_path()} HTTP/1.1" if FAKER_AVAILABLE else "GET /index.html HTTP/1.1"
    status = random.choice([200, 404, 500, 302])
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

def format_log(entry: Dict[str, Any], log_format: str) -> str:
    """Format log entry according to specified format.

    Args:
        entry: Log entry dictionary
        log_format: Target format (JSON, logfmt, apache, syslog, etc.)

    Returns:
        str: Formatted log line
    """
    format_lower = log_format.lower()

    if format_lower == "json":
        return format_json_log(entry)
    elif format_lower == "logfmt":
        return format_logfmt_log(entry)
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
        self.fh.write(line + "\n")
        self.lines_in_part += 1
        # ponytail: byte-based split counts uncompressed UTF-8 payload, not the
        # on-disk compressed size (unknown until flush). For .gz output the
        # physical part files will be smaller than the --split-by threshold.
        self.bytes_in_part += len(line.encode("utf-8")) + 1

    def close(self) -> None:
        """Close the current file handle if open (safe to call more than once)."""
        if self.fh:
            self.fh.close()
            self.fh = None

def parse_duration(value: str) -> float:
    """Parse a duration string into seconds (flog-style).

    Accepts a plain number (seconds) or a suffixed value: ms, s, m, h.
    ponytail: supported units are ms/s/m/h; a bare number means seconds.

    Args:
        value: Duration string, e.g. '10', '20ms', '5s', '1m'

    Returns:
        float: Duration in seconds

    Raises:
        SystemExit: If the value cannot be parsed
    """
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*(ms|s|m|h)?\s*", value)
    if not m:
        print(f"Error: invalid --time-step duration '{value}' (use e.g. 10, 20ms, 5s, 1m)")
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
                       help=f"Output format: JSON, logfmt, 'apache common', 'apache combined', 'apache error', 'bsd syslog', syslog (default: {DEFAULT_LOG_FORMAT})")
    basic.add_argument("--lines-per-second", type=float, default=DEFAULT_LINES_PER_SECOND, metavar="RATE",
                       help=f"Generation rate (default: {DEFAULT_LINES_PER_SECOND})")
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

    # Field Control
    fields = parser.add_argument_group('Field Control (use --no-* to exclude fields)')
    fields.add_argument("--no-trace-id", action="store_true",
                        help="Exclude trace_id field")
    fields.add_argument("--trace-id-type", type=str, default=DEFAULT_TRACE_ID_TYPE, metavar="TYPE",
                        choices=["pid", "integer"],
                        help=f"Trace ID type: pid (PID/Container) or integer (incremental) (default: {DEFAULT_TRACE_ID_TYPE})")
    fields.add_argument("--no-timestamp", action="store_true",
                        help="Exclude timestamp field")
    fields.add_argument("--no-log-level", action="store_true",
                        help="Exclude log level field")
    fields.add_argument("--no-length", action="store_true",
                        help="Exclude message length field")

    # Output Control (flog-inspired; all opt-in, streaming stays the default)
    outctl = parser.add_argument_group('Output Control')
    outctl.add_argument("-n", "--count", type=int, default=DEFAULT_COUNT, metavar="N",
                        help="Generate exactly N lines then exit (default: 0 = infinite streaming)")
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

    # --count takes precedence over --max-bytes (flog parity)
    if count > 0:
        max_bytes = 0

    # Parse fake-time step (seconds); None = real wall-clock
    time_step = parse_duration(time_step_raw) if time_step_raw is not None else None

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

    lines_written = 0
    bytes_written = 0
    try:
        while True:
            # Stop conditions (bounded batch mode); count beats bytes
            if count > 0 and lines_written >= count:
                break
            if max_bytes > 0 and bytes_written >= max_bytes:
                break

            log_level = random.choice(LOG_LEVELS)
            trace_id = generate_trace_id(include_trace_id, trace_id_type)
            message_length = random.randint(min_len, max_len)
            message = generate_random_message(message_length)
            timestamp = generate_timestamp(tz, base=synthetic_time)

            # Build log entry with optimal field ordering for UX
            log_entry = build_log_entry(
                timestamp, log_level, message, trace_id,
                include_timestamp, include_log_level, include_length
            )
            line = format_log(log_entry, log_format)
            if to_stdout:
                print(line, flush=True)  # flush for real-time tailing in pipes/containers
            if handler:
                handler.write(line)

            lines_written += 1
            bytes_written += len(line.encode("utf-8")) + 1
            if synthetic_time is not None:
                synthetic_time += timedelta(seconds=time_step)

            # ponytail: skip sub-millisecond sleeps — OS timer granularity (~1ms)
            # would throttle throughput at high rates (e.g. 2000+ lines/sec).
            # Ceiling: this is best-effort pacing, not a precise rate limiter;
            # upgrade path = token-bucket/deadline scheduling if exact rates matter.
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
