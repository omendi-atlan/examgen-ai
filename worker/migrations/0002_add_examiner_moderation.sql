-- EXAMGEN AI: examiner moderation metadata
ALTER TABLE examination_attempts ADD COLUMN review_status TEXT NOT NULL DEFAULT 'not_required'
  CHECK (review_status IN ('not_required', 'pending', 'approved'));
ALTER TABLE examination_attempts ADD COLUMN moderation_json TEXT;
ALTER TABLE examination_attempts ADD COLUMN moderated_by TEXT;
ALTER TABLE examination_attempts ADD COLUMN moderated_at TEXT;

UPDATE examination_attempts
SET review_status = 'pending'
WHERE status = 'submitted' AND result_json LIKE '%"pending_review"%';

CREATE INDEX IF NOT EXISTS idx_attempts_review_status
  ON examination_attempts(review_status, submitted_at);
