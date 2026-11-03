-- EXAMGEN AI: per-IP generation throttling (hashed identifiers only)
CREATE TABLE IF NOT EXISTS api_rate_limits (
  ip_hash TEXT PRIMARY KEY,
  window_start INTEGER NOT NULL,
  request_count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_rate_limits_window ON api_rate_limits(window_start);
