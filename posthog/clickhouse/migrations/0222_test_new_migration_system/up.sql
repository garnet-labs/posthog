CREATE TABLE IF NOT EXISTS {{ database }}.ch_migrate_test (id UInt64) ENGINE = MergeTree() ORDER BY id
