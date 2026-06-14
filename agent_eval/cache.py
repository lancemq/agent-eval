"""Dataset caching layer for benchmark datasets.

Avoids re-downloading datasets (mmlu, gsm8k, humaneval) on every run.
Uses a simple file-based cache with SHA256-based keys.

Usage:
    from agent_eval.cache import DatasetCache

    cache = DatasetCache()
    data = cache.get_or_load("mmlu", loader_fn=lambda: load_from_hf("mmlu"))
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("agent_eval.cache")

DEFAULT_CACHE_DIR = os.path.expanduser("~/.cache/agent_eval/datasets")


class DatasetCache:
    """File-based dataset cache with TTL and size limits."""

    def __init__(
        self,
        cache_dir: str = DEFAULT_CACHE_DIR,
        ttl_seconds: int = 86400 * 7,  # 7 days
        max_size_mb: int = 1024,  # 1GB
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self.max_size_mb = max_size_mb

    def _cache_path(self, key: str, fmt: str = "pkl") -> Path:
        """Generate cache file path from key."""
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{key_hash}.{fmt}"

    def _meta_path(self, key: str) -> Path:
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{key_hash}.meta.json"

    def exists(self, key: str) -> bool:
        """Check if a cached entry exists and is not expired."""
        path = self._cache_path(key)
        meta_path = self._meta_path(key)
        if not path.exists() or not meta_path.exists():
            return False
        if self.ttl_seconds > 0:
            mtime = path.stat().st_mtime
            if time.time() - mtime > self.ttl_seconds:
                logger.debug(f"Cache entry '{key}' expired")
                return False
        return True

    def get(self, key: str) -> Optional[Any]:
        """Retrieve data from cache. Returns None if not found/expired."""
        if not self.exists(key):
            return None
        path = self._cache_path(key)
        try:
            if path.suffix == ".json":
                with open(path) as f:
                    return json.load(f)
            else:
                with open(path, "rb") as f:
                    return pickle.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache entry '{key}': {e}")
            return None

    def put(self, key: str, data: Any, fmt: str = "pkl") -> None:
        """Store data in cache."""
        path = self._cache_path(key, fmt)
        meta_path = self._meta_path(key)
        try:
            if fmt == "json":
                with open(path, "w") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                with open(path, "wb") as f:
                    pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            with open(meta_path, "w") as f:
                json.dump({
                    "key": key,
                    "cached_at": time.time(),
                    "size_bytes": path.stat().st_size,
                }, f)
            logger.debug(f"Cached '{key}' ({path.stat().st_size} bytes)")
            self._enforce_size_limit()
        except Exception as e:
            logger.warning(f"Failed to cache '{key}': {e}")

    def get_or_load(
        self,
        key: str,
        loader: Callable[[], Any],
        fmt: str = "pkl",
    ) -> Any:
        """Get from cache, or call loader and cache the result."""
        if self.exists(key):
            data = self.get(key)
            if data is not None:
                logger.debug(f"Cache hit: '{key}'")
                return data
        logger.debug(f"Cache miss: '{key}', loading...")
        data = loader()
        self.put(key, data, fmt)
        return data

    def invalidate(self, key: str) -> None:
        """Remove a specific cache entry."""
        path = self._cache_path(key)
        meta = self._meta_path(key)
        path.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)

    def clear(self) -> int:
        """Clear all cache entries. Returns number of entries removed."""
        count = 0
        for f in self.cache_dir.iterdir():
            if f.is_file():
                f.unlink()
                count += 1
        return count

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_size = 0
        entry_count = 0
        for f in self.cache_dir.iterdir():
            if f.is_file() and f.suffix == ".pkl":
                total_size += f.stat().st_size
                entry_count += 1
        return {
            "entries": entry_count,
            "size_mb": round(total_size / 1024 / 1024, 2),
            "cache_dir": str(self.cache_dir),
            "max_size_mb": self.max_size_mb,
        }

    def _enforce_size_limit(self) -> None:
        """Remove oldest entries if cache exceeds max size."""
        files = sorted(
            (f for f in self.cache_dir.iterdir() if f.suffix == ".pkl"),
            key=lambda f: f.stat().st_mtime,
        )
        total_size = sum(f.stat().st_size for f in files)
        max_bytes = self.max_size_mb * 1024 * 1024
        while total_size > max_bytes and files:
            oldest = files.pop(0)
            size = oldest.stat().st_size
            oldest.unlink(missing_ok=True)
            meta = oldest.with_suffix(".meta.json")
            meta.unlink(missing_ok=True)
            total_size -= size
            logger.debug(f"Evicted cache entry: {oldest.name}")


# Global singleton cache instance
_global_cache: Optional[DatasetCache] = None


def get_cache() -> DatasetCache:
    """Get the global cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = DatasetCache()
    return _global_cache
