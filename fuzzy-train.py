#!/usr/bin/env python3

import argparse
import random
import time
import string
import os
import json
import socket
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

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
__version__ = "2.2.0"
DETAIL_PROBABILITY = 0.3
TRACE_ID_COUNTER = 1

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
DEFAULT_TRACE_ID = "true"
DEFAULT_TRACE_ID_TYPE = "pid"
DEFAULT_TIMESTAMP = "true"
DEFAULT_LOG_LEVEL = "true"
DEFAULT_LENGTH = "true"
DEFAULT_TIME_ZONE = "local"
DEFAULT_LOG_FORMAT = "JSON"
DEFAULT_OUTPUT = "stdout"
DEFAULT_FILE = "fuzzy-train.log"

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

    Args:
        length: Target message length in characters

    Returns:
        str: Generated message truncated to specified length
    """
    message = ""
    while len(message) < length:
        sentence = random.choice(SENTENCES)
        if random.random() < DETAIL_PROBABILITY:
            detail = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(10, 30)))
            sentence += f" Details: {detail}"
        message += sentence + " "
    return message[:length]

def generate_timestamp(time_zone: str) -> str:
    """Generate ISO 8601 timestamp in specified timezone.

    Args:
        time_zone: 'local', 'UTC', 'utc', or 'LOCAL'

    Returns:
        str: ISO 8601 formatted timestamp
    """
    now = datetime.now(timezone.utc)
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
    global TRACE_ID_COUNTER
    if not include_trace_id:
        return None

    if trace_id_type == "pid":
        trace_id = f"{PID}-{TRACE_ID_COUNTER:08d}"
    else:  # integer
        trace_id = f"{TRACE_ID_COUNTER:08d}"

    TRACE_ID_COUNTER += 1
    return trace_id

def format_json_log(entry: Dict[str, Any]) -> str:
    """Format log entry as JSON."""
    return json.dumps(entry)

def format_logfmt_log(entry: Dict[str, Any]) -> str:
    """Format log entry as logfmt."""
    return ' '.join(f'{k}="{str(v).replace("\"", "\\\"")}"' for k, v in entry.items())

def format_apache_common_log(entry: Dict[str, Any]) -> str:
    """Format log entry as Apache Common Log Format."""
    host = "127.0.0.1"
    ident = "-"
    user = "-"
    timestamp = entry.get('timestamp', datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    dt = datetime.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S")
    tstr = dt.strftime("[%d/%b/%Y:%H:%M:%S +0000]")
    request = "GET /index.html HTTP/1.1"
    status = random.choice([200, 404, 500, 302])
    size = len(entry['message'])
    return f'{host} {ident} {user} {tstr} "{request}" {status} {size}'

def format_apache_combined_log(entry: Dict[str, Any]) -> str:
    """Format log entry as Apache Combined Log Format."""
    host = "127.0.0.1"
    ident = "-"
    user = "-"
    timestamp = entry.get('timestamp', datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    dt = datetime.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S")
    tstr = dt.strftime("[%d/%b/%Y:%H:%M:%S +0000]")
    request = "GET /index.html HTTP/1.1"
    status = random.choice([200, 404, 500, 302])
    size = len(entry['message'])
    referer = "https://example.com/"
    ua = "Mozilla/5.0 (compatible; FakeBot/1.0)"
    return f'{host} {ident} {user} {tstr} "{request}" {status} {size} "{referer}" "{ua}"'

def format_apache_error_log(entry: Dict[str, Any]) -> str:
    """Format log entry as Apache Error Log Format."""
    timestamp = entry.get('timestamp', datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    dt = datetime.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S")
    tstr = dt.strftime("%a %b %d %H:%M:%S.%f %Y")
    pid = random.randint(1000, 99999)
    client = f"127.0.0.1:{random.randint(1000, 65535)}"
    level = entry.get('level', 'info').lower()
    return f'[{tstr}] [core:{level}] [pid {pid}] [client {client}] {entry["message"]}'

def format_bsd_syslog_log(entry: Dict[str, Any]) -> str:
    """Format log entry as BSD Syslog (RFC3164)."""
    timestamp = entry.get('timestamp', datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    dt = datetime.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S")
    tstr = dt.strftime("%b %d %H:%M:%S")
    host = "localhost"
    tag = "fuzzy-train"
    pri = "<13>"  # user.notice
    return f'{pri}{tstr} {host} {tag}: {entry["message"]}'

def format_rfc5424_syslog_log(entry: Dict[str, Any]) -> str:
    """Format log entry as RFC5424 Syslog."""
    timestamp = entry.get('timestamp', datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    dt = datetime.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S")
    tstr = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    host = "localhost"
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

def write_log(line: str, file_path: str) -> None:
    """Write log line to file.

    Args:
        line: Log line to write
        file_path: Target file path
    """
    resolved_path = resolve_file_path(file_path)
    with open(resolved_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments
    """
    # Create custom description with banner
    banner = get_banner()
    description = f"fuzzy-train: A versatile fake log generator for testing and development - runs anywhere.\n\n{banner}"

    parser = argparse.ArgumentParser(
        description=description,
        epilog="""Examples:
  python3 fuzzy-train.py                                            # Default JSON logs to stdout
  python3 fuzzy-train.py --log-format 'apache common' --output file # Apache logs to file
  python3 fuzzy-train.py --lines-per-second 5 --time-zone UTC       # High rate with UTC timestamps
  python3 fuzzy-train.py --min-log-length 200 --max-log-length 300  # Custom message lengths
  python3 fuzzy-train.py --no-timestamp --no-trace-id               # Minimal logs (message only)
  python3 fuzzy-train.py --log-format syslog --trace-id-type integer  # Syslog with simple trace IDs
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-v", "--version", action="version", version=f"fuzzy-train {__version__}")

    # Basic Options
    basic = parser.add_argument_group('Basic Options')
    basic.add_argument("--log-format", type=str, default=DEFAULT_LOG_FORMAT, metavar="FORMAT",
                       help=f"Output format: JSON, logfmt, 'apache common', 'apache combined', 'apache error', 'bsd syslog', syslog (default: {DEFAULT_LOG_FORMAT})")
    basic.add_argument("--lines-per-second", type=float, default=DEFAULT_LINES_PER_SECOND, metavar="RATE",
                       help=f"Generation rate (default: {DEFAULT_LINES_PER_SECOND})")
    basic.add_argument("--output", type=str, default=DEFAULT_OUTPUT, metavar="TYPE",
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
    return getattr(args, underscore_name, None) or getattr(args, name, None)

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

    # Output logic
    to_stdout = (output == "stdout") or (output == "" and not file_path)
    to_file = (output == "file") or (file_path is not None)
    if to_file and not file_path:
        file_path = DEFAULT_FILE

    try:
        while True:
            log_level = random.choice(LOG_LEVELS)
            trace_id = generate_trace_id(include_trace_id, trace_id_type)
            message_length = random.randint(min_len, max_len)
            message = generate_random_message(message_length)
            timestamp = generate_timestamp(tz)

            # Build log entry with optimal field ordering for UX
            log_entry = build_log_entry(
                timestamp, log_level, message, trace_id,
                include_timestamp, include_log_level, include_length
            )
            line = format_log(log_entry, log_format)
            if to_stdout:
                print(line)
            if to_file:
                write_log(line, file_path)
            time.sleep(1.0 / lps)
    except KeyboardInterrupt:
        print("\nLog generation stopped.")

if __name__ == "__main__":
    main()
