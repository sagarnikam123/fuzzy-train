#!/usr/bin/env python3

import argparse
import random
import time
import string
import os
import json
from datetime import datetime, timezone

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

TRACE_ID_COUNTER = 1
PID = os.getpid()

def generate_random_message(length):
    message = ""
    while len(message) < length:
        sentence = random.choice(SENTENCES)
        if random.random() < 0.3:
            detail = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(10, 30)))
            sentence += f" Details: {detail}"
        message += sentence + " "
    return message[:length]

def generate_timestamp(time_zone):
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

def generate_trace_id(pid):
    global TRACE_ID_COUNTER
    if pid:
        trace_id = f"{pid}-{TRACE_ID_COUNTER:08d}"
    else:
        trace_id = f"{TRACE_ID_COUNTER:08d}"
    TRACE_ID_COUNTER += 1
    return trace_id

def format_log(entry, log_format):
    # Supported formats: logfmt, JSON, Apache common, Apache combined, Apache error,
    # BSD syslog (rfc3164), Syslog (rfc5424)
    if log_format.lower() == "json":
        return json.dumps(entry)
    elif log_format.lower() == "logfmt":
        # logfmt: key1="value1" key2="value2" ...
        return ' '.join(f'{k}="{str(v).replace("\"", "\\\"")}"' for k, v in entry.items())
    elif log_format.lower() == "apache common":
        # Common Log Format: "%h %l %u %t \"%r\" %>s %b"
        # We'll fake these fields
        host = "127.0.0.1"
        ident = "-"
        user = "-"
        dt = datetime.strptime(entry['timestamp'][:19], "%Y-%m-%dT%H:%M:%S")
        tstr = dt.strftime("[%d/%b/%Y:%H:%M:%S +0000]")
        request = "GET /index.html HTTP/1.1"
        status = random.choice([200, 404, 500, 302])
        size = len(entry['message'])
        return f'{host} {ident} {user} {tstr} "{request}" {status} {size}'
    elif log_format.lower() == "apache combined":
        # Combined Log Format: Common + "Referer" "User-Agent"
        host = "127.0.0.1"
        ident = "-"
        user = "-"
        dt = datetime.strptime(entry['timestamp'][:19], "%Y-%m-%dT%H:%M:%S")
        tstr = dt.strftime("[%d/%b/%Y:%H:%M:%S +0000]")
        request = "GET /index.html HTTP/1.1"
        status = random.choice([200, 404, 500, 302])
        size = len(entry['message'])
        referer = "https://example.com/"
        ua = "Mozilla/5.0 (compatible; FakeBot/1.0)"
        return f'{host} {ident} {user} {tstr} "{request}" {status} {size} "{referer}" "{ua}"'
    elif log_format.lower() == "apache error":
        # [Wed Oct 11 14:32:52.123456 2023] [core:error] [pid 12345] [client 127.0.0.1:12345] message
        dt = datetime.strptime(entry['timestamp'][:19], "%Y-%m-%dT%H:%M:%S")
        tstr = dt.strftime("%a %b %d %H:%M:%S.%f %Y")
        pid = random.randint(1000, 99999)
        client = f"127.0.0.1:{random.randint(1000, 65535)}"
        return f'[{tstr}] [core:{entry["level"].lower()}] [pid {pid}] [client {client}] {entry["message"]}'
    elif log_format.lower() == "bsd syslog" or log_format.lower() == "rfc3164":
        # <PRI>MMM dd HH:mm:ss HOST TAG: message
        dt = datetime.strptime(entry['timestamp'][:19], "%Y-%m-%dT%H:%M:%S")
        tstr = dt.strftime("%b %d %H:%M:%S")
        host = "localhost"
        tag = "fake-app"
        pri = "<13>"  # user.notice
        return f'{pri}{tstr} {host} {tag}: {entry["message"]}'
    elif log_format.lower() == "syslog" or log_format.lower() == "rfc5424":
        # <PRI>1 YYYY-MM-DDTHH:MM:SS.sssZ HOST APP PROCID MSGID - message
        dt = datetime.strptime(entry['timestamp'][:19], "%Y-%m-%dT%H:%M:%S")
        tstr = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        host = "localhost"
        app = "fake-app"
        proc_id = str(os.getpid())
        msg_id = "ID1"
        pri = "<13>"  # user.notice
        return f'{pri}1 {tstr} {host} {app} {proc_id} {msg_id} - {entry["message"]}'
    else:
        # Default to JSON
        return json.dumps(entry)

def ensure_file_path(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def write_log(line, file_path):
    ensure_file_path(file_path)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def parse_args():
    parser = argparse.ArgumentParser(description="Fake Log Generator with format and output options.")
    parser.add_argument("--min_log_length", type=int, default=90,
                        help="Minimum log message length (default: 90)")
    parser.add_argument("--max_log_length", type=int, default=100,
                        help="Maximum log message length (default: 100)")
    parser.add_argument("--lines_per_second", type=float, default=1,
                        help="Log lines per second (default: 1)")
    parser.add_argument("--pid", type=str, default="true",
                        choices=["true", "True", "false", "False", "yes", "Yes", "no", "No"],
                        help="PID (process id to include in trace_id) (default: true)")
    parser.add_argument("--time_zone", type=str, default="local",
                        choices=["local", "UTC", "utc", "LOCAL"],
                        help="Time zone for timestamps (default: local)")
    parser.add_argument("--log_format", type=str, default="JSON",
                        help="Log format: logfmt, JSON, Apache common, Apache combined, "
                             "Apache error, BSD syslog (rfc3164), Syslog (rfc5424) (default: JSON)")
    parser.add_argument("--output", type=str, default="stdout",
                        help="Output: stdout or file (default: stdout)")
    parser.add_argument("--file", type=str,
                        help="File path for log output (if output=file)")
    return parser.parse_args()

def main():
    args = parse_args()
    min_len = args.min_log_length
    max_len = args.max_log_length
    lps = args.lines_per_second
    pid = PID if args.pid.lower() in ["true", "yes"] else ""
    tz = args.time_zone
    log_format = args.log_format
    output = args.output.lower()
    file_path = args.file

    # Output logic
    to_stdout = (output == "stdout") or (not output and not file_path)
    to_file = (output == "file") or (file_path is not None)
    if to_file and not file_path:
        file_path = "fake.log"

    try:
        while True:
            log_level = random.choice(LOG_LEVELS)
            trace_id = generate_trace_id(pid)
            message_length = random.randint(min_len, max_len)
            message = generate_random_message(message_length)
            timestamp = generate_timestamp(tz)
            log_entry = {
                "timestamp": timestamp,
                "level": log_level,
                "trace_id": trace_id,
                "message": message,
                "length": len(message)
            }
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
