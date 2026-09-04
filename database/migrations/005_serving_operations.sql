-- Migration: 005_serving_operations
-- Description: Adds tables and indexes required for operational hardening of the Razorpay Serving Model.

-- Table for serving feedback (ground truth)
CREATE TABLE IF NOT EXISTS serving_evaluation_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id TEXT NOT NULL UNIQUE,
    transaction_id TEXT NOT NULL,
    ground_truth TEXT NOT NULL,          -- FRAUD or LEGITIMATE
    label_source TEXT NOT NULL,          -- e.g., MANUAL_REVIEW, CHARGEBACK
    notes TEXT,
    labeled_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (assessment_id) REFERENCES serving_assessments(assessment_id)
);

CREATE INDEX IF NOT EXISTS idx_serving_feedback_assessment_id ON serving_evaluation_feedback(assessment_id);
CREATE INDEX IF NOT EXISTS idx_serving_feedback_labeled_at ON serving_evaluation_feedback(labeled_at);
CREATE INDEX IF NOT EXISTS idx_serving_feedback_ground_truth ON serving_evaluation_feedback(ground_truth);

-- Add review_status column to serving_assessments to support the Review Queue workflow
ALTER TABLE serving_assessments ADD COLUMN review_status TEXT DEFAULT 'PENDING';

-- By default, BLOCK and ALLOW do not require review, only REVIEW.
UPDATE serving_assessments SET review_status = 'NOT_REQUIRED' WHERE decision != 'REVIEW';

-- Index for the Review Queue (ordered by risk DESC for priority)
CREATE INDEX IF NOT EXISTS idx_serving_assessments_queue 
    ON serving_assessments(decision, review_status, risk DESC);
