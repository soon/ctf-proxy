from .base_time_stats import BaseTimeStats


class HeaderStats(BaseTimeStats):
    table_name = "http_header_time_stats"
    key_columns = ["name", "value"]
