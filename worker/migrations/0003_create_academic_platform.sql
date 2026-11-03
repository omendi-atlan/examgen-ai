-- EXAMGEN AI: academic content, blueprint, question bank and learning records.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subjects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  code TEXT,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS topics (
  id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  parent_topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(subject_id, parent_topic_id, name)
);
CREATE INDEX IF NOT EXISTS idx_topics_subject ON topics(subject_id, status);

CREATE TABLE IF NOT EXISTS learning_outcomes (
  id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
  code TEXT,
  description TEXT NOT NULL,
  cognitive_level TEXT NOT NULL DEFAULT 'understand'
    CHECK (cognitive_level IN ('remember','understand','apply','analyse','evaluate','create')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(subject_id, code)
);
CREATE INDEX IF NOT EXISTS idx_outcomes_subject_topic ON learning_outcomes(subject_id, topic_id);

CREATE TABLE IF NOT EXISTS source_documents (
  id TEXT PRIMARY KEY,
  subject_id TEXT REFERENCES subjects(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_size INTEGER NOT NULL CHECK (file_size >= 0),
  storage_key TEXT,
  extracted_text TEXT NOT NULL DEFAULT '',
  extraction_status TEXT NOT NULL DEFAULT 'uploaded'
    CHECK (extraction_status IN ('uploaded','processing','extracted','needs_review','failed','approved','rejected')),
  extraction_error TEXT,
  source_metadata_json TEXT NOT NULL DEFAULT '{}',
  approved_at TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_sources_subject_status ON source_documents(subject_id, extraction_status);

CREATE TABLE IF NOT EXISTS source_document_topics (
  source_document_id TEXT NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
  topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  PRIMARY KEY(source_document_id, topic_id)
);

CREATE TABLE IF NOT EXISTS visual_assets (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  alt_text TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_size INTEGER NOT NULL CHECK (file_size >= 0),
  storage_key TEXT NOT NULL,
  approval_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (approval_status IN ('pending','approved','rejected','archived')),
  approved_at TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_visual_assets_status ON visual_assets(approval_status);

CREATE TABLE IF NOT EXISTS question_bank (
  id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
  learning_outcome_id TEXT REFERENCES learning_outcomes(id) ON DELETE SET NULL,
  source_document_id TEXT REFERENCES source_documents(id) ON DELETE SET NULL,
  visual_asset_id TEXT REFERENCES visual_assets(id) ON DELETE SET NULL,
  question_type TEXT NOT NULL CHECK (question_type IN ('multiple_choice','dropdown','short_answer','long_answer','numeric')),
  difficulty TEXT NOT NULL CHECK (difficulty IN ('foundation','intermediate','advanced')),
  cognitive_level TEXT NOT NULL DEFAULT 'understand'
    CHECK (cognitive_level IN ('remember','understand','apply','analyse','evaluate','create')),
  marks INTEGER NOT NULL CHECK (marks > 0),
  question_json TEXT NOT NULL,
  answer_key_json TEXT NOT NULL,
  rubric_json TEXT,
  provenance_json TEXT NOT NULL DEFAULT '{}',
  quality_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (quality_status IN ('draft','review','approved','archived')),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  duplicate_hash TEXT,
  usage_count INTEGER NOT NULL DEFAULT 0 CHECK (usage_count >= 0),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_questions_subject_topic ON question_bank(subject_id, topic_id, quality_status);
CREATE INDEX IF NOT EXISTS idx_questions_filter ON question_bank(question_type, difficulty, cognitive_level, quality_status);
CREATE INDEX IF NOT EXISTS idx_questions_duplicate ON question_bank(duplicate_hash);

CREATE TABLE IF NOT EXISTS exam_blueprints (
  id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 1 AND 360),
  total_marks INTEGER NOT NULL CHECK (total_marks > 0),
  difficulty_distribution_json TEXT NOT NULL DEFAULT '{}',
  cognitive_distribution_json TEXT NOT NULL DEFAULT '{}',
  question_type_distribution_json TEXT NOT NULL DEFAULT '{}',
  section_structure_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','archived')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS blueprint_topic_allocations (
  blueprint_id TEXT NOT NULL REFERENCES exam_blueprints(id) ON DELETE CASCADE,
  topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  allocated_marks INTEGER NOT NULL CHECK (allocated_marks >= 0),
  allocated_percentage REAL NOT NULL CHECK (allocated_percentage >= 0 AND allocated_percentage <= 100),
  PRIMARY KEY(blueprint_id, topic_id)
);

CREATE TABLE IF NOT EXISTS exam_papers (
  id TEXT PRIMARY KEY,
  blueprint_id TEXT REFERENCES exam_blueprints(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  mode TEXT NOT NULL CHECK (mode IN ('practice','simulation')),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','published','archived')),
  exam_snapshot_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS exam_paper_questions (
  exam_paper_id TEXT NOT NULL REFERENCES exam_papers(id) ON DELETE CASCADE,
  question_bank_id TEXT NOT NULL REFERENCES question_bank(id) ON DELETE RESTRICT,
  question_order INTEGER NOT NULL CHECK (question_order > 0),
  marks INTEGER NOT NULL CHECK (marks > 0),
  section_name TEXT NOT NULL DEFAULT 'Section A',
  PRIMARY KEY(exam_paper_id, question_order),
  UNIQUE(exam_paper_id, question_bank_id)
);

CREATE TABLE IF NOT EXISTS marking_reviews (
  id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES examination_attempts(id) ON DELETE CASCADE,
  question_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','in_progress','finalised')),
  marks_awarded REAL,
  marks_available REAL NOT NULL CHECK (marks_available > 0),
  criteria_results_json TEXT NOT NULL DEFAULT '[]',
  feedback TEXT NOT NULL DEFAULT '',
  marker_label TEXT NOT NULL DEFAULT 'Manual reviewer',
  finalised_at TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(attempt_id, question_id),
  CHECK (marks_awarded IS NULL OR (marks_awarded >= 0 AND marks_awarded <= marks_available))
);
CREATE INDEX IF NOT EXISTS idx_marking_reviews_status ON marking_reviews(status, created_at);

CREATE TABLE IF NOT EXISTS revision_recommendations (
  id TEXT PRIMARY KEY,
  attempt_id TEXT REFERENCES examination_attempts(id) ON DELETE SET NULL,
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
  priority TEXT NOT NULL CHECK (priority IN ('low','medium','high')),
  reason TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  recommended_actions_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','completed','dismissed')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_revision_subject_status ON revision_recommendations(subject_id, status, priority);

CREATE TABLE IF NOT EXISTS academic_resources (
  id TEXT PRIMARY KEY,
  subject_id TEXT REFERENCES subjects(id) ON DELETE SET NULL,
  exam_paper_id TEXT REFERENCES exam_papers(id) ON DELETE SET NULL,
  resource_type TEXT NOT NULL CHECK (resource_type IN ('exam_paper','memorandum','examiner_notes','revision_notes','topic_summary','performance_report')),
  title TEXT NOT NULL,
  mime_type TEXT NOT NULL DEFAULT 'application/pdf',
  storage_key TEXT,
  content_hash TEXT,
  status TEXT NOT NULL DEFAULT 'generated' CHECK (status IN ('generated','approved','archived','failed')),
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_resources_subject_type ON academic_resources(subject_id, resource_type, status);
