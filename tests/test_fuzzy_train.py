"""Argument-coverage tests for fuzzy-train.

Scope: each CLI arg's behavior individually + the combinations that actually
interact (not the full cartesian product). Function-level tests import the
module; a few subprocess tests exercise main()'s bounded loop end to end.
"""
import gzip
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Union

import pytest


# ---------------------------------------------------------------------------
# Task 2: Log-content args (min/max length, time-zone, message generation)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("length", [1, 50, 90, 200, 500])
def test_message_length_preserved_faker(ft, length):
    assert len(ft.generate_random_message(length)) == length


@pytest.mark.parametrize("length", [1, 50, 90, 200, 500])
def test_message_length_preserved_fallback(ft_no_faker, length):
    assert len(ft_no_faker.generate_random_message(length)) == length


def test_validate_length_defaults(ft):
    assert ft.validate_length_params(
        ft.DEFAULT_MIN_LOG_LENGTH, ft.DEFAULT_MAX_LOG_LENGTH
    ) == (ft.DEFAULT_MIN_LOG_LENGTH, ft.DEFAULT_MAX_LOG_LENGTH)


def test_validate_length_single_min_applies_to_both(ft):
    # only min changed -> max follows min
    assert ft.validate_length_params(200, ft.DEFAULT_MAX_LOG_LENGTH) == (200, 200)


def test_validate_length_single_max_applies_to_both(ft):
    # only max changed -> min follows max
    assert ft.validate_length_params(ft.DEFAULT_MIN_LOG_LENGTH, 300) == (300, 300)


def test_validate_length_min_gt_max_exits(ft):
    # Both differ from defaults so the single-value adjust branches don't fire;
    # min(300) > max(120) must raise.
    with pytest.raises(SystemExit):
        ft.validate_length_params(300, 120)


def test_timezone_utc_has_z_suffix(ft):
    ts = ft.generate_timestamp("UTC")
    assert ts.endswith("Z")
    # parseable ISO-ish shape
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z", ts)


def test_timezone_local_has_offset(ft):
    ts = ft.generate_timestamp("local")
    assert not ts.endswith("Z")
    # ends with +HH:MM or -HH:MM
    assert re.search(r"[+-]\d{2}:\d{2}$", ts)


# ---------------------------------------------------------------------------
# Task 3: Field-control args (no-* flags, trace-id-type, field order)
# ---------------------------------------------------------------------------

def test_build_entry_all_fields_order(ft):
    e = ft.build_log_entry("TS", "INFO", "msg", "tid", True, True, True)
    assert list(e.keys()) == ["timestamp", "level", "message", "trace_id", "length"]
    assert e["length"] == len("msg")


def test_build_entry_no_timestamp(ft):
    e = ft.build_log_entry("TS", "INFO", "msg", "tid", False, True, True)
    assert "timestamp" not in e
    assert list(e.keys()) == ["level", "message", "trace_id", "length"]


def test_build_entry_no_log_level(ft):
    e = ft.build_log_entry("TS", "INFO", "msg", "tid", True, False, True)
    assert "level" not in e


def test_build_entry_no_length(ft):
    e = ft.build_log_entry("TS", "INFO", "msg", "tid", True, True, False)
    assert "length" not in e


def test_build_entry_no_trace_id(ft):
    # trace_id None => omitted
    e = ft.build_log_entry("TS", "INFO", "msg", None, True, True, True)
    assert "trace_id" not in e


def test_build_entry_message_only(ft):
    e = ft.build_log_entry("TS", "INFO", "msg", None, False, False, False)
    assert list(e.keys()) == ["message"]


def test_trace_id_pid_format(ft):
    tid = ft.generate_trace_id(True, "pid")
    # {PID}-{8-digit counter}
    assert re.match(r".+-\d{8}$", tid)


def test_trace_id_integer_format(ft):
    tid = ft.generate_trace_id(True, "integer")
    assert re.match(r"^\d{8}$", tid)


