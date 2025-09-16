from ctf_proxy.config import Service
from ctf_proxy.db import ProxyStatsDB

from .base_stats_screen import BaseStatsScreen
from .query_param_stats import QueryParamStats


class QueryParamStatsScreen(BaseStatsScreen):
    stats_type_name = "Query params"

    def __init__(self, db: ProxyStatsDB, service: Service):
        super().__init__(db, service)
        self.query_param_stats = QueryParamStats(db)

    def get_stats_instance(self):
        return self.query_param_stats

    def get_ignored_config(self) -> dict[str, str]:
        return self.service.ignore_query_param_stats

    def format_key_display(self, key: tuple) -> tuple[str, str]:
        param, value = key
        return param, value
