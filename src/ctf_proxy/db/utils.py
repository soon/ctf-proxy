import datetime


def convert_datetime_to_timestamp(dt: datetime.datetime) -> int:
    return int(dt.timestamp() * 1000)


def now_timestamp() -> int:
    return convert_datetime_to_timestamp(datetime.datetime.now())


def convert_timestamp_to_datetime(ts: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(ts / 1000)
