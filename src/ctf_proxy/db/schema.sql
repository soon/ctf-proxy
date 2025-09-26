-- Enable WAL mode and performance optimizations ???
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=10000;
PRAGMA temp_store=MEMORY;

CREATE TABLE IF NOT EXISTS http_request (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    start_time INTEGER NOT NULL,
    path TEXT NOT NULL,
    method TEXT NOT NULL,
    user_agent TEXT,
    body TEXT,
    is_blocked INTEGER NOT NULL,
    -- trace request data in archive
    tap_id TEXT,
    batch_id TEXT
) STRICT;

CREATE INDEX IF NOT EXISTS http_request_port ON http_request(port);
CREATE INDEX IF NOT EXISTS http_request_path ON http_request(path);
CREATE INDEX IF NOT EXISTS http_request_user_agent ON http_request(user_agent);

CREATE TABLE IF NOT EXISTS http_response (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL,
    status INTEGER NOT NULL,
    body TEXT,
    FOREIGN KEY (request_id) REFERENCES http_request (id)
) STRICT;

CREATE INDEX IF NOT EXISTS http_response_status ON http_response(status);
CREATE INDEX IF NOT EXISTS http_response_request_id ON http_response(request_id);

CREATE TABLE IF NOT EXISTS http_request_time_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    time INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS http_request_time_stats_unique ON http_request_time_stats(port, time);

CREATE TABLE IF NOT EXISTS http_header (
    id INTEGER PRIMARY KEY,
    request_id INTEGER,
    response_id INTEGER,
    name TEXT NOT NULL,
    value TEXT NOT NULL,
    FOREIGN KEY (request_id) REFERENCES http_request (id),
    FOREIGN KEY (response_id) REFERENCES http_response (id)
) STRICT;

CREATE INDEX IF NOT EXISTS http_header_name ON http_header(name);
CREATE INDEX IF NOT EXISTS http_header_request_id ON http_header(request_id);
CREATE INDEX IF NOT EXISTS http_header_response_id ON http_header(response_id);
CREATE INDEX IF NOT EXISTS http_header_name_value ON http_header(name, value);

CREATE TABLE IF NOT EXISTS alert (
    id INTEGER PRIMARY KEY,
    created INTEGER NOT NULL,
    description TEXT NOT NULL,
    port INTEGER,
    http_request_id INTEGER,
    http_response_id INTEGER,
    tcp_connection_id INTEGER,
    FOREIGN KEY (http_request_id) REFERENCES http_request (id),
    FOREIGN KEY (http_response_id) REFERENCES http_response (id),
    FOREIGN KEY (tcp_connection_id) REFERENCES tcp_connection (id)
) STRICT;

CREATE INDEX IF NOT EXISTS alert_port ON alert(port);
CREATE INDEX IF NOT EXISTS alert_http_request_id ON alert(http_request_id);
CREATE INDEX IF NOT EXISTS alert_http_response_id ON alert(http_response_id);
CREATE INDEX IF NOT EXISTS alert_tcp_connection_id ON alert(tcp_connection_id);
CREATE INDEX IF NOT EXISTS alert_description ON alert(description);

CREATE TABLE IF NOT EXISTS flag (
    id INTEGER PRIMARY KEY,
    http_request_id INTEGER,
    http_response_id INTEGER,
    tcp_connection_id INTEGER,
    tcp_event_id INTEGER,
    location TEXT,
    offset INTEGER,
    value TEXT NOT NULL,
    FOREIGN KEY (http_request_id) REFERENCES http_request (id),
    FOREIGN KEY (http_response_id) REFERENCES http_response (id),
    FOREIGN KEY (tcp_connection_id) REFERENCES tcp_connection (id),
    FOREIGN KEY (tcp_event_id) REFERENCES tcp_event (id)
) STRICT;

CREATE INDEX IF NOT EXISTS flag_http_request_id ON flag(http_request_id);
CREATE INDEX IF NOT EXISTS flag_http_response_id ON flag(http_response_id);
CREATE INDEX IF NOT EXISTS flag_tcp_connection_id ON flag(tcp_connection_id);
CREATE INDEX IF NOT EXISTS flag_tcp_event_id ON flag(tcp_event_id);

CREATE TABLE IF NOT EXISTS flag_time_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    time INTEGER NOT NULL,
    write_count INTEGER NOT NULL DEFAULT 0,
    read_count INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS flag_time_stats_unique ON flag_time_stats(port, time);

