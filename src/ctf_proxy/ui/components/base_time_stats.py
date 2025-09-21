from datetime import datetime

from ctf_proxy.db import ProxyStatsDB
from ctf_proxy.db.utils import convert_datetime_to_timestamp


class BaseTimeStats:
    table_name: str = None
    key_columns: list[str] = None

    def __init__(self, db: ProxyStatsDB):
        self.db = db

    def get_time_series_with_totals(
        self, port: int, window_minutes: int = 60
    ) -> dict[tuple[str, ...], dict]:
        """Get time series data for all key combinations on a specific port for the specified time window with 1-minute precision, including totals."""
        with self.db.connect() as conn:
            cursor = conn.cursor()

            # Get current time
            now = datetime.now()

            # Convert to timestamps (milliseconds) and truncate to minute boundaries
            now_ms = convert_datetime_to_timestamp(now)
            now_truncated = (now_ms // 60000) * 60000  # Truncate current time to minute

            # Calculate window start from the current truncated minute
            window_start_truncated = now_truncated - (
                (window_minutes - 1) * 60000
            )  # N minutes ago to include current minute

            # Create time buckets (1 minute each) for the window including current minute
            time_buckets = []
            for i in range(window_minutes):
                bucket_time_ms = window_start_truncated + (i * 60000)  # Add i minutes
                time_buckets.append(bucket_time_ms)

            # Build query dynamically based on key columns
            key_columns_str = ", ".join(self.key_columns)
            query = f"""
                SELECT {key_columns_str}, time, count
                FROM {self.table_name}
                WHERE port = ? AND time >= ?
                ORDER BY {key_columns_str}, time
            """

            cursor.execute(query, [port, window_start_truncated])

            # Collect all key combinations and their data
            result = {}
            for row in cursor.fetchall():
                # Extract key values (all columns except time and count)
                key_values = row[:-2]
                time_val = row[-2]
                count = row[-1]

                key = tuple(key_values)
                if key not in result:
                    bucket_data = dict.fromkeys(time_buckets, 0)
                    result[key] = {"time_series": bucket_data, "total_count": 0}

                # Add to total count
                result[key]["total_count"] += count

                # Truncate timestamp to minute boundary and use as bucket
                truncated_time = (time_val // 60000) * 60000
                if truncated_time in result[key]["time_series"]:
                    result[key]["time_series"][truncated_time] += count

            # Convert time series to lists in chronological order and sort by total count first, then by recency
            sorted_results = {}

            # Pre-calculate most recent activity timestamp for each entry
            most_recent_activity = {}
            for key in result.keys():
                max_time = 0
                for bucket_time, count in result[key]["time_series"].items():
                    if count > 0 and bucket_time > max_time:
                        max_time = bucket_time
                most_recent_activity[key] = max_time

            # Sort by total count (descending), then by most recent activity (descending)
            sorted_keys = sorted(
                result.keys(),
                key=lambda k: (result[k]["total_count"], most_recent_activity[k]),
                reverse=True,
            )

            for key in sorted_keys:
                # Create timestamp-count pairs, excluding zeros
                time_series_list = []
                for bucket_time in time_buckets:
                    count = result[key]["time_series"][bucket_time]
                    if count > 0:  # Only include non-zero counts
                        time_series_list.append({"timestamp": bucket_time, "count": count})

                sorted_results[key] = {
                    "time_series": time_series_list,
                    "total_count": result[key]["total_count"],
                }

            return sorted_results

    def get_time_series_for_range(
        self, port: int, start_time: datetime, end_time: datetime
    ) -> dict[tuple[str, ...], dict]:
        """Get time series data for a specific time range."""
        with self.db.connect() as conn:
            cursor = conn.cursor()

            # Convert to timestamps (milliseconds)
            start_ms = convert_datetime_to_timestamp(start_time)
            end_ms = convert_datetime_to_timestamp(end_time)

            # Build query
            key_columns_str = ", ".join(self.key_columns)
            query = f"""
                SELECT {key_columns_str}, time, count
                FROM {self.table_name}
                WHERE port = ? AND time >= ? AND time < ?
                ORDER BY {key_columns_str}, time
            """

            cursor.execute(query, [port, start_ms, end_ms])

            # Collect all key combinations and their data
            result = {}
            for row in cursor.fetchall():
                # Extract key values
                key_values = row[:-2]
                time_val = row[-2]
                count = row[-1]

                key = tuple(key_values)
                if key not in result:
                    result[key] = {"time_series": [], "total_count": 0}

                # Add to time series and total
                result[key]["time_series"].append({"timestamp": time_val, "count": count})
                result[key]["total_count"] += count

            # Sort by total count
            sorted_results = {}
            sorted_keys = sorted(
                result.keys(),
                key=lambda k: result[k]["total_count"],
                reverse=True,
            )

            for key in sorted_keys:
                sorted_results[key] = result[key]

            return sorted_results
