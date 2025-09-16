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
    FOREIGN KEY (http_request_id) REFERENCES http_request (id),
    FOREIGN KEY (http_response_id) REFERENCES http_response (id)
) STRICT;

CREATE INDEX IF NOT EXISTS alert_port ON alert(port);
CREATE INDEX IF NOT EXISTS alert_http_request_id ON alert(http_request_id);
CREATE INDEX IF NOT EXISTS alert_http_response_id ON alert(http_response_id);
CREATE INDEX IF NOT EXISTS alert_description ON alert(description);

CREATE TABLE IF NOT EXISTS flag (
    id INTEGER PRIMARY KEY,
    http_request_id INTEGER,
    http_response_id INTEGER,
    location TEXT,
    offset INTEGER,
    value TEXT NOT NULL,
    FOREIGN KEY (http_request_id) REFERENCES http_request (id),
    FOREIGN KEY (http_response_id) REFERENCES http_response (id)
) STRICT;

CREATE INDEX IF NOT EXISTS flag_http_request_id ON flag(http_request_id);
CREATE INDEX IF NOT EXISTS flag_http_response_id ON flag(http_response_id);

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