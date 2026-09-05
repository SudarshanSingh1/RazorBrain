-- Add explanation snapshot to investigation cases

ALTER TABLE investigation_cases ADD COLUMN explanation_snapshot TEXT DEFAULT NULL;
ALTER TABLE investigation_cases ADD COLUMN explanation_version TEXT DEFAULT NULL;
