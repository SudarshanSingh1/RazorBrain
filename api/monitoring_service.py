"""
Monitoring Evaluation Service for RazorBrain.

Evaluates configurable alert conditions against current metrics
and system state. Separated from route handlers for testability.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.connection import get_connection

logger = logging.getLogger(__name__)


# ── Default Thresholds (configurable) ─────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    # Fraud activity
    "fraud_high_risk_rate": 0.30,          # % of HIGH-risk transactions in window
    "fraud_high_risk_count": 10,           # absolute count of HIGH-risk txns
    "fraud_decline_rate": 0.25,            # decline rate threshold

    # Decision rates
    "decision_review_rate": 0.40,          # review rate threshold
    "decision_step_up_rate": 0.20,
    "decision_decline_rate": 0.25,

    # Review queue
    "queue_open_cases": 50,                # max open cases before alert
    "queue_oldest_case_hours": 48,         # oldest unresolved case age in hours

    # API health
    "api_error_rate": 0.10,                # 10% error rate
    "api_avg_latency_ms": 2000,            # 2 second average latency

    # Data quality
    "data_quality_missing_rate": 0.15,     # 15% missing field rate

    # Feedback quality
    "feedback_false_positive_rate": 0.50,  # 50% FP rate among labeled

    # Drift
    "drift_psi_threshold": 0.25,           # PSI threshold for HIGH drift
}


class MonitoringService:
    """
    Evaluates monitoring conditions and delegates alert creation
    to the AlertService.
    """

    def __init__(self, db_path: str = "razorbrain_api.db",
                 thresholds: Optional[Dict[str, float]] = None):
        self._db_path = db_path
        self._thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    @property
    def thresholds(self) -> Dict[str, float]:
        return dict(self._thresholds)

    def evaluate_all(self, metrics_collector=None) -> List[Dict[str, Any]]:
        """
        Run all monitoring evaluations and return a list of alert
        condition dicts that should be created/updated.

        Each dict has the shape expected by AlertService.create_or_update_alert().
        """
        alerts: List[Dict[str, Any]] = []

        try:
            alerts.extend(self._evaluate_fraud_activity())
        except Exception as e:
            logger.warning(f"Fraud activity evaluation failed (non-fatal): {e}")

        try:
            alerts.extend(self._evaluate_decision_rates())
        except Exception as e:
            logger.warning(f"Decision rate evaluation failed (non-fatal): {e}")

        try:
            alerts.extend(self._evaluate_review_queue())
        except Exception as e:
            logger.warning(f"Review queue evaluation failed (non-fatal): {e}")

        try:
            alerts.extend(self._evaluate_api_health(metrics_collector))
        except Exception as e:
            logger.warning(f"API health evaluation failed (non-fatal): {e}")

        try:
            alerts.extend(self._evaluate_feedback_quality())
        except Exception as e:
            logger.warning(f"Feedback quality evaluation failed (non-fatal): {e}")

        return alerts

    # ── A. Fraud Activity ─────────────────────────────────────────────────

    def _evaluate_fraud_activity(self) -> List[Dict[str, Any]]:
        alerts = []
        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            # Count recent serving assessments (last 1 hour)
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN risk = 'HIGH' THEN 1 ELSE 0 END) as high_risk,
                    SUM(CASE WHEN decision = 'DECLINE' THEN 1 ELSE 0 END) as declined
                FROM serving_assessments
                WHERE created_at >= datetime('now', '-1 hour')
            """)
            row = cursor.fetchone()
            total = row["total"] or 0

            if total > 0:
                high_risk = row["high_risk"] or 0
                declined = row["declined"] or 0
                high_risk_rate = high_risk / total
                decline_rate = declined / total

                # High risk spike
                if high_risk >= self._thresholds["fraud_high_risk_count"] or \
                   high_risk_rate >= self._thresholds["fraud_high_risk_rate"]:
                    alerts.append({
                        "alert_type": "FRAUD_SPIKE",
                        "severity": "CRITICAL" if high_risk_rate >= 0.50 else "WARNING",
                        "category": "FRAUD",
                        "title": "Fraud Risk Spike Detected",
                        "message": f"{high_risk} HIGH-risk transactions in the last hour ({high_risk_rate:.1%} of {total} total).",
                        "metric_name": "high_risk_rate_1h",
                        "metric_value": high_risk_rate,
                        "threshold": self._thresholds["fraud_high_risk_rate"],
                        "metadata": {"high_risk_count": high_risk, "total_transactions": total, "window": "1h"},
                    })

                # High decline rate
                if decline_rate >= self._thresholds["fraud_decline_rate"]:
                    alerts.append({
                        "alert_type": "HIGH_DECLINE_RATE",
                        "severity": "WARNING",
                        "category": "FRAUD",
                        "title": "High Decline Rate",
                        "message": f"Decline rate is {decline_rate:.1%} over the last hour ({declined}/{total}).",
                        "metric_name": "decline_rate_1h",
                        "metric_value": decline_rate,
                        "threshold": self._thresholds["fraud_decline_rate"],
                        "metadata": {"declined_count": declined, "total_transactions": total, "window": "1h"},
                    })
        finally:
            conn.close()

        return alerts

    # ── B. Decision Rates ─────────────────────────────────────────────────

    def _evaluate_decision_rates(self) -> List[Dict[str, Any]]:
        alerts = []
        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT decision, COUNT(*) as cnt
                FROM serving_assessments
                WHERE created_at >= datetime('now', '-1 hour')
                GROUP BY decision
            """)
            rows = cursor.fetchall()
            counts = {r["decision"]: r["cnt"] for r in rows}
            total = sum(counts.values())

            if total < 5:
                return alerts

            for decision, threshold_key, title in [
                ("REVIEW", "decision_review_rate", "High Review Rate"),
                ("STEP_UP", "decision_step_up_rate", "High Step-Up Rate"),
                ("DECLINE", "decision_decline_rate", "High Decline Rate (Decision)"),
            ]:
                count = counts.get(decision, 0)
                rate = count / total
                if rate >= self._thresholds[threshold_key]:
                    alerts.append({
                        "alert_type": f"HIGH_{decision}_RATE",
                        "severity": "WARNING",
                        "category": "FRAUD",
                        "title": title,
                        "message": f"{decision} rate is {rate:.1%} ({count}/{total}) in the last hour.",
                        "metric_name": f"{decision.lower()}_rate_1h",
                        "metric_value": rate,
                        "threshold": self._thresholds[threshold_key],
                        "metadata": {"decision_counts": counts, "total": total, "window": "1h"},
                    })
        finally:
            conn.close()

        return alerts

    # ── C. Review Queue Backlog ───────────────────────────────────────────

    def _evaluate_review_queue(self) -> List[Dict[str, Any]]:
        alerts = []
        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            # Open investigation cases
            cursor.execute("""
                SELECT COUNT(*) as open_count,
                       MIN(created_at) as oldest_created
                FROM investigation_cases
                WHERE status IN ('OPEN', 'INVESTIGATING', 'ESCALATED')
            """)
            row = cursor.fetchone()
            open_count = row["open_count"] or 0
            oldest_created = row["oldest_created"]

            if open_count >= self._thresholds["queue_open_cases"]:
                alerts.append({
                    "alert_type": "REVIEW_QUEUE_BACKLOG",
                    "severity": "WARNING" if open_count < self._thresholds["queue_open_cases"] * 2 else "CRITICAL",
                    "category": "QUEUE",
                    "title": "Review Queue Backlog High",
                    "message": f"{open_count} open investigation cases exceed threshold of {int(self._thresholds['queue_open_cases'])}.",
                    "metric_name": "open_case_count",
                    "metric_value": float(open_count),
                    "threshold": self._thresholds["queue_open_cases"],
                    "metadata": {"open_case_count": open_count, "oldest_case_created": oldest_created},
                })

            # Oldest case age
            if oldest_created:
                try:
                    oldest_dt = datetime.fromisoformat(oldest_created.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    age_hours = (now - oldest_dt).total_seconds() / 3600
                    if age_hours >= self._thresholds["queue_oldest_case_hours"]:
                        alerts.append({
                            "alert_type": "STALE_CASE",
                            "severity": "WARNING",
                            "category": "QUEUE",
                            "title": "Stale Investigation Case",
                            "message": f"Oldest unresolved case is {age_hours:.1f} hours old (threshold: {self._thresholds['queue_oldest_case_hours']}h).",
                            "metric_name": "oldest_case_age_hours",
                            "metric_value": age_hours,
                            "threshold": self._thresholds["queue_oldest_case_hours"],
                            "metadata": {"oldest_case_created": oldest_created, "age_hours": round(age_hours, 1)},
                        })
                except (ValueError, TypeError):
                    pass
        finally:
            conn.close()

        return alerts

    # ── D/E. API Health (from MetricsCollector) ───────────────────────────

    def _evaluate_api_health(self, metrics_collector=None) -> List[Dict[str, Any]]:
        alerts = []
        if not metrics_collector:
            return alerts

        request_count = metrics_collector.get_counter("api.request_count")
        error_count = metrics_collector.get_counter("api.error_count")
        timing = metrics_collector.get_timing_stats("api.request_latency")

        if request_count > 0:
            error_rate = error_count / request_count
            if error_rate >= self._thresholds["api_error_rate"]:
                alerts.append({
                    "alert_type": "HIGH_API_ERROR_RATE",
                    "severity": "CRITICAL" if error_rate >= 0.25 else "WARNING",
                    "category": "API",
                    "title": "High API Error Rate",
                    "message": f"API error rate is {error_rate:.1%} ({int(error_count)}/{int(request_count)}).",
                    "metric_name": "api_error_rate",
                    "metric_value": error_rate,
                    "threshold": self._thresholds["api_error_rate"],
                    "metadata": {
                        "request_count": int(request_count),
                        "error_count": int(error_count),
                    },
                })

        if timing["count"] > 0 and timing["avg_ms"] >= self._thresholds["api_avg_latency_ms"]:
            alerts.append({
                "alert_type": "HIGH_API_LATENCY",
                "severity": "WARNING",
                "category": "API",
                "title": "High API Latency",
                "message": f"Average API latency is {timing['avg_ms']:.0f}ms (threshold: {self._thresholds['api_avg_latency_ms']}ms).",
                "metric_name": "api_avg_latency_ms",
                "metric_value": timing["avg_ms"],
                "threshold": self._thresholds["api_avg_latency_ms"],
                "metadata": timing,
            })

        return alerts

    # ── I. Feedback Quality ───────────────────────────────────────────────

    def _evaluate_feedback_quality(self) -> List[Dict[str, Any]]:
        alerts = []
        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            # Check evaluation feedback table
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN evaluation_outcome = 'FP' THEN 1 ELSE 0 END) as fp,
                    SUM(CASE WHEN evaluation_outcome = 'FN' THEN 1 ELSE 0 END) as fn
                FROM evaluation_feedback
                WHERE labeled_at >= datetime('now', '-24 hours')
            """)
            row = cursor.fetchone()
            total = row["total"] or 0
            fp = row["fp"] or 0

            if total >= 5:
                fp_rate = fp / total
                if fp_rate >= self._thresholds["feedback_false_positive_rate"]:
                    alerts.append({
                        "alert_type": "HIGH_FALSE_POSITIVE_RATE",
                        "severity": "WARNING",
                        "category": "FEEDBACK",
                        "title": "High False Positive Rate",
                        "message": f"False positive rate is {fp_rate:.1%} ({fp}/{total}) in the last 24 hours.",
                        "metric_name": "false_positive_rate_24h",
                        "metric_value": fp_rate,
                        "threshold": self._thresholds["feedback_false_positive_rate"],
                        "metadata": {"fp_count": fp, "total_labeled": total, "window": "24h"},
                    })
        except Exception:
            pass  # Table may not exist in test DBs
        finally:
            conn.close()

        return alerts

    # ── Monitoring Summary ────────────────────────────────────────────────

    def get_monitoring_summary(self, alert_service=None, metrics_collector=None) -> Dict[str, Any]:
        """Build an aggregated monitoring summary."""
        summary: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_health": "HEALTHY",
            "recent_alert_count": 0,
            "critical_alert_count": 0,
            "open_alert_count": 0,
            "review_queue_size": 0,
            "recent_error_rate": 0.0,
            "recent_latency_ms": 0.0,
            "fraud_activity": {},
        }

        # Alert counts
        if alert_service:
            try:
                counts = alert_service.get_alert_counts()
                summary["open_alert_count"] = counts.get("open", 0) + counts.get("acknowledged", 0)
                summary["critical_alert_count"] = counts.get("critical_active", 0)
                summary["recent_alert_count"] = counts.get("total", 0)

                if counts.get("critical_active", 0) > 0:
                    summary["system_health"] = "CRITICAL"
                elif counts.get("warning_active", 0) > 0:
                    summary["system_health"] = "DEGRADED"
            except Exception as e:
                logger.warning(f"Alert counts unavailable: {e}")

        # Review queue
        try:
            conn = get_connection(self._db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM investigation_cases
                WHERE status IN ('OPEN', 'INVESTIGATING', 'ESCALATED')
            """)
            row = cursor.fetchone()
            summary["review_queue_size"] = row["cnt"] or 0
            conn.close()
        except Exception:
            pass

        # API metrics
        if metrics_collector:
            try:
                req = metrics_collector.get_counter("api.request_count")
                err = metrics_collector.get_counter("api.error_count")
                if req > 0:
                    summary["recent_error_rate"] = round(err / req, 4)
                timing = metrics_collector.get_timing_stats("api.request_latency")
                summary["recent_latency_ms"] = round(timing.get("avg_ms", 0.0), 1)
            except Exception:
                pass

        # Fraud activity summary
        try:
            conn = get_connection(self._db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN risk = 'HIGH' THEN 1 ELSE 0 END) as high_risk,
                    SUM(CASE WHEN decision = 'DECLINE' THEN 1 ELSE 0 END) as declined
                FROM serving_assessments
                WHERE created_at >= datetime('now', '-1 hour')
            """)
            row = cursor.fetchone()
            total = row["total"] or 0
            summary["fraud_activity"] = {
                "transactions_1h": total,
                "high_risk_1h": row["high_risk"] or 0,
                "declined_1h": row["declined"] or 0,
            }
            conn.close()
        except Exception:
            pass

        return summary