def test_trace_id_excluded(ft):
    assert ft.generate_trace_id(False, "pid") is None


def test_trace_id_counter_increments(ft):
    a = ft.generate_trace_id(True, "integer")
    b = ft.generate_trace_id(True, "integer")
    assert int(b) == int(a) + 1


# ---------------------------------------------------------------------------
# Task 4: Format args (--log-format values + default)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_entry(ft):
    return ft.build_log_entry(
        "2026-01-01T00:00:00.000000Z", "INFO", "hello world", "tid-1",
        True, True, True,
    )


def test_format_json(ft, sample_entry):
    line = ft.format_log(sample_entry, "JSON")
    parsed = json.loads(line)
    assert parsed["message"] == "hello world"


def test_format_logfmt(ft, sample_entry):
    line = ft.format_log(sample_entry, "logfmt")
    assert 'message="hello world"' in line
    assert 'level="INFO"' in line


def test_format_apache_common(ft, sample_entry):
    line = ft.format_log(sample_entry, "apache common")
    assert re.search(r'"\S+ /\S* HTTP/1\.1" \d{3} \d+', line)


def test_format_apache_combined(ft, sample_entry):
    line = ft.format_log(sample_entry, "apache combined")
    # request, referer, user-agent => 6 double quotes
    assert line.count('"') == 6


def test_format_apache_error(ft, sample_entry):
    line = ft.format_log(sample_entry, "apache error")
    assert line.startswith("[") and "hello world" in line
    assert "[core:info]" in line


@pytest.mark.parametrize("fmt", ["bsd syslog", "rfc3164"])
def test_format_bsd_syslog(ft, sample_entry, fmt):
    line = ft.format_log(sample_entry, fmt)
    assert line.startswith("<13>") and "hello world" in line


@pytest.mark.parametrize("fmt", ["syslog", "rfc5424"])
def test_format_rfc5424(ft, sample_entry, fmt):
    line = ft.format_log(sample_entry, fmt)
    assert line.startswith("<13>1 ") and "hello world" in line


def test_format_unknown_defaults_to_json(ft, sample_entry):
    line = ft.format_log(sample_entry, "totally-made-up")
    assert json.loads(line)["message"] == "hello world"


