from .base_time_stats import BaseTimeStats


class QueryParamStats(BaseTimeStats):
    table_name = "http_query_param_time_stats"
    key_columns = ["param", "value"]
