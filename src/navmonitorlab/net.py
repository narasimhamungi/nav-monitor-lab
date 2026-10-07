"""One place for network access: fetch, cache the raw bytes, record a hash.

Raw downloads go to a cache directory that is not committed to git (docs/sources.md explains why).
The manifest of what was fetched, when, and its sha256 is committed.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (compatible; nav-monitor-lab/0.1; research use)"


class FetchError(RuntimeError):
    pass


class Fetcher:
    """Fetches URLs. Tests replace `transport` so no test ever touches the network."""

    def __init__(self, cache_dir: Path | None = None, user_agent: str = USER_AGENT, timeout: int = 30,
                 pause_seconds: float = 0.5, transport=None):
        self.cache_dir = cache_dir
        self.user_agent = user_agent
        self.timeout = timeout
        self.pause = pause_seconds
        self.transport = transport or self._urllib
        self.log: list[dict] = []

    def _urllib(self, url: str, data: bytes | None, headers: dict) -> bytes:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise FetchError(f"HTTP {e.code} from {url}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FetchError(f"could not reach {url}: {e}") from e

    def get(self, url: str, *, data: dict | None = None, headers: dict | None = None, label: str = "") -> bytes:
        h = {"User-Agent": self.user_agent, "Accept": "*/*"}
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8"); h["Content-Type"] = "application/json"
        h.update(headers or {})
        raw = self.transport(url, body, h)
        digest = hashlib.sha256(raw).hexdigest()
        entry = {"url": url, "label": label, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "sha256": digest, "bytes": len(raw)}
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{digest[:16]}.bin").write_bytes(raw)
            entry["cache_file"] = f"{digest[:16]}.bin"
        self.log.append(entry)
        if self.pause and self.transport == self._urllib:
            time.sleep(self.pause)
        return raw

    def text(self, url: str, **kw) -> str:
        raw = self.get(url, **kw)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
