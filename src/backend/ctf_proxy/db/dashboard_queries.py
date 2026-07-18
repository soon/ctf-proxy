from psycopg import Connection, Cursor

from ctf_proxy.db.utils import parse_headers


class DashboardQueries:
    def tag_filter_clause(
        self, source: str, port: int, tag: str, outer_column: str
    ) -> tuple[str, list]:
        table = "http_analysis_result" if source == "http" else "tcp_analysis_result"
        ref_column = "http_request_id" if source == "http" else "tcp_connection_id"
        clause = (
            f" AND {outer_column} IN ("
            f"SELECT {ref_column} FROM analytics.{table} WHERE tag = %s AND port = %s)"
        )
        return clause, [tag, port]

    def build_tcp_search_filter(self, search: str) -> tuple[str, list]:
        return (
            " AND id IN (SELECT connection_id FROM tcp_event WHERE data_text ILIKE %s)",
            [f"%{search}%"],
        )

    def service_stats_by_ports(self, cursor: Cursor, ports: list[int]) -> list:
        placeholders = ",".join(["%s"] * len(ports))
        cursor.execute(
            f"""SELECT port, total_requests, total_blocked_requests, total_responses, total_blocked_responses,
                      total_flags_written, total_flags_retrieved, total_flags_blocked
               FROM service_stats WHERE port IN ({placeholders})""",
            ports,
        )
        return cursor.fetchall()

    def response_code_stats_by_ports(self, cursor: Cursor, ports: list[int]) -> list:
        placeholders = ",".join(["%s"] * len(ports))
        cursor.execute(
            f"""SELECT port, status_code, count
               FROM http_response_code_stats
               WHERE port IN ({placeholders})
               ORDER BY port, count DESC""",
            ports,
        )
        return cursor.fetchall()

    def request_count_deltas(self, cursor: Cursor, ports: list[int], since: int) -> list:
        placeholders = ",".join(["%s"] * len(ports))
        cursor.execute(
            f"""SELECT port, SUM(count) as recent_count
               FROM http_request_time_stats
               WHERE port IN ({placeholders})
                 AND time >= %s
               GROUP BY port""",
            ports + [since],
        )
        return cursor.fetchall()

    def blocked_request_count_deltas(self, cursor: Cursor, ports: list[int], since: int) -> list:
        placeholders = ",".join(["%s"] * len(ports))
        cursor.execute(
            f"""SELECT port, SUM(blocked_count) as recent_blocked_count
               FROM http_request_time_stats
               WHERE port IN ({placeholders})
                 AND time >= %s
               GROUP BY port""",
            ports + [since],
        )
        return cursor.fetchall()

    def flag_deltas_by_ports(self, cursor: Cursor, ports: list[int], since: int) -> list:
        placeholders = ",".join(["%s"] * len(ports))
        cursor.execute(
            f"""SELECT port,
                       SUM(write_count) as flags_written_delta,
                       SUM(read_count) as flags_retrieved_delta
               FROM flag_time_stats
               WHERE port IN ({placeholders})
                 AND time >= %s
               GROUP BY port""",
            ports + [since],
        )
        return cursor.fetchall()

    def request_count_delta_for_port(self, cursor: Cursor, port: int, since: int) -> tuple:
        cursor.execute(
            """SELECT SUM(count) FROM http_request_time_stats
               WHERE port = %s AND time >= %s""",
            (port, since),
        )
        return cursor.fetchone()

    def blocked_request_count_delta_for_port(self, cursor: Cursor, port: int, since: int) -> tuple:
        cursor.execute(
            """SELECT SUM(blocked_count) FROM http_request_time_stats
               WHERE port = %s AND time >= %s""",
            (port, since),
        )
        return cursor.fetchone()

    def flag_delta_for_port(self, cursor: Cursor, port: int, since: int) -> tuple:
        cursor.execute(
            """SELECT SUM(write_count), SUM(read_count)
               FROM flag_time_stats
               WHERE port = %s AND time >= %s""",
            (port, since),
        )
        return cursor.fetchone()

    def list_http_requests(
        self,
        conn: Connection,
        port: int,
        filter_path: str | None,
        filter_method: str | None,
        filter_status: int | None,
        filter_blocked: bool | None,
        filter_tag: str | None,
        page_size: int,
        offset: int,
    ) -> tuple[int, list]:
        cursor = conn.cursor()

        base_query = """
            FROM http_request req
            LEFT JOIN http_response resp ON req.id = resp.request_id
            WHERE req.port = %s
        """

        params = [port]

        if filter_tag:
            clause, tag_params = self.tag_filter_clause("http", port, filter_tag, "req.id")
            base_query += clause
            params.extend(tag_params)

        if filter_path:
            base_query += " AND req.path LIKE %s"
            params.append(f"%{filter_path}%")

        if filter_method:
            base_query += " AND req.method = %s"
            params.append(filter_method.upper())

        if filter_status:
            base_query += " AND resp.status = %s"
            params.append(filter_status)

        if filter_blocked is not None:
            base_query += " AND req.is_blocked = %s"
            params.append(1 if filter_blocked else 0)

        count_query = f"SELECT COUNT(*) {base_query}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        id_query = f"""
            SELECT req.id
            {base_query}
            ORDER BY req.start_time DESC
            LIMIT %s OFFSET %s
        """

        id_params = params.copy()
        id_params.extend([page_size, offset])
        cursor.execute(id_query, id_params)
        request_ids = [row[0] for row in cursor.fetchall()]

        if not request_ids:
            return total_count, []

        query = """
            WITH request_data AS (
                SELECT
                    req.id,
                    req.start_time,
                    req.method,
                    req.path,
                    resp.status,
                    resp.id as response_id,
                    req.is_blocked,
                    req.user_agent
                FROM http_request req
                LEFT JOIN http_response resp ON req.id = resp.request_id
                WHERE req.id IN ({})
            ),
            flag_counts AS (
                SELECT
                    http_request_id,
                    COUNT(*) as req_count
                FROM flag
                WHERE http_request_id IN ({})
                GROUP BY http_request_id
            ),
            resp_flag_counts AS (
                SELECT
                    http_response_id,
                    COUNT(*) as resp_count
                FROM flag
                WHERE http_response_id IN (
                    SELECT response_id FROM request_data WHERE response_id IS NOT NULL
                )
                GROUP BY http_response_id
            ),
            session_counts AS (
                SELECT
                    sl.http_request_id,
                    SUM(s.count) as total_session_requests
                FROM session_link sl
                JOIN session s ON sl.session_id = s.id
                WHERE sl.http_request_id IN ({})
                GROUP BY sl.http_request_id
            )
            SELECT
                rd.id,
                rd.start_time,
                rd.method,
                rd.path,
                rd.status,
                rd.is_blocked,
                rd.user_agent,
                COALESCE(fc.req_count, 0) as req_flags_count,
                COALESCE(rfc.resp_count, 0) as resp_flags_count,
                COALESCE(sc.total_session_requests, 0) as total_session_requests
            FROM request_data rd
            LEFT JOIN flag_counts fc ON rd.id = fc.http_request_id
            LEFT JOIN resp_flag_counts rfc ON rd.response_id = rfc.http_response_id
            LEFT JOIN session_counts sc ON rd.id = sc.http_request_id
            ORDER BY rd.start_time DESC
        """.format(
            ",".join(["%s"] * len(request_ids)),
            ",".join(["%s"] * len(request_ids)),
            ",".join(["%s"] * len(request_ids)),
        )

        cursor.execute(query, request_ids * 2 + request_ids)
        return total_count, cursor.fetchall()

    def http_request_detail(self, cursor: Cursor, request_id: int) -> tuple:
        cursor.execute(
            """
            SELECT
                req.method,
                req.path,
                req.body,
                req.user_agent,
                req.start_time,
                req.port,
                req.is_blocked,
                req.is_websocket,
                resp.id as response_id,
                resp.status,
                resp.body as response_body
            FROM http_request req
            LEFT JOIN http_response resp ON req.id = resp.request_id
            WHERE req.id = %s
            """,
            (request_id,),
        )
        return cursor.fetchone()

    def http_request_headers(self, cursor: Cursor, request_id: int) -> list:
        cursor.execute("SELECT request_headers FROM http_request WHERE id = %s", (request_id,))
        row = cursor.fetchone()
        return parse_headers(row[0]) if row else []

    def flags_for_request(self, cursor: Cursor, request_id: int) -> list:
        cursor.execute(
            """
            SELECT id, value, location
            FROM flag
            WHERE http_request_id = %s
            """,
            (request_id,),
        )
        return cursor.fetchall()

    def linked_session_requests(self, cursor: Cursor, request_id: int) -> list:
        cursor.execute(
            """
            SELECT DISTINCT sl2.http_request_id,
                   CASE
                     WHEN sl2.http_request_id < %s THEN 'incoming'
                     WHEN sl2.http_request_id > %s THEN 'outgoing'
                   END as direction,
                   s.key as session_key
            FROM session_link sl1
            JOIN session_link sl2 ON sl1.session_id = sl2.session_id
            JOIN session s ON s.id = sl1.session_id
            WHERE sl1.http_request_id = %s
              AND sl2.http_request_id != %s
            ORDER BY sl2.http_request_id
            """,
            (request_id, request_id, request_id, request_id),
        )
        return cursor.fetchall()

    def http_requests_basic(self, cursor: Cursor, ids: list[int]) -> list:
        placeholders = ",".join("%s" for _ in ids)
        cursor.execute(
            f"""
                SELECT id, method, path, start_time
                FROM http_request
                WHERE id IN ({placeholders})
                """,
            ids,
        )
        return cursor.fetchall()

    def websocket_connection_id_for_request(self, cursor: Cursor, request_id: int) -> tuple:
        cursor.execute(
            """
                SELECT wc.id
                FROM websocket_connection wc
                WHERE wc.http_request_id = %s
                """,
            (request_id,),
        )
        return cursor.fetchone()

    def websocket_frames_for_connection(self, cursor: Cursor, connection_id: int) -> list:
        cursor.execute(
            """
                    SELECT wf.id, wf.ord, wf.opcode, wf.payload_text, wf.payload_size, wf.is_client
                    FROM websocket_frame wf
                    WHERE wf.connection_id = %s
                    ORDER BY wf.ord
                    """,
            (connection_id,),
        )
        return cursor.fetchall()

    def flags_for_websocket_frame(self, cursor: Cursor, frame_id: int) -> list:
        cursor.execute(
            """
                        SELECT value FROM flag WHERE websocket_frame_id = %s
                        """,
            (frame_id,),
        )
        return cursor.fetchall()

    def http_response_headers(self, cursor: Cursor, response_id: int) -> list:
        cursor.execute("SELECT response_headers FROM http_response WHERE id = %s", (response_id,))
        row = cursor.fetchone()
        return parse_headers(row[0]) if row else []

    def flags_for_response(self, cursor: Cursor, response_id: int) -> list:
        cursor.execute(
            """
                SELECT id, value, location
                FROM flag
                WHERE http_response_id = %s
                """,
            (response_id,),
        )
        return cursor.fetchall()

    def tcp_stats_for_port(self, cursor: Cursor, port: int) -> tuple:
        cursor.execute(
            """
            SELECT
                total_connections,
                total_bytes_in,
                total_bytes_out,
                avg_duration_ms,
                total_flags_found
            FROM tcp_stats
            WHERE port = %s
        """,
            (port,),
        )
        return cursor.fetchone()

    def list_tcp_connections(
        self,
        conn: Connection,
        port: int,
        search: str | None,
        filter_tag: str | None,
        page_size: int,
        offset: int,
    ) -> tuple[int, list]:
        cursor = conn.cursor()

        search_clause, search_params = self.build_tcp_search_filter(search) if search else ("", [])

        tag_clause, tag_params = "", []
        if filter_tag:
            tag_clause, tag_params = self.tag_filter_clause("tcp", port, filter_tag, "id")
        filter_clause = f"{search_clause}{tag_clause}"
        filter_params = [*search_params, *tag_params]

        cursor.execute(
            f"""
            SELECT COUNT(*) FROM tcp_connection WHERE port = %s{filter_clause}
        """,
            (port, *filter_params),
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            f"""
            WITH tcp_ids AS (
                SELECT id FROM tcp_connection
                WHERE port = %s{filter_clause}
                ORDER BY start_time DESC
                LIMIT %s OFFSET %s
            )
            SELECT
                tc.id, tc.connection_id, tc.start_time, tc.duration_ms,
                tc.bytes_in, tc.bytes_out,
                COALESCE(f_in.count, 0) as flags_in,
                COALESCE(f_out.count, 0) as flags_out,
                tc.is_blocked
            FROM tcp_connection tc
            LEFT JOIN (
                SELECT tcp_connection_id, COUNT(*) as count
                FROM flag
                WHERE location = 'read' AND tcp_connection_id IN (SELECT id FROM tcp_ids)
                GROUP BY tcp_connection_id
            ) f_in ON tc.id = f_in.tcp_connection_id
            LEFT JOIN (
                SELECT tcp_connection_id, COUNT(*) as count
                FROM flag
                WHERE location = 'write' AND tcp_connection_id IN (SELECT id FROM tcp_ids)
                GROUP BY tcp_connection_id
            ) f_out ON tc.id = f_out.tcp_connection_id
            WHERE tc.id IN (SELECT id FROM tcp_ids)
            ORDER BY tc.start_time DESC
        """,
            (port, *filter_params, page_size, offset),
        )
        return total, cursor.fetchall()

    def tcp_connection_detail(self, cursor: Cursor, connection_id: int) -> tuple:
        cursor.execute(
            """
            SELECT
                tc.id, tc.connection_id, tc.port, tc.start_time, tc.duration_ms,
                tc.bytes_in, tc.bytes_out, tc.is_blocked
            FROM tcp_connection tc
            WHERE tc.id = %s
        """,
            (connection_id,),
        )
        return cursor.fetchone()

    def tcp_events_for_connection(self, cursor: Cursor, connection_id: int) -> list:
        cursor.execute(
            """
            SELECT
                te.id, te.timestamp, te.event_type, te.data_size, te.data,
                te.truncated, te.end_stream
            FROM tcp_event te
            WHERE te.connection_id = %s
            ORDER BY te.timestamp
        """,
            (connection_id,),
        )
        return cursor.fetchall()

    def flags_for_tcp_event(self, cursor: Cursor, event_id: int) -> list:
        cursor.execute(
            """
                SELECT value FROM flag WHERE tcp_event_id = %s
            """,
            (event_id,),
        )
        return cursor.fetchall()

    def flag_count_for_tcp_connection(self, cursor: Cursor, connection_id: int) -> tuple:
        cursor.execute(
            """
            SELECT COUNT(*) FROM flag WHERE tcp_connection_id = %s
        """,
            (connection_id,),
        )
        return cursor.fetchone()

    def tcp_connection_time_stats(self, cursor: Cursor, port: int, start_timestamp: int) -> list:
        cursor.execute(
            """
            SELECT read_min, read_max, write_min, write_max, time, SUM(count) as count
            FROM tcp_connection_time_stats
            WHERE port = %s AND time >= %s
            GROUP BY read_min, read_max, write_min, write_max, time
            ORDER BY read_min, write_min, time
        """,
            (port, start_timestamp),
        )
        return cursor.fetchall()

    def tcp_connection_blocked_counts(
        self, cursor: Cursor, port: int, start_timestamp: int
    ) -> list:
        cursor.execute(
            """
            SELECT bytes_in, bytes_out, COUNT(*) as blocked_count
            FROM tcp_connection
            WHERE port = %s AND start_time >= %s AND is_blocked = 1
            GROUP BY bytes_in, bytes_out
        """,
            (port, start_timestamp),
        )
        return cursor.fetchall()

    def list_websocket_connections(
        self, cursor: Cursor, port: int, page_size: int, offset: int
    ) -> tuple[int, list]:
        cursor.execute(
            """
            SELECT COUNT(*) FROM websocket_connection WHERE port = %s
        """,
            (port,),
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            WITH ws_ids AS (
                SELECT id FROM websocket_connection
                WHERE port = %s
                ORDER BY start_time DESC
                LIMIT %s OFFSET %s
            )
            SELECT
                wc.id, wc.start_time, wc.duration_ms,
                wc.frames_in, wc.frames_out, wc.bytes_in, wc.bytes_out,
                COALESCE(f_in.count, 0) as flags_in,
                COALESCE(f_out.count, 0) as flags_out,
                wc.is_blocked
            FROM websocket_connection wc
            LEFT JOIN (
                SELECT wf.connection_id, COUNT(DISTINCT f.id) as count
                FROM websocket_frame wf
                JOIN flag f ON f.websocket_frame_id = wf.id
                WHERE wf.direction = 'receive' AND wf.connection_id IN (SELECT id FROM ws_ids)
                GROUP BY wf.connection_id
            ) f_in ON wc.id = f_in.connection_id
            LEFT JOIN (
                SELECT wf.connection_id, COUNT(DISTINCT f.id) as count
                FROM websocket_frame wf
                JOIN flag f ON f.websocket_frame_id = wf.id
                WHERE wf.direction = 'send' AND wf.connection_id IN (SELECT id FROM ws_ids)
                GROUP BY wf.connection_id
            ) f_out ON wc.id = f_out.connection_id
            WHERE wc.id IN (SELECT id FROM ws_ids)
            ORDER BY wc.start_time DESC
        """,
            (port, page_size, offset),
        )
        return total, cursor.fetchall()

    def websocket_connection_detail(self, cursor: Cursor, connection_id: int) -> tuple:
        cursor.execute(
            """
            SELECT
                wc.id, wc.port, wc.start_time, wc.duration_ms,
                wc.frames_in, wc.frames_out, wc.bytes_in, wc.bytes_out, wc.is_blocked
            FROM websocket_connection wc
            WHERE wc.id = %s
        """,
            (connection_id,),
        )
        return cursor.fetchone()

    def websocket_frames_detail(self, cursor: Cursor, connection_id: int) -> list:
        cursor.execute(
            """
            SELECT
                wf.id, wf.timestamp, wf.direction, wf.opcode, wf.payload_size, wf.payload_text
            FROM websocket_frame wf
            WHERE wf.connection_id = %s
            ORDER BY wf.timestamp
        """,
            (connection_id,),
        )
        return cursor.fetchall()

    def flag_count_for_websocket_connection(self, cursor: Cursor, connection_id: int) -> tuple:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT f.id)
            FROM websocket_frame wf
            JOIN flag f ON f.websocket_frame_id = wf.id
            WHERE wf.connection_id = %s
        """,
            (connection_id,),
        )
        return cursor.fetchone()

    def recent_flag_stats(self, cursor: Cursor, since: int) -> list:
        cursor.execute(
            """
            SELECT port, time, write_count, read_count
            FROM flag_time_stats
            WHERE time >= %s
            ORDER BY time DESC
            """,
            (since,),
        )
        return cursor.fetchall()

    def flag_time_stats_for_port(self, cursor: Cursor, port: int, start_time: int) -> list:
        cursor.execute(
            """
            SELECT port, time, write_count, read_count
            FROM flag_time_stats
            WHERE port = %s AND time >= %s
            ORDER BY time ASC
            """,
            (port, start_time),
        )
        return cursor.fetchall()

    def request_time_stats_for_port(self, cursor: Cursor, port: int, start_time: int) -> list:
        cursor.execute(
            """
            SELECT port, time, count, blocked_count
            FROM http_request_time_stats
            WHERE port = %s AND time >= %s
            ORDER BY time ASC
            """,
            (port, start_time),
        )
        return cursor.fetchall()

    def all_request_time_stats(self, cursor: Cursor, start_time: int) -> list:
        cursor.execute(
            """
            SELECT port, time, count, blocked_count
            FROM http_request_time_stats
            WHERE time >= %s
            ORDER BY port, time ASC
            """,
            (start_time,),
        )
        return cursor.fetchall()

    def all_flag_time_stats(self, cursor: Cursor, start_time: int) -> list:
        cursor.execute(
            """
            SELECT port, time, write_count, read_count
            FROM flag_time_stats
            WHERE time >= %s
            ORDER BY port, time ASC
            """,
            (start_time,),
        )
        return cursor.fetchall()

    def time_series_with_totals_rows(
        self,
        cursor: Cursor,
        table_name: str,
        key_columns: list[str],
        port: int,
        window_start: int,
    ) -> list:
        key_columns_str = ", ".join(key_columns)
        cursor.execute(
            f"""
                SELECT {key_columns_str}, time, count
                FROM {table_name}
                WHERE port = %s AND time >= %s
                ORDER BY {key_columns_str}, time
            """,
            [port, window_start],
        )
        return cursor.fetchall()

    def time_series_range_rows(
        self,
        cursor: Cursor,
        table_name: str,
        key_columns: list[str],
        port: int,
        start_ms: int,
        end_ms: int,
    ) -> list:
        key_columns_str = ", ".join(key_columns)
        cursor.execute(
            f"""
                SELECT {key_columns_str}, time, count
                FROM {table_name}
                WHERE port = %s AND time >= %s AND time < %s
                ORDER BY {key_columns_str}, time
            """,
            [port, start_ms, end_ms],
        )
        return cursor.fetchall()

    def service_stats_for_port(self, cursor: Cursor, port: int) -> tuple:
        cursor.execute(
            """SELECT total_requests, total_blocked_requests, total_responses, total_blocked_responses,
                      total_flags_written, total_flags_retrieved, total_flags_blocked
               FROM service_stats WHERE port = %s""",
            (port,),
        )
        return cursor.fetchone()

    def response_code_counts_for_port(self, cursor: Cursor, port: int) -> list:
        cursor.execute(
            """SELECT status_code, count FROM http_response_code_stats
               WHERE port = %s ORDER BY count DESC""",
            (port,),
        )
        return cursor.fetchall()

    def distinct_path_count_for_port(self, cursor: Cursor, port: int) -> tuple:
        cursor.execute(
            """SELECT COUNT(DISTINCT path) FROM http_path_stats WHERE port = %s""",
            (port,),
        )
        return cursor.fetchone()

    def header_distinct_counts_for_port(self, cursor: Cursor, port: int) -> tuple:
        cursor.execute(
            """SELECT COUNT(DISTINCT name), COUNT(DISTINCT value)
               FROM http_header_time_stats
               WHERE port = %s""",
            (port,),
        )
        return cursor.fetchone()

    def request_batch_tap(self, cursor: Cursor, request_id: int) -> tuple:
        cursor.execute("SELECT batch_id, tap_id FROM http_request WHERE id = %s", (request_id,))
        return cursor.fetchone()
