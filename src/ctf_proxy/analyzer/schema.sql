PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=10000;
PRAGMA temp_store=MEMORY;

CREATE TABLE IF NOT EXISTS rule (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE IF NOT EXISTS analysis_cursor (
    rule_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    last_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (rule_id, source),
    FOREIGN KEY (rule_id) REFERENCES rule (id)
) STRICT;

CREATE TABLE IF NOT EXISTS http_analysis_result (
    id INTEGER PRIMARY KEY,
    rule_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    meta TEXT,
    port INTEGER,
    http_request_id INTEGER,
    created INTEGER NOT NULL,
    event_time INTEGER,
    batch_id TEXT,
    FOREIGN KEY (rule_id) REFERENCES rule (id)
) STRICT;

CREATE INDEX IF NOT EXISTS http_analysis_result_tag ON http_analysis_result(tag);
CREATE INDEX IF NOT EXISTS http_analysis_result_rule_id ON http_analysis_result(rule_id);
CREATE INDEX IF NOT EXISTS http_analysis_result_port ON http_analysis_result(port);
CREATE INDEX IF NOT EXISTS http_analysis_result_http_request_id ON http_analysis_result(http_request_id);

CREATE TABLE IF NOT EXISTS tcp_analysis_result (
    id INTEGER PRIMARY KEY,
    rule_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    meta TEXT,
    port INTEGER,
    tcp_connection_id INTEGER,
    created INTEGER NOT NULL,
    event_time INTEGER,
    batch_id TEXT,
    FOREIGN KEY (rule_id) REFERENCES rule (id)
) STRICT;

CREATE INDEX IF NOT EXISTS tcp_analysis_result_tag ON tcp_analysis_result(tag);
CREATE INDEX IF NOT EXISTS tcp_analysis_result_rule_id ON tcp_analysis_result(rule_id);
CREATE INDEX IF NOT EXISTS tcp_analysis_result_port ON tcp_analysis_result(port);
CREATE INDEX IF NOT EXISTS tcp_analysis_result_tcp_connection_id ON tcp_analysis_result(tcp_connection_id);

CREATE TABLE IF NOT EXISTS backfill_job (
    id INTEGER PRIMARY KEY,
    target_id INTEGER NOT NULL,
    ports TEXT,
    http_cursor INTEGER NOT NULL DEFAULT 0,
    tcp_cursor INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    created INTEGER NOT NULL,
    updated INTEGER NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS backfill_job_status ON backfill_job(status);

CREATE TABLE IF NOT EXISTS tag_time_stats (
    id INTEGER PRIMARY KEY,
    port INTEGER NOT NULL,
    rule_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    source TEXT NOT NULL,
    time INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (rule_id) REFERENCES rule (id)
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS tag_time_stats_unique
    ON tag_time_stats(port, rule_id, tag, source, time);
CREATE INDEX IF NOT EXISTS tag_time_stats_port_time ON tag_time_stats(port, time);
CREATE INDEX IF NOT EXISTS tag_time_stats_tag ON tag_time_stats(tag);
