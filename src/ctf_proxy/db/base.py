import enum
from dataclasses import dataclass


class RowStatus(enum.Enum):
    NEW = "new"
    UPDATED = "updated"


@dataclass
class TimeStatsRow:
    id: int
    port: int
    time: int
    count: int


@dataclass
class TimeStatsInsertRow:
    port: int
    time: int
    count: int


@dataclass
class TimeStatsIncrementRow:
    port: int
    time: int
    count: int
