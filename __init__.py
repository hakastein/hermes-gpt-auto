"""Automatic Codex context through the supported provider-profile extension."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from types import SimpleNamespace

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)
BASE_URL = "https://chatgpt.com/backend-api/codex"
CACHE_SECONDS = 3600
RETRY_SECONDS = 60


@dataclass
class AutoContextCodex(ProviderProfile):
    """Keep native auth, transport and model picker; override only context discovery."""

    def __post_init__(self):
        self._lock = threading.RLock()

    def get_model_context_length(self, model):
        from agent.model_metadata import strip_codex_context_variant_suffix
        from hermes_cli.plugins_state import PluginState
        from hermes_cli.config import load_config_readonly

        if "gpt-auto" in (load_config_readonly() or {}).get("plugins", {}).get("disabled", []):
            return None
        slug = strip_codex_context_variant_suffix(model).rsplit("/", 1)[-1]
        if not slug.startswith("gpt-"):
            return None
        state = PluginState("gpt-auto")
        # shortcut: one account on official Codex per profile; clear plugin data after changing accounts.
        key = "catalog"
        with self._lock:
            try:
                cached = state.get(key) or {}
            except (OSError, ValueError, RuntimeError):
                cached = {}
            if not isinstance(cached, dict):
                cached = {}
            windows = cached.get("windows", {})
            if not isinstance(windows, dict):
                windows = {}
            windows = {m: n for m, n in windows.items() if isinstance(m, str) and type(n) is int and n > 0}
            now = time.time()
            at = cached.get("checked_at", 0)
            ttl = RETRY_SECONDS if cached.get("failed") else CACHE_SECONDS
            fresh = type(at) in {int, float} and 0 <= now - at < ttl
            if not fresh:
                try:
                    windows = self._fetch_windows()
                    cached = {"windows": windows, "checked_at": time.time(), "failed": False}
                except Exception as exc:
                    # Preserve the last successful catalog during an outage.
                    logger.warning("gpt-auto: catalog unavailable (%s); using last-known context", type(exc).__name__)
                    cached = {"windows": windows, "checked_at": now, "failed": True}
                try:
                    state.set(key, cached)
                except (OSError, ValueError, RuntimeError):
                    logger.warning("gpt-auto: could not save context cache")
            return windows.get(slug)

    @staticmethod
    def _fetch_windows():
        from agent.model_metadata import fetch_codex_catalog_entries
        from hermes_cli.plugin_provider_requests import credentialed_provider_request

        def get(url):
            response = credentialed_provider_request("openai-codex", "GET", url, timeout=8)
            return SimpleNamespace(status_code=response.status, json=response.json)

        entries, status = fetch_codex_catalog_entries(get, base_url=BASE_URL)
        windows = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            model = entry.get("slug")
            if not isinstance(model, str) or not model.startswith("gpt-") or model != model.strip():
                continue
            maximum, advertised = entry.get("max_context_window"), entry.get("context_window")
            context = maximum if type(maximum) is int and maximum > 0 else advertised
            if type(context) is int and context > 0:
                windows[model] = context
        if status != 200 or not windows:
            raise RuntimeError("Codex catalog returned no valid GPT context windows")
        return windows


profile = AutoContextCodex(
    name="openai-codex", aliases=("codex", "openai_codex"), api_mode="codex_responses",
    env_vars=(), base_url=BASE_URL, auth_type="oauth_external",
)
register_provider(profile)
