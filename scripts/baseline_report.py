"""Per-event and per-endpoint baseline report over logs/app.log (read-only).

Phase 3 measures before caching: this prints one line per flow event and per
API endpoint from a representative dev session — call counts, failures, and
duration percentiles (p50/p95 in ms) taken from ``duration_ms``. Run it after
a session that drives the app like an employee and an HR agent, and read the
leaderboard top-down:

    python scripts/baseline_report.py [--log logs/app.log]

Caveats worth keeping in view while reading:
- Flow-instrumented operations appear in the started/done/fail columns;
  endpoints without flow events (several KB and admin reads) appear only in
  the reqs column via the RequestLogMiddleware's per-request line.
- p50/p95 are over THIS window only: a short session is a sample, not a
  benchmark. The memo compares candidates, not absolute truth.
Exits 1 when the log contains zero backend records — a baseline over an
empty window proves nothing and would look like a green result.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

_STAGE_STARTED = "_started"
_STAGE_DONE = "_completed"
_STAGE_FAILED = "_failed"


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = round(fraction * (len(ordered) - 1))
    return ordered[index]


def _tally_flow_event(record: dict, counts: dict[str, dict[str, int]]) -> None:
    """One hrdesk.flow event -> its base operation's started/completed/failed
    tally. duration_ms rides only _completed records (observability.py)."""
    event = record.get("event") or ""
    if event.endswith(_STAGE_STARTED):
        counts[event[: len(event) - len(_STAGE_STARTED)]]["started"] += 1
    elif event.endswith(_STAGE_DONE):
        counts[event[: len(event) - len(_STAGE_DONE)]]["completed"] += 1
    elif event.endswith(_STAGE_FAILED):
        counts[event[: len(event) - len(_STAGE_FAILED)]]["failed"] += 1


def _tally_request_line(
    record: dict,
    counts: dict[str, dict[str, int]],
    durations: dict[str, list[float]],
) -> None:
    """RequestLogMiddleware record: no ``event`` key, but method/path/status/
    duration_ms. Grouped under 'METHOD /path'; 4xx/5xx statuses tally into
    the failed column so unauthorized or broken traffic is visible."""
    label = f"{record.get('method')} {record.get('path')}"
    counts[label]["requests"] += 1
    if isinstance(record.get("status"), int) and record["status"] >= 400:
        counts[label]["failed"] += 1
    duration = record.get("duration_ms")
    if isinstance(duration, (int, float)):
        durations[label].append(float(duration))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default="logs/app.log", help="JSON-log file to read")
    args = parser.parse_args()
    path = Path(args.log)
    if not path.exists():
        print(f"No log file at {path} — run a live session first.")
        return 1

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    durations: dict[str, list[float]] = defaultdict(list)
    malformed = 0

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except Exception:
                malformed += 1
                continue
            if record.get("source") != "backend":
                continue
            event = record.get("event") or ""
            if event:
                _tally_flow_event(record, counts)
            elif record.get("path"):
                _tally_request_line(record, counts, durations)
            ended = event.endswith(_STAGE_DONE)
            if ended:
                base = event[: len(event) - len(_STAGE_DONE)]
                duration = record.get("duration_ms")
                if isinstance(duration, (int, float)):
                    durations[base].append(float(duration))

    if not counts:
        print(f"No backend records in {path}")
        return 1

    print(f"Baseline over {path.name} ({malformed} malformed lines skipped)")
    header = (
        f"{'operation / endpoint':44}"
        f" {'started':>7} {'done':>6} {'fail':>5} {'reqs':>5}"
        f" {'p50 ms':>8} {'p95 ms':>8} {'n':>4}"
    )
    print(header)
    print("-" * len(header))
    for base in sorted(counts):
        row = counts[base]
        values = durations.get(base, [])
        p50 = f"{_percentile(values, 0.50):.1f}" if values else "—"
        p95 = f"{_percentile(values, 0.95):.1f}" if values else "—"
        n = f"{len(values):>4}" if values else "   0"
        print(
            f"{base:44}"
            f" {row.get('started', 0):>7}"
            f" {row.get('completed', 0):>6}"
            f" {row.get('failed', 0):>5}"
            f" {row.get('requests', 0):>5}"
            f" {p50:>8}"
            f" {p95:>8}"
            f" {n:>4}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
