from ctf_proxy.config import Service
from ctf_proxy.db import ProxyStatsDB

from .base_stats_screen import BaseStatsScreen
from .header_stats import HeaderStats


class HeaderStatsScreen(BaseStatsScreen):
    stats_type_name = "Headers"

    def __init__(self, db: ProxyStatsDB, service: Service):
        super().__init__(db, service)
        self.header_stats = HeaderStats(db)

    def get_stats_instance(self):
        return self.header_stats

    def get_ignored_config(self) -> dict[str, str]:
        return self.service.ignore_header_stats

    def format_key_display(self, key: tuple) -> tuple[str, str]:
        name, value = key
        return name, value
