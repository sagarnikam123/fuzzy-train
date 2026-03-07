#!/usr/bin/env python3
"""
fuzzy-train-skywalking.py - Fake log generator with SkyWalking integration

Based on fuzzy-train.py, this version sends logs to SkyWalking via the Python agent's log reporter.
Logs appear in SkyWalking UI under General Service → <service-name> → Log tab.

Usage:
    python3 fuzzy-train-skywalking.py --help
    python3 fuzzy-train-skywalking.py --lines-per-second 2

Environment Variables:
    SW_AGENT_NAME                         - Service name (default: skywalking-test::fuzzy-train)
    SW_AGENT_COLLECTOR_BACKEND_SERVICES   - Satellite/OAP endpoint (default: skywalking-satellite.skywalking.svc:11800)
    SW_AGENT_LOG_REPORTER_ACTIVE          - Enable log reporter (default: true)
    SW_AGENT_DISABLE                      - Set to 'true' to disable agent (for local testing)
"""

import argparse
import logging
import os
import random
import signal
import socket
import string
import sys
import time
from datetime import datetime, timezone
from typing import Optional

# SkyWalking agent configuration
SW_SERVICE_NAME = os.getenv('SW_AGENT_NAME', 'skywalking-test::fuzzy-train')
SW_BACKEND = os.getenv('SW_AGENT_COLLECTOR_BACKEND_SERVICES', 'skywalking-satellite.skywalking.svc:11800')
SW_AGENT_ENABLED = os.getenv('SW_AGENT_DISABLE', 'false').lower() != 'true'

# Try to initialize SkyWalking agent (may fail locally without proper setup)
if SW_AGENT_ENABLED:
    try:
        from skywalking import agent, config
        config.init(
            agent_collector_backend_services=SW_BACKEND,
            agent_name=SW_SERVICE_NAME,
            agent_log_reporter_active=True,
            agent_log_reporter_level='DEBUG',
            agent_logging_level='WARNING',  # Agent's own logging (not app logs)
        )
        agent.start()
        print(f"[INFO] SkyWalking agent started: {SW_SERVICE_NAME} -> {SW_BACKEND}", file=sys.stderr)
    except ImportError as e:
        print(f"[WARN] SkyWalking agent not available: {e}. Running without agent.", file=sys.stderr)
        SW_AGENT_ENABLED = False
    except Exception as e:
        print(f"[WARN] SkyWalking agent failed to start: {e}. Running without agent.", file=sys.stderr)
        SW_AGENT_ENABLED = False
else:
    print("[INFO] SkyWalking agent disabled (SW_AGENT_DISABLE=true)", file=sys.stderr)

# Now set up application logging
logger = logging.getLogger('fuzzy-train')
logger.setLevel(logging.DEBUG)

# Console handler for stdout
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Constants (matching fuzzy-train.py)
__version__ = "1.0.0"
DETAIL_PROBABILITY = 0.3
TRACE_ID_COUNTER = 1

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

# Default configuration constants
DEFAULT_MIN_LOG_LENGTH = 90
DEFAULT_MAX_LOG_LENGTH = 100
DEFAULT_LINES_PER_SECOND = 1
DEFAULT_TRACE_ID_TYPE = "pid"
DEFAULT_TIME_ZONE = "local"

def get_process_id() -> str:
    """Get process identifier based on environment (PID for local, container ID for containers)."""
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
                return f"{parts[-2]}-{parts[-1]}"[:12] if len(parts) > 2 else parts[-1][:12]

        # Fallback to truncated hostname for Docker/Podman
        return hostname[:12]
    else:
        return str(os.getpid())

PID = get_process_id()

def generate_random_message(length: int) -> str:
    """Generate a random log message of specified length."""
    message = ""
    while len(message) < length:
        sentence = random.choice(SENTENCES)
        if random.random() < DETAIL_PROBABILITY:
            detail = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(10, 30)))
            sentence += f" Details: {detail}"
        message += sentence + " "
    return message[:length]

def generate_timestamp(time_zone: str) -> str:
    """Generate ISO 8601 timestamp in specified timezone."""
    now = datetime.now(timezone.utc)
    if time_zone.lower() == "local":
        now = now.astimezone()
    if time_zone.upper() == "UTC":
        return now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        offset = now.strftime('%z')
        offset_fmt = f"{offset[:3]}:{offset[3:]}" if offset else ""
        return now.strftime(f"%Y-%m-%dT%H:%M:%S.%f{offset_fmt}")

def generate_trace_id(include_trace_id: bool, trace_id_type: str) -> Optional[str]:
    """Generate trace ID for log correlation."""
    global TRACE_ID_COUNTER
    if not include_trace_id:
        return None

    if trace_id_type == "pid":
        trace_id = f"{PID}-{TRACE_ID_COUNTER:08d}"
    else:  # integer
        trace_id = f"{TRACE_ID_COUNTER:08d}"

    TRACE_ID_COUNTER += 1
    return trace_id

