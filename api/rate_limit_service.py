import time
import threading
import logging
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Rate limit exceeded")

class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate # tokens per second
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        
        # Refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
        
    def get_retry_after(self) -> int:
        # Time to get 1 token
        if self.refill_rate <= 0:
            return 60
        return int((1.0 - self.tokens) / self.refill_rate) + 1

class RateLimitService:
    def __init__(self, max_keys: int = 10000):
        self.buckets = OrderedDict()
        self.lock = threading.Lock()
        self.max_keys = max_keys
        
        # Defaults, can be overridden by env
        self.default_capacity = 100
        self.default_refill = 10.0 # 10 per sec

    def check_rate_limit(self, identity: str, endpoint: str, capacity: Optional[int] = None, refill_rate: Optional[float] = None):
        if not identity:
            return

        cap = capacity if capacity is not None else self.default_capacity
        refill = refill_rate if refill_rate is not None else self.default_refill
        
        key = f"{identity}:{endpoint}"
        
        with self.lock:
            bucket = self.buckets.get(key)
            if not bucket:
                if len(self.buckets) >= self.max_keys:
                    self.buckets.popitem(last=False) # remove oldest
                bucket = TokenBucket(cap, refill)
                self.buckets[key] = bucket
            else:
                self.buckets.move_to_end(key)
                
            if not bucket.consume(1):
                raise RateLimitExceeded(bucket.get_retry_after())

# Global instance for the app
rate_limiter = RateLimitService()