# ---------------------------------------------------------------------------
# Task 5: Output-control individual (parse_duration, OutputHandler, time-step)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("10", 10.0), ("20ms", 0.02), ("5s", 5.0), ("1m", 60.0), ("2h", 7200.0),
    ("0.5s", 0.5), ("1.5m", 90.0),
])
def test_parse_duration_valid(ft, value, expected):
    assert ft.parse_duration(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", ["abc", "10x", "", "s", "1 2"])
def test_parse_duration_invalid_exits(ft, value):
    with pytest.raises(SystemExit):
        ft.parse_duration(value)


def test_output_handler_append(ft, tmp_path):
    p = tmp_path / "a.log"
    h = ft.OutputHandler(str(p), overwrite=False)
    for i in range(3):
        h.write(f"L{i}")
    h.close()
    h2 = ft.OutputHandler(str(p), overwrite=False)
    h2.write("L3")
    h2.close()
    assert p.read_text().splitlines() == ["L0", "L1", "L2", "L3"]


def test_output_handler_overwrite(ft, tmp_path):
    p = tmp_path / "a.log"
    first = ft.OutputHandler(str(p), overwrite=False)
    first.write("old")
    first.close()
    h = ft.OutputHandler(str(p), overwrite=True)
    h.write("new")
    h.close()
    assert p.read_text().splitlines() == ["new"]


def test_output_handler_gzip_via_extension(ft, tmp_path):
    p = tmp_path / "b.log.gz"
    h = ft.OutputHandler(str(p))
    for i in range(4):
        h.write(f"G{i}")
    h.close()
    with gzip.open(str(p), "rt") as fh:
        assert fh.read().splitlines() == ["G0", "G1", "G2", "G3"]


def test_output_handler_gzip_via_flag(ft, tmp_path):
    p = tmp_path / "c.log"
    h = ft.OutputHandler(str(p), compress=True)
    h.write("X")
    h.close()
    # written as gzip even though name lacks .gz
    with gzip.open(str(p), "rt") as fh:
        assert fh.read().splitlines() == ["X"]


def test_output_handler_split_by_lines(ft, tmp_path):
    p = tmp_path / "d.log"
    h = ft.OutputHandler(str(p), split_by=5, split_unit="lines")
    for i in range(12):
        h.write(f"S{i}")
    h.close()
    parts = sorted(tmp_path.glob("d*.log"))
    assert [x.name for x in parts] == ["d.log", "d1.log", "d2.log"]
    assert len(parts[0].read_text().splitlines()) == 5
    assert len(parts[2].read_text().splitlines()) == 2


def test_output_handler_split_by_bytes(ft, tmp_path):
    p = tmp_path / "e.log"
    # each line "0123456789" + newline = 11 bytes; threshold 20 => 2 lines/part
    h = ft.OutputHandler(str(p), split_by=20, split_unit="bytes")
    for _ in range(5):
        h.write("0123456789")
    h.close()
    parts = sorted(tmp_path.glob("e*.log"))
    assert len(parts) == 3  # 2,2,1


def test_output_handler_split_gzip_name_pairing(ft, tmp_path):
    p = tmp_path / "f.log.gz"
    h = ft.OutputHandler(str(p), split_by=2, split_unit="lines")
    for i in range(5):
        h.write(f"Z{i}")
    h.close()
    parts = sorted(tmp_path.glob("f*.log.gz"))
    assert [x.name for x in parts] == ["f.log.gz", "f1.log.gz", "f2.log.gz"]


def test_time_step_timestamps_advance(ft):
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t0 = ft.generate_timestamp("UTC", base=base)
    t1 = ft.generate_timestamp("UTC", base=base + timedelta(seconds=60))
    assert t0 == "2026-01-01T00:00:00.000000Z"
    assert t1 == "2026-01-01T00:01:00.000000Z"


# ---------------------------------------------------------------------------
# Task 6: Interacting combinations that matter
# ---------------------------------------------------------------------------

def test_faker_parity_message_valid_both(ft, ft_no_faker):
    # same length request yields valid length in both modes
    assert len(ft.generate_random_message(120)) == 120
    assert len(ft_no_faker.generate_random_message(120)) == 120


def test_faker_absent_uses_builtin_literals(ft_no_faker):
    entry = {"timestamp": "2026-01-01T00:00:00", "level": "info", "message": "m"}
    common = ft_no_faker.format_apache_common_log(entry)
    combined = ft_no_faker.format_apache_combined_log(entry)
    bsd = ft_no_faker.format_bsd_syslog_log(entry)
    assert '"GET /index.html HTTP/1.1"' in common
    assert '"https://example.com/"' in combined
    assert '"Mozilla/5.0 (compatible; FakeBot/1.0)"' in combined
    assert " localhost fuzzy-train: " in bsd


def test_split_gzip_combination(ft, tmp_path):
    # compress + split via flag (name without .gz)
    p = tmp_path / "g.log"
    h = ft.OutputHandler(str(p), compress=True, split_by=2, split_unit="lines")
    for i in range(5):
        h.write(f"C{i}")
    h.close()
    parts = sorted(tmp_path.glob("g*.log"))
    assert len(parts) == 3
    # each part is valid gzip
    with gzip.open(str(parts[0]), "rt") as fh:
        assert len(fh.read().splitlines()) == 2


def test_overwrite_with_multiple_writes(ft, tmp_path):
    p = tmp_path / "h.log"
    h = ft.OutputHandler(str(p), overwrite=True)
    for i in range(3):
        h.write(f"O{i}")
    h.close()
    assert p.read_text().splitlines() == ["O0", "O1", "O2"]


# ---------------------------------------------------------------------------
# Task 7: End-to-end CLI (subprocess) — bounded runs so main() terminates
# ---------------------------------------------------------------------------

def _run(script_path: str, *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, script_path, *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _run_in_cwd(script_path: str, cwd: Union[str, Path], *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    # Run with a specific working directory so default-filename output
    # (fuzzy-train.log) lands in an isolated tmp dir.
    return subprocess.run(
        [sys.executable, script_path, *args],
        capture_output=True, text=True, timeout=timeout, cwd=str(cwd),
    )


def test_cli_version(script_path):
    r = _run(script_path, "--version")
    assert r.returncode == 0
    assert "fuzzy-train" in r.stdout


def test_cli_help_shows_output_control(script_path):
    r = _run(script_path, "--help")
    assert r.returncode == 0
    assert "Output Control" in r.stdout
    for flag in ["--count", "--max-bytes", "--overwrite", "--compress", "--split-by", "--time-step"]:
        assert flag in r.stdout


def test_cli_count_exact_lines(script_path):
    r = _run(script_path, "--count", "5", "--lines-per-second", "1000",
             "--no-timestamp", "--no-trace-id")
    assert r.returncode == 0
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert len(lines) == 5


def test_cli_count_json_valid(script_path):
    r = _run(script_path, "--count", "3", "--lines-per-second", "1000", "--no-trace-id")
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert len(lines) == 3
    for l in lines:
        json.loads(l)  # each line valid JSON


def test_cli_max_bytes_to_file(script_path, tmp_path):
    out = tmp_path / "mb.log"
    r = _run(script_path, "--max-bytes", "400", "--lines-per-second", "1000", "--file", str(out))
    assert r.returncode == 0
    assert out.stat().st_size >= 400


def test_cli_count_beats_max_bytes(script_path, tmp_path):
    # count set => max-bytes ignored => exactly 4 lines
    out = tmp_path / "cb.log"
    r = _run(script_path, "--count", "4", "--max-bytes", "999999", "--lines-per-second", "1000",
             "--file", str(out), "--no-timestamp", "--no-trace-id")
    assert r.returncode == 0
    assert len(out.read_text().splitlines()) == 4


def test_cli_gzip_file(script_path, tmp_path):
    out = tmp_path / "z.log.gz"
    r = _run(script_path, "--count", "6", "--lines-per-second", "1000", "--file", str(out))
    assert r.returncode == 0
    with gzip.open(str(out), "rt") as fh:
        assert len([l for l in fh.read().splitlines() if l.strip()]) == 6


def test_cli_split_files(script_path, tmp_path):
    out = tmp_path / "s.log"
    r = _run(script_path, "--count", "10", "--split-by", "4", "--lines-per-second", "1000",
             "--file", str(out))
    assert r.returncode == 0
    parts = sorted(tmp_path.glob("s*.log"))
    assert len(parts) == 3  # 4,4,2


def test_cli_time_step_spacing(script_path):
    r = _run(script_path, "--count", "3", "--time-step", "1m", "--time-zone", "UTC",
             "--lines-per-second", "1000", "--no-trace-id", "--no-length")
    lines = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    ts = [l["timestamp"] for l in lines]
    assert len(ts) == 3
    # minute component advances by 1 each line
    parsed = [datetime.strptime(t, "%Y-%m-%dT%H:%M:%S.%fZ") for t in ts]
    assert (parsed[1] - parsed[0]).total_seconds() == 60
    assert (parsed[2] - parsed[1]).total_seconds() == 60


@pytest.mark.parametrize("flag", ["--count", "--max-bytes", "--split-by"])
def test_cli_negative_values_exit(script_path, flag, tmp_path):
    r = _run(script_path, flag, "-5", "--file", str(tmp_path / "n.log"))
    assert r.returncode != 0


@pytest.mark.parametrize("rate", ["0", "-5"])
def test_cli_nonpositive_rate_exits(script_path, rate):
    # --lines-per-second <= 0 would divide-by-zero / misbehave; must be rejected
    r = _run(script_path, "--lines-per-second", rate, "--count", "3")
    assert r.returncode != 0
    assert "lines-per-second" in (r.stdout + r.stderr)


@pytest.mark.parametrize("short,long_equiv_args", [
    (["-f", "logfmt", "-n", "3"], ["--log-format", "logfmt", "--count", "3"]),
    (["-n", "4"], ["--count", "4"]),
])
def test_cli_short_forms_parse(script_path, short, long_equiv_args):
    # short form runs and produces the same line count as its long equivalent
    r_short = _run(script_path, *short, "--lines-per-second", "1000",
                   "--no-trace-id", "--no-timestamp")
    r_long = _run(script_path, *long_equiv_args, "--lines-per-second", "1000",
                  "--no-trace-id", "--no-timestamp")
    assert r_short.returncode == 0 and r_long.returncode == 0
    n_short = len([l for l in r_short.stdout.splitlines() if l.strip()])
    n_long = len([l for l in r_long.stdout.splitlines() if l.strip()])
    assert n_short == n_long


def test_cli_short_forms_output_control(script_path, tmp_path):
    # -n (count) -o (output) -w (overwrite) -p (split) together
    out = tmp_path / "s.log"
    r = _run(script_path, "-n", "10", "-o", "file", "-w", "-p", "4",
             "--file", str(out), "--lines-per-second", "1000")
    assert r.returncode == 0
    parts = sorted(tmp_path.glob("s*.log"))
    assert len(parts) == 3  # 4,4,2


def test_cli_overwrite_truncates(script_path, tmp_path):
    out = tmp_path / "ow.log"
    _run(script_path, "--count", "5", "--lines-per-second", "1000", "--file", str(out))
    _run(script_path, "--count", "1", "--lines-per-second", "1000", "--file", str(out),
         "--overwrite", "--no-timestamp", "--no-trace-id")
    assert len(out.read_text().splitlines()) == 1


def test_cli_compress_auto_enables_file(script_path, tmp_path):
    # --compress alone (no --output file) implies file output, warns on stderr,
    # and writes gzip to the default filename in the cwd.
    r = _run_in_cwd(script_path, tmp_path, "--compress", "--count", "3",
                    "--lines-per-second", "1000")
    assert r.returncode == 0
    assert "imply file output" in r.stderr
    out = tmp_path / "fuzzy-train.log"
    assert out.exists()
    with gzip.open(str(out), "rt") as fh:
        assert len([l for l in fh.read().splitlines() if l.strip()]) == 3


def test_cli_overwrite_alone_enables_file(script_path, tmp_path):
    # --overwrite alone (no --output file) implies file output.
    r = _run_in_cwd(script_path, tmp_path, "--overwrite", "--count", "2",
                    "--lines-per-second", "1000", "--no-timestamp", "--no-trace-id")
    assert r.returncode == 0
    out = tmp_path / "fuzzy-train.log"
    assert out.exists()
    assert len(out.read_text().splitlines()) == 2


def test_cli_count_zero_streams_then_interrupt(script_path):
    # --count 0 means infinite streaming (today's default); it must NOT exit on
    # its own. Confirm it keeps running until we time out, then produced output.
    proc = subprocess.Popen(
        [sys.executable, script_path, "--count", "0", "--lines-per-second", "1000",
         "--no-timestamp", "--no-trace-id"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        try:
            proc.wait(timeout=2)
            raise AssertionError("--count 0 should stream forever, but the process exited")
        except subprocess.TimeoutExpired:
            proc.terminate()
            out, _ = proc.communicate(timeout=5)
            assert len([l for l in out.splitlines() if l.strip()]) > 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
