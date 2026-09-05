-- Migration: 006_decision_engine
-- Description: Adds decision_trace to serving_assessments for the 4-tier Decision Engine.

ALTER TABLE serving_assessments ADD COLUMN decision_trace TEXT;
