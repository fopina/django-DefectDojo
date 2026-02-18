#!/usr/bin/env python3

import argparse
import json
import logging
import re
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from operator import itemgetter
from pathlib import Path
from time import perf_counter
from typing import Any

DATETIME_FIELD_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T"
    r"(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,6}))?Z$",
)
DATE_FIELD_PATTERN = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})$")
logger = logging.getLogger(__name__)


def parse_utc_timestamp(value: str) -> tuple[datetime, re.Pattern[str], int] | None:
    match = DATETIME_FIELD_PATTERN.match(value)
    if match:
        fraction = match.group("fraction") or ""
        padded_fraction = (fraction + "000000")[:6]
        timestamp = f"{match.group('date')}T{match.group('time')}.{padded_fraction}+00:00"
        parsed = datetime.fromisoformat(timestamp)
        return parsed, DATETIME_FIELD_PATTERN, len(fraction)

    date_only_match = DATE_FIELD_PATTERN.match(value)
    if date_only_match:
        parsed = datetime.fromisoformat(f"{date_only_match.group('date')}T00:00:00+00:00")
        return parsed, DATE_FIELD_PATTERN, 0

    return None


def format_utc_timestamp(value: datetime, value_type: re.Pattern[str], fraction_len: int) -> str:
    value = value.astimezone(UTC)
    if value_type is DATE_FIELD_PATTERN:
        return value.date().isoformat()

    base = value.strftime("%Y-%m-%dT%H:%M:%S")
    if fraction_len > 0:
        micro = f"{value.microsecond:06d}"[:fraction_len]
        return f"{base}.{micro}Z"
    return f"{base}Z"


def iter_string_nodes(value: Any) -> Generator[tuple[dict[str, Any] | list[Any], str | int, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str):
                yield value, key, item
            else:
                yield from iter_string_nodes(item)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            if isinstance(item, str):
                yield value, idx, item
            else:
                yield from iter_string_nodes(item)


def parse_target_latest_time(value: str) -> datetime:
    parsed = parse_utc_timestamp(value)
    if not parsed:
        msg = "Invalid --latest-time. Expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS(.fraction)Z."
        raise argparse.ArgumentTypeError(msg)
    dt, _, _ = parsed
    return dt


class FixtureUpdater:
    def __init__(self, fixture_path: Path, output_path: Path, target_latest_dt: datetime | None = None) -> None:
        self.fixture_path = fixture_path
        self.output_path = output_path
        self.target_latest_dt = target_latest_dt
        self.data: list[dict[str, Any]] = []
        self.found_dates: list[tuple[dict[str, Any] | list[Any], str | int, datetime, re.Pattern[str], int]] = []
        self.latest_dt: datetime | None = None
        self.latest_type: re.Pattern[str] | None = None
        self.latest_fraction_len = 0
        self.delta: timedelta | None = None
        self.updated_count = 0
        self.elapsed_ms = 0

    def load_fixture(self) -> None:
        data = json.loads(self.fixture_path.read_text())
        if not isinstance(data, list):
            msg = "Fixture JSON must be an array at the top level."
            raise TypeError(msg)
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                msg = f"Fixture item at index {idx} is not an object."
                raise TypeError(msg)
            fields = item.get("fields")
            if not isinstance(fields, dict):
                msg = f'Fixture item at index {idx} is missing a valid "fields" object.'
                raise TypeError(msg)
        self.data = data

    def collect_dates(self) -> None:
        for obj in self.data:
            for container, key, item in iter_string_nodes(obj["fields"]):
                parsed = parse_utc_timestamp(item)
                if parsed:
                    self.found_dates.append((container, key, *parsed))

    def compute_shift(self) -> None:
        _, _, self.latest_dt, self.latest_type, self.latest_fraction_len = max(self.found_dates, key=itemgetter(2))
        target = self.target_latest_dt or datetime.now(UTC)
        self.delta = target - self.latest_dt

    def apply_shift(self) -> int:
        if self.delta is None:
            msg = "Cannot apply shift before computing delta."
            raise RuntimeError(msg)
        for container, key, dt, value_type, fraction_len in self.found_dates:
            shifted = dt + self.delta
            container[key] = format_utc_timestamp(shifted, value_type, fraction_len)
        return len(self.found_dates)

    def write_output(self) -> None:
        self.output_path.write_text(json.dumps(self.data, indent=2))

    def run(self) -> None:
        started_at = perf_counter()
        self.load_fixture()
        self.collect_dates()
        if not self.found_dates:
            self.elapsed_ms = int((perf_counter() - started_at) * 1000)
            return

        self.compute_shift()
        self.updated_count = self.apply_shift()
        self.write_output()
        self.elapsed_ms = int((perf_counter() - started_at) * 1000)

    def report(self) -> None:
        if self.latest_dt is None or self.latest_type is None or self.delta is None:
            logger.info("No matching UTC date strings found. No changes made.")
            logger.info("Completed in %dms!", self.elapsed_ms)
            return

        logger.info("Dates moved up by %.1f days", self.delta.total_seconds() / 86400)
        logger.info("Updated %d date value(s).", self.updated_count)
        logger.info(
            "Most recent original timestamp: %s",
            format_utc_timestamp(self.latest_dt, self.latest_type, self.latest_fraction_len),
        )
        logger.info(
            "New most recent timestamp:      %s",
            format_utc_timestamp(self.latest_dt + self.delta, self.latest_type, self.latest_fraction_len),
        )
        logger.info("Wrote updated fixture to:       %s", self.output_path)
        logger.info("Completed in %dms!", self.elapsed_ms)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description=(
            "Shift date values under each fixture object's 'fields' (supports "
            "YYYY-MM-DDTHH:MM:SS(.fraction)Z and YYYY-MM-DD) so the most recent "
            "detected value becomes the current UTC datetime."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("fixture_file", type=Path, help="Path to a Django fixture JSON file")
    parser.add_argument(
        "-o",
        "--output-file",
        default="output.json",
        type=Path,
        help="Path to output JSON file",
    )
    parser.add_argument(
        "--latest-time",
        type=parse_target_latest_time,
        help="Custom UTC target for the most recent fixture timestamp",
    )
    args = parser.parse_args()
    updater = FixtureUpdater(args.fixture_file, args.output_file, args.latest_time)
    updater.run()
    updater.report()


if __name__ == "__main__":
    main()
