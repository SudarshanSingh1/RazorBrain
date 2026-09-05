"""
Metrics Collection Service for RazorBrain Monitoring.

Provides a lightweight, in-process metrics collection layer.
Tracks operational events using bounded time-window counters
without requiring external infrastructure.
"""

import logging
import math
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Thread-safe in-memory metrics collector with periodic SQLite persistence.

    Tracks counters, gauges, and timing histograms in bounded sliding windows.
    The collector is designed to be called from hot paths (scoring, decisions)
    without adding meaningful latency.
    """

    def __init__(self, db_path: str = "razorbrain_api.db", flush_interval: int = 60):
        self._lock = threading.Lock()
        self._db_path = db_path
        self._flush_interval = flush_interval
        self._last_flush = time.monotonic()

        # In-memory counters for the current window
        self._counters: Dict[str, float] = defaultdict(float)
        # Timing samples (bounded to last N)
        self._timings: Dict[str, List[float]] = defaultdict(list)
        self._MAX_TIMING_SAMPLES = 500

    # ── Public API ────────────────────────────────────────────────────────────

    def increment(self, metric: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        if not math.isfinite(value):
            return
        with self._lock:
            key = self._make_key(metric, tags)
            self._counters[key] += value
        self._maybe_flush()

    def record_timing(self, metric: str, duration_ms: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a latency/timing observation."""
        if not math.isfinite(duration_ms):
            return
        with self._lock:
            key = self._make_key(metric, tags)
            samples = self._timings[key]
            if len(samples) >= self._MAX_TIMING_SAMPLES:
                samples.pop(0)
            samples.append(duration_ms)
        self._maybe_flush()

    def get_counter(self, metric: str, tags: Optional[Dict[str, str]] = None) -> float:
        key = self._make_key(metric, tags)
        with self._lock:
            return self._counters.get(key, 0.0)

    def get_timing_stats(self, metric: str, tags: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        key = self._make_key(metric, tags)
        with self._lock:
            samples = list(self._timings.get(key, []))
        if not samples:
            return {"count": 0, "avg_ms": 0.0, "max_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0}
        samples.sort()
        n = len(samples)
        return {
            "count": n,
            "avg_ms": sum(samples) / n,
            "max_ms": samples[-1],
            "p50_ms": samples[n // 2],
            "p95_ms": samples[int(n * 0.95)] if n >= 20 else samples[-1],
        }

    def get_all_counters(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._counters)

    def snapshot_and_reset(self) -> Dict[str, float]:
        """Atomically snapshot counters and reset them."""
        with self._lock:
            snapshot = dict(self._counters)
            self._counters.clear()
            return snapshot

    def flush_to_db(self) -> None:
        """Persist current counter values to SQLite for historical queries."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            items = list(self._counters.items())
        if not items:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            for key, value in items:
                cursor.execute(
                    "INSERT INTO monitoring_metrics (metric_name, metric_value, recorded_at) VALUES (?, ?, ?)",
                    (key, value, now),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Metrics flush failed (non-fatal): {e}")

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_key(metric: str, tags: Optional[Dict[str, str]] = None) -> str:
        if not tags:
            return metric
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{metric}|{tag_str}"

    def _maybe_flush(self) -> None:
        now = time.monotonic()
        if now - self._last_flush >= self._flush_interval:
            self._last_flush = now
            try:
                self.flush_to_db()
            except Exception:
                pass
