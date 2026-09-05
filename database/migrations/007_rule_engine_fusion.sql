-- Migration: 007_rule_engine_fusion
-- Description: Adds rule policy and hybrid fusion tracking columns to serving_assessments.

ALTER TABLE serving_assessments ADD COLUMN rule_policy_version TEXT;
ALTER TABLE serving_assessments ADD COLUMN triggered_rules TEXT;
ALTER TABLE serving_assessments ADD COLUMN fusion_version TEXT;
ALTER TABLE serving_assessments ADD COLUMN fusion_result TEXT;
