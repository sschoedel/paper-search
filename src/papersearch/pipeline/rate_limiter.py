"""Rate limiting utilities."""

import asyncio
import time
from typing import Optional


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate: float, burst: Optional[int] = None):
        """Initialize rate limiter.

        Args:
            rate: Requests per second
            burst: Maximum burst size (defaults to rate)
        """
        self.rate = rate
        self.burst = burst or int(rate)
        self.tokens = float(self.burst)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a request (blocking)."""
        async with self.lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update

                # Add tokens based on elapsed time
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                # Wait for next token
                wait_time = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
