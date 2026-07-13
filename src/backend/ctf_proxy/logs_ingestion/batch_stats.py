from psycopg import Cursor

UPSERT_CHUNK_SIZE = 1000

SERVICE_SUM_COLS = [
    "total_requests",
    "total_blocked_requests",
    "total_responses",
    "total_blocked_responses",
    "total_flags_written",
    "total_flags_retrieved",
    "total_flags_blocked",
    "total_websocket_connections",
    "total_websocket_frames",
]


def bulk_upsert(
    tx: Cursor,
    table: str,
    key_cols: list[str],
    sum_cols: list[str],
    buffer: dict[tuple, list[int]],
) -> None:
    if not buffer:
        return

    cols = key_cols + sum_cols
    row_placeholder = "(" + ",".join(["%s"] * len(cols)) + ")"
    set_clause = ", ".join(f"{c} = {table}.{c} + EXCLUDED.{c}" for c in sum_cols)
    conflict = ", ".join(key_cols)

    rows = list(buffer.items())
    for start in range(0, len(rows), UPSERT_CHUNK_SIZE):
        chunk = rows[start : start + UPSERT_CHUNK_SIZE]
        values = ", ".join([row_placeholder] * len(chunk))
        params: list = []
        for key, sums in chunk:
            params.extend(key)
            params.extend(sums)
        tx.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES {values} "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}",
            params,
        )


class BatchStats:
    def __init__(self):
        self.service_stats: dict[tuple, list[int]] = {}
        self.response_code_stats: dict[tuple, list[int]] = {}
        self.request_time_stats: dict[tuple, list[int]] = {}
        self.path_time_stats: dict[tuple, list[int]] = {}
        self.query_param_time_stats: dict[tuple, list[int]] = {}
        self.header_time_stats: dict[tuple, list[int]] = {}
        self.flag_time_stats: dict[tuple, list[int]] = {}

    @staticmethod
    def accumulate(buffer: dict[tuple, list[int]], key: tuple, values: tuple[int, ...]) -> None:
        current = buffer.get(key)
        if current is None:
            buffer[key] = list(values)
        else:
            for i, value in enumerate(values):
                current[i] += value

    def add_service(
        self,
        port: int,
        total_requests: int = 0,
        total_blocked_requests: int = 0,
        total_responses: int = 0,
        total_blocked_responses: int = 0,
        total_flags_written: int = 0,
        total_flags_retrieved: int = 0,
        total_flags_blocked: int = 0,
        total_websocket_connections: int = 0,
        total_websocket_frames: int = 0,
    ) -> None:
        self.accumulate(
            self.service_stats,
            (port,),
            (
                total_requests,
                total_blocked_requests,
                total_responses,
                total_blocked_responses,
                total_flags_written,
                total_flags_retrieved,
                total_flags_blocked,
                total_websocket_connections,
                total_websocket_frames,
            ),
        )

    def add_response_code(self, port: int, status_code: int, count: int = 1) -> None:
        self.accumulate(self.response_code_stats, (port, status_code), (count,))

    def add_request_time(
        self, port: int, time: int, count: int = 1, blocked_count: int = 0
    ) -> None:
        self.accumulate(self.request_time_stats, (port, time), (count, blocked_count))

    def add_path_time(self, port: int, method: str, path: str, time: int, count: int = 1) -> None:
        self.accumulate(self.path_time_stats, (port, method, path, time), (count,))

    def add_query_param_time(
        self, port: int, param: str, value: str, time: int, count: int = 1
    ) -> None:
        self.accumulate(self.query_param_time_stats, (port, param, value, time), (count,))

    def add_header_time(self, port: int, name: str, value: str, time: int, count: int = 1) -> None:
        self.accumulate(self.header_time_stats, (port, name, value, time), (count,))

    def add_flag_time(
        self, port: int, time: int, write_count: int = 0, read_count: int = 0
    ) -> None:
        self.accumulate(self.flag_time_stats, (port, time), (write_count, read_count))

    def flush(self, tx: Cursor) -> None:
        bulk_upsert(tx, "service_stats", ["port"], SERVICE_SUM_COLS, self.service_stats)
        bulk_upsert(
            tx, "http_response_code_stats", ["port", "status_code"], ["count"],
            self.response_code_stats,
        )
        bulk_upsert(
            tx, "http_request_time_stats", ["port", "time"], ["count", "blocked_count"],
            self.request_time_stats,
        )
        bulk_upsert(
            tx, "http_path_time_stats", ["port", "method", "path", "time"], ["count"],
            self.path_time_stats,
        )
        bulk_upsert(
            tx, "http_query_param_time_stats", ["port", "param", "value", "time"], ["count"],
            self.query_param_time_stats,
        )
        bulk_upsert(
            tx, "http_header_time_stats", ["port", "name", "value", "time"], ["count"],
            self.header_time_stats,
        )
        bulk_upsert(
            tx, "flag_time_stats", ["port", "time"], ["write_count", "read_count"],
            self.flag_time_stats,
        )
