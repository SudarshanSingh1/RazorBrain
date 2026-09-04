-- Create evaluation_feedback table to capture ground truth
CREATE TABLE evaluation_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id TEXT NOT NULL UNIQUE,
    transaction_id TEXT NOT NULL,
    ground_truth TEXT NOT NULL,
    label_source TEXT NOT NULL,
    evaluation_outcome TEXT NOT NULL,
    notes TEXT,
    labeled_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (assessment_id) REFERENCES risk_assessments(assessment_id)
);

CREATE INDEX idx_evaluation_feedback_assessment_id ON evaluation_feedback(assessment_id);
CREATE INDEX idx_evaluation_feedback_transaction_id ON evaluation_feedback(transaction_id);
CREATE INDEX idx_evaluation_feedback_labeled_at ON evaluation_feedback(labeled_at);
CREATE INDEX idx_evaluation_feedback_ground_truth ON evaluation_feedback(ground_truth);
