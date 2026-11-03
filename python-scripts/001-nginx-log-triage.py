#!/usr/bin/env python3
from __future__ import annotations

# standard library module is used to build user-friendly command-line interfaces (CLIs).
# CLF / Common Log File is a standardized text file format used by 
# web servers to record client requests.
import argparse


import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Tuple

# running it gives:
# {'Jan': 1, 'Feb': 2, 'Mar': 3, ... 
#  ... 'Oct': 10, 'Nov': 11, 'Dec': 12}
# enumerate(iterable, start=1)
MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ),
        start=1,
    )
}

# ^ means line must begin here 
# (?P<client>) defines named capturing group
# \S+ means one or more non-whitespace characters
# \s means single whitespace character
# backward slash (\) for special characters and in-built like \s
# [^\]]+ ; [ ] is character class and ^ inside character class is negation
# basically [^\]]+ includes any character except \] which is ]
# \d matches any digit
LINE_RE = re.compile(
    r"^(?P<client>\S+)\s+\S+\s+\S+\s+"
    r"\[(?P<timestamp>[^\]]+)\]\s+"
    r'"(?P<request>[^"]*)"\s+'
    r"(?P<status>\d{3})\s+"
    r"(?P<bytes>\S+)"
)

# [A-Z][a-z]{2} means one character followed by two more
TIMESTAMP_RE = re.compile(
    r"(?P<day>\d{2})/(?P<month>[A-Z][a-z]{2})/(?P<year>\d{4}):"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) "
    r"(?P<sign>[+-])(?P<off_hour>\d{2})(?P<off_minute>\d{2})"
)

CLASS_KEYS = ("2xx", "3xx", "4xx", "5xx")

# input type for --top arg
def positive_int(raw: str) -> int:
    try:
        value = int(raw, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {raw!r}")
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarise a Common Log Format access log."
    )

    # --help would display: --log PATH
    parser.add_argument("--log", required=True, metavar="PATH", help="access log to read")
    parser.add_argument(
        "--top",
        type=positive_int,
        default=5,
        metavar="N",
        help="maximum entries per top list (default: 5)",
    )
    parser.add_argument(
        "--since",
        type=parse_since,
        default=None,
        metavar="ISO8601",
        help="only count valid entries at or after this instant"
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    return parser

def parse_since(raw: str) -> datetime:
    text = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected an ISO-8601 timestamp, got {raw!r}"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return value

# format: [10/Oct/2024:13:55:36 +0000]
def parse_log_timestamp(raw: str) -> datetime | None:

    # format: re.match(string)
    match = TIMESTAMP_RE.match(raw)
    if match is None:
        return None
    month = MONTHS.get(match["month"])
    if month is None:
        return None
    try:
        # datetime.timedelta object holds the log line's UTC offset 
        # as a duration
        delta = timedelta(
            hours=int(match["off_hour"]),
            minutes=int(match["off_minute"])
        )
        if match["sign"] == "-":
            delta = -delta
        offset = timezone(delta)
        return datetime(
            int(match["year"]),
            month,
            int(match["day"]),
            int(match["hour"]),
            int(match["minute"]),
            int(match["second"]),
            tzinfo=offset,
        )
    except ValueError:
        return None

# 
# def parse_since(raw: str) -> datetime:
#     text = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw 

def top_entries(counter: Counter, limit: int) -> List[Tuple[str, int]]:
    # count descending, then key ascending for deterministic ties
    # turns counter into a list of (key, count) pairs ordered by count desc
    # counter.items() returns (key, count) tuple
    # sorted(iterable, key=...)
    # sorted returns new list ascending by default
    # key= is a one-argument lambda function; item is (key, count)
    # -item[1] is negated count & item[0] is key ; sorted compares tuple
    # lexicographically: first elements decide, only on equality does it look at second
    # effective take: larger count first, because the count was negated
    # among equal counts, smaller key first, because keys are compared normally
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]


def render_text(
        total: int,
        malformed: int, 
        classes: Counter,
        error_clients: Iterable[Tuple[str, int]],
        paths: Iterable[Tuple[str, int]]
) -> str:
    lines = [
        f"Total requests: {total}"
        f"Malformed lines: {malformed}",
        "Status classes: " + " ".join(f"{key}={classes.get(key, 0)}" for key in CLASS_KEYS),
        "Top error clients:",
    ]
    client_rows = list(error_clients)

    # line.extends extends given sentence onto lines[]
    # list[].extend()
    if client_rows:
        lines.extend(f" {client} {count}" for client, count in client_rows)
    else:
        lines.extend(f" (none)")

    # list.append()
    lines.append("Top request paths:")
    path_rows = list(paths)
    if path_rows:
        lines.extend(f" {target} {count}" for target, count in path_rows)
    else:
        lines.append(" (none)")

    # join(): to join strings at each newline with begin &/ end newline
    return "\n".join(lines) + "\n"





# argc & argv: conventional parameter names of main in C
# example: int main(int argc, char *argv[])
def main(argv: List[str] | None = None) -> int:
    # build_parser(): func that create argparse.ArgumentParser and register option
    # parser asked to read command-line arguments
    args = build_parser().parse_args(argv)

    total = 0
    malformed = 0

    # annotate as Counter and assign it a Counter() object
    classes: Counter = Counter()
    error_clients: Counter = Counter()
    paths: Counter = Counter()


    # open arg.log in read mode
    try:
        handle = open(args.log, "r", encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"error: cannot open {args.log!r}: {exc}", file=sys.stderr)

    try:
        with handle:
            for raw_line in handle:
                line = raw_line.rstrip("\n")
                # a line is malformed if it is empty or whitespace-only
                # in python, "" is falsy
                if not line.strip():
                    malformed += 1
                    continue

                match = LINE_RE.match(line)
                if match is None:
                    malformed += 1
                    continue
                
                # parse_log_timestamp(): func that calculates timestamp
                timestamp = parse_log_timestamp(match["timestamp"])
                if timestamp is None:
                    malformed += 1
                    continue

                status = int(match["status"])
                if status < 100 or status > 599:
                    malformed += 1
                    continue

                request_parts = match["request"].split()
                if len(request_parts) != 3:
                    malformed += 1
                    continue
                
                # --since accepts ISO8601 that includes UTC offset
                # 2024-10-10T12:15:00+02:00 where + is sign, 02 is offset hour
                if args.since is not None and timestamp < args.since:
                    continue

                target = request_parts[1]
                total += 1
                bucket = f"{status // 100}xx"

                # dict is another alternative to Counter() here
                # dict gives key error on not finding
                # Counter() return 0 on not finding the key
                if bucket in CLASS_KEYS:
                    classes[bucket] += 1
                if status >= 500:
                    error_clients[match["client"]] += 1
                paths[target] += 1
    except OSError as exc:
        print(f"error: cannot read {args.log!r}: {exc}", file=sys.stderr)
        return 1

    # top_entries(): show top entries as per args.top
    top_clients = top_entries(error_clients, args.top)
    top_paths = top_entries(paths, args.top)

    if args.format == "json":
        output = render_json(total, amlformed, classes, top_clients, top_paths)
    else:
        output = render_text(total, malformed, classes, top_clients, top_paths)

    try:
        sys.stdout.write(output)
        sys.stdout.flush()
    except BrokenPipeError:
        return 0
    return 0

# main
if __name__ == "__main__":
    sys.exit(main())