CREATE TABLE IF NOT EXISTS service_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    total_requests INTEGER NOT NULL DEFAULT 0,
    total_blocked_requests INTEGER NOT NULL DEFAULT 0,
    total_responses INTEGER NOT NULL DEFAULT 0,
    total_blocked_responses INTEGER NOT NULL DEFAULT 0,
    total_flags_written INTEGER NOT NULL DEFAULT 0,
    total_flags_retrieved INTEGER NOT NULL DEFAULT 0,
    total_flags_blocked INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS service_stats_unique_port ON service_stats(port);


CREATE TABLE IF NOT EXISTS http_response_code_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    status_code INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS http_response_code_stats_unique ON http_response_code_stats(port, status_code);

CREATE TABLE IF NOT EXISTS http_path_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    path TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS http_path_stats_unique ON http_path_stats(port, path);

CREATE TABLE IF NOT EXISTS http_path_time_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    time INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS http_path_time_stats_unique ON http_path_time_stats(port, method, path, time);

CREATE TABLE IF NOT EXISTS http_query_param_time_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    param TEXT NOT NULL,
    value TEXT NOT NULL,
    time INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS http_query_param_time_stats_unique ON http_query_param_time_stats(port, param, value, time);

CREATE TABLE IF NOT EXISTS http_header_time_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    name TEXT NOT NULL,
    value TEXT NOT NULL,
    time INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS http_header_time_stats_unique ON http_header_time_stats(port, name, value, time);

CREATE TABLE IF NOT EXISTS session (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    key TEXT NOT NULL
) STRICT;
CREATE UNIQUE INDEX IF NOT EXISTS session_unique ON session(port, key);

CREATE TABLE IF NOT EXISTS session_link (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    http_request_id INTEGER,
    FOREIGN KEY (session_id) REFERENCES session (id),
    FOREIGN KEY (http_request_id) REFERENCES http_request (id)
) STRICT;

CREATE INDEX IF NOT EXISTS session_link_session_id ON session_link(session_id);
CREATE INDEX IF NOT EXISTS session_link_http_request_id ON session_link(http_request_id);

CREATE TABLE IF NOT EXISTS tcp_connection (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    connection_id INTEGER NOT NULL,
    start_time INTEGER NOT NULL,
    duration_ms INTEGER,
    bytes_in INTEGER NOT NULL,
    bytes_out INTEGER NOT NULL,
    is_blocked INTEGER NOT NULL,
    -- trace data in archive
    tap_id TEXT,
    batch_id TEXT
) STRICT;

CREATE INDEX IF NOT EXISTS tcp_connection_port ON tcp_connection(port);
CREATE INDEX IF NOT EXISTS tcp_connection_start_time ON tcp_connection(start_time);
CREATE INDEX IF NOT EXISTS tcp_connection_connection_id ON tcp_connection(connection_id);

CREATE TABLE IF NOT EXISTS tcp_event (
    id INTEGER PRIMARY KEY,
    connection_id INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    event_type TEXT NOT NULL, -- 'read' or 'write'
    data BLOB,
    data_text TEXT, -- decoded text if applicable
    data_size INTEGER NOT NULL,
    end_stream INTEGER NOT NULL DEFAULT 0,
    truncated INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (connection_id) REFERENCES tcp_connection (id)
) STRICT;

CREATE INDEX IF NOT EXISTS tcp_event_connection_id ON tcp_event(connection_id);
CREATE INDEX IF NOT EXISTS tcp_event_timestamp ON tcp_event(timestamp);
CREATE INDEX IF NOT EXISTS tcp_event_type ON tcp_event(event_type);


CREATE TABLE IF NOT EXISTS tcp_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    total_connections INTEGER NOT NULL DEFAULT 0,
    total_bytes_in INTEGER NOT NULL DEFAULT 0,
    total_bytes_out INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms INTEGER NOT NULL DEFAULT 0,
    total_flags_found INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS tcp_stats_unique_port ON tcp_stats(port);

CREATE TABLE IF NOT EXISTS tcp_connection_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    read_min INTEGER NOT NULL,
    read_max INTEGER NOT NULL,
    write_min INTEGER NOT NULL,
    write_max INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS tcp_connection_stats_unique ON tcp_connection_stats(port, read_min, read_max, write_min, write_max);

CREATE TABLE IF NOT EXISTS tcp_connection_time_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    read_min INTEGER NOT NULL,
    read_max INTEGER NOT NULL,
    write_min INTEGER NOT NULL,
    write_max INTEGER NOT NULL,
    time INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS tcp_connection_time_stats_unique ON tcp_connection_time_stats(port, read_min, read_max, write_min, write_max, time);
