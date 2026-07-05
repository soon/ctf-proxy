CREATE SCHEMA IF NOT EXISTS dashboard;
SET search_path TO dashboard;

CREATE TABLE IF NOT EXISTS rule_source (
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    updated BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (name, status)
);
