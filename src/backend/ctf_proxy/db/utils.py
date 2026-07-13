import datetime
import json


def parse_headers(text: str | None) -> list[tuple[str, str]]:
    """Parse the request_headers/response_headers json column into (name, value) pairs."""
    if not text:
        return []
    return [(name, value) for name, value in json.loads(text)]


def convert_datetime_to_timestamp(dt: datetime.datetime) -> int:
    return int(dt.timestamp() * 1000)


def now_timestamp() -> int:
    return convert_datetime_to_timestamp(datetime.datetime.now())


def convert_timestamp_to_datetime(ts: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.UTC)
