from .base_time_stats import BaseTimeStats


class PathStats(BaseTimeStats):
    table_name = "http_path_time_stats"
    key_columns = ["method", "path"]