def log_message(level: str, message: str, trace_id: Optional[str] = None):
    """Log a message at the specified level with optional trace_id in extra."""
    extra = {'trace_id': trace_id} if trace_id else {}
    
    if level == 'INFO':
        logger.info(message, extra=extra)
    elif level == 'WARN':
        logger.warning(message, extra=extra)
    elif level == 'ERROR':
        logger.error(message, extra=extra)
    elif level == 'DEBUG':
        logger.debug(message, extra=extra)

# Signal handler for graceful shutdown
running = True

def signal_handler(signum, frame):
    global running
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Fake log generator with SkyWalking integration (based on fuzzy-train)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: 1 log per second
  python3 fuzzy-train-skywalking.py

  # High volume: 10 logs per second
  python3 fuzzy-train-skywalking.py --lines-per-second 10

  # Custom message length
  python3 fuzzy-train-skywalking.py --min-log-length 150 --max-log-length 200

  # Without trace ID
  python3 fuzzy-train-skywalking.py --no-trace-id

Environment Variables:
  SW_AGENT_NAME                         Service name in SkyWalking
  SW_AGENT_COLLECTOR_BACKEND_SERVICES   Satellite/OAP endpoint
        """
    )
    
    parser.add_argument('-v', '--version', action='version', version=f'fuzzy-train-skywalking {__version__}')
    
    # Basic Options
    basic = parser.add_argument_group('Basic Options')
    basic.add_argument('--lines-per-second', type=float, default=DEFAULT_LINES_PER_SECOND,
                       help=f'Generation rate (default: {DEFAULT_LINES_PER_SECOND})')
    
    # Log Content
    content = parser.add_argument_group('Log Content')
    content.add_argument('--min-log-length', type=int, default=DEFAULT_MIN_LOG_LENGTH,
                         help=f'Minimum message length in characters (default: {DEFAULT_MIN_LOG_LENGTH})')
    content.add_argument('--max-log-length', type=int, default=DEFAULT_MAX_LOG_LENGTH,
                         help=f'Maximum message length in characters (default: {DEFAULT_MAX_LOG_LENGTH})')
    content.add_argument('--time-zone', type=str, default=DEFAULT_TIME_ZONE,
                         choices=['local', 'UTC', 'utc', 'LOCAL'],
                         help=f'Timestamp timezone (default: {DEFAULT_TIME_ZONE})')
    
    # Field Control
    fields = parser.add_argument_group('Field Control')
    fields.add_argument('--no-trace-id', action='store_true',
                        help='Exclude trace_id field')
    fields.add_argument('--trace-id-type', type=str, default=DEFAULT_TRACE_ID_TYPE,
                        choices=['pid', 'integer'],
                        help=f'Trace ID type: pid or integer (default: {DEFAULT_TRACE_ID_TYPE})')
    
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Validate length params
    min_len = args.min_log_length
    max_len = args.max_log_length
    
    if min_len != DEFAULT_MIN_LOG_LENGTH and max_len == DEFAULT_MAX_LOG_LENGTH:
        max_len = min_len
    elif min_len == DEFAULT_MIN_LOG_LENGTH and max_len != DEFAULT_MAX_LOG_LENGTH:
        min_len = max_len
    
    if min_len > max_len:
        logger.error(f"min-log-length ({min_len}) cannot be greater than max-log-length ({max_len})")
        sys.exit(1)
    
    lps = args.lines_per_second
    include_trace_id = not args.no_trace_id
    trace_id_type = args.trace_id_type.lower()
    tz = args.time_zone
    
    interval = 1.0 / lps if lps > 0 else 1.0
    
    logger.info(f"Starting fuzzy-train-skywalking v{__version__}")
    logger.info(f"Service: {SW_SERVICE_NAME}")
    logger.info(f"Backend: {SW_BACKEND}")
    logger.info(f"Rate: {lps} logs/second")
    logger.info(f"Message length: {min_len}-{max_len} chars")
    logger.info(f"Trace ID: {'enabled (' + trace_id_type + ')' if include_trace_id else 'disabled'}")
    
    count = 0
    while running:
        try:
            log_level = random.choice(LOG_LEVELS)
            trace_id = generate_trace_id(include_trace_id, trace_id_type)
            message_length = random.randint(min_len, max_len)
            message = generate_random_message(message_length)
            
            # Add trace_id to message if enabled (for visibility in logs)
            if trace_id:
                full_message = f"[{trace_id}] {message}"
            else:
                full_message = message
            
            log_message(log_level, full_message, trace_id)
            
            count += 1
            if count % 100 == 0:
                logger.info(f"Generated {count} log entries")
            
            time.sleep(interval)
            
        except Exception as e:
            logger.error(f"Error generating log: {e}")
            time.sleep(1)
    
    logger.info(f"Shutdown complete. Generated {count} total log entries.")

if __name__ == '__main__':
    main()
