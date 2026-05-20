"""Shared thresholds for cache performance tests."""

from __future__ import annotations

# Cached path should be at least this many times faster than a simulated cold path.
MIN_CACHE_SPEEDUP_RATIO = 3.0

# Simulated cold-path work (repository / executor) in seconds.
SIMULATED_COLD_LATENCY_S = 0.012

# Upper bound for a cache hit after warm-up (milliseconds); guards regressions.
MAX_CACHE_HIT_MS = 25.0
