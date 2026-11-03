-- EXAMGEN AI: persistent examination attempts
CREATE TABLE IF NOT EXISTS examination_attempts (
  id TEXT PRIMARY KEY,
  mode TEXT NOT NULL CHECK (mode IN ('practice', 'simulation')),
  subject TEXT NOT NULL,
  exam_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'in_progress'
    CHECK (status IN ('in_progress', 'submitted', 'expired')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  expires_at TEXT NOT NULL,
  submitted_at TEXT,
  answers_json TEXT,
  result_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_attempts_status_expiry
  ON examination_attempts(status, expires_at);

CREATE INDEX IF NOT EXISTS idx_attempts_created
  ON examination_attempts(created_at);
