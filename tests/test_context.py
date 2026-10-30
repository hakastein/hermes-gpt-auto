"""Behavior of the provider profile at the authenticated-catalog and state boundaries."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hermes_cli.plugins_state import PluginState
from hermes_constants import set_hermes_home_override, reset_hermes_home_override

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gpt_auto_tests", ROOT / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
# The unit tests inspect the registered profile without replacing a process-wide provider.
import sys
sys.modules[spec.name] = plugin
with patch("providers.register_provider"):
    spec.loader.exec_module(plugin)

MODEL = "gpt-6.1-sol"
IDENTITY = "account-a/user-a\n" + plugin.BASE_URL


class AutoContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        home = set_hermes_home_override(self.temp.name)
        self.addCleanup(reset_hermes_home_override, home)
        self.profile = plugin.AutoContextCodex(name="openai-codex")
        self.entries = [{"slug": MODEL, "context_window": 500000, "max_context_window": 872000}]
        response = SimpleNamespace(status=200, json=lambda: {"models": self.entries})
        self.response = response
        patcher = patch("hermes_cli.plugin_provider_requests.credentialed_provider_request", return_value=response)
        self.http = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(plugin.time, "time", return_value=10000)
        self.clock = patcher.start()
        self.addCleanup(patcher.stop)

    def resolve(self, model=MODEL):
        return self.profile.get_model_context_length(model)

    def expire(self):
        self.clock.return_value += 3601

    def test_plain_and_legacy_variant_get_maximum_with_one_catalog_read(self):
        self.assertEqual(self.resolve(), 872000)
        self.assertEqual(self.resolve(MODEL + "-900k"), 872000)
        self.assertEqual(self.http.call_count, 1)
        self.assertEqual(self.http.call_args.args[:2], ("openai-codex", "GET"))

    def test_future_model_and_maximum_above_900k_need_no_code_change(self):
        self.entries.append({"slug": "gpt-next", "context_window": 500000, "max_context_window": 1500000})
        self.assertEqual(self.resolve("gpt-next"), 1500000)

    def test_refresh_follows_both_increases_and_decreases(self):
        self.assertEqual(self.resolve(), 872000)
        for maximum in (1200000, 600000):
            self.entries[0]["max_context_window"] = maximum
            self.expire()
            self.assertEqual(self.resolve(), maximum)

    def test_missing_or_invalid_maximum_uses_advertised_window(self):
        for maximum in (None, True, -1, "2000000"):
            with self.subTest(maximum=maximum):
                self.entries[0]["max_context_window"] = maximum
                self.expire()
                self.assertEqual(self.resolve(), 500000)

    def test_invalid_rows_cannot_inject_bad_context_or_repaired_identifier(self):
        self.entries.extend([None, {"slug": "gpt-invalid", "context_window": True},
                             {"slug": " gpt-spaced", "max_context_window": 2000000}])
        self.assertIsNone(self.resolve("gpt-invalid"))
        self.assertIsNone(self.resolve("gpt-spaced"))
        self.assertEqual(self.resolve(), 872000)

    def test_outage_retains_success_across_profile_instance_and_retries_without_hammering(self):
        self.assertEqual(self.resolve(), 872000)
        self.profile = plugin.AutoContextCodex(name="openai-codex")
        self.response.status = 503
        self.expire()
        self.assertEqual(self.resolve(), 872000)
        calls = self.http.call_count
        self.assertEqual(self.resolve(), 872000)
        self.assertEqual(self.http.call_count, calls)
        self.response.status = 200
        self.entries[0]["max_context_window"] = 700000
        self.clock.return_value += 61
        self.assertEqual(self.resolve(), 700000)

    def test_outage_without_success_returns_none_for_native_fallback(self):
        self.http.side_effect = TimeoutError("offline")
        self.assertIsNone(self.resolve())

    def test_successful_removal_does_not_resurrect_old_model(self):
        self.assertEqual(self.resolve(), 872000)
        self.entries[:] = [{"slug": "gpt-other", "context_window": 300000}]
        self.expire()
        self.assertIsNone(self.resolve())

    def test_profile_cache_isolation(self):
        self.assertEqual(self.resolve(), 872000)
        self.http.side_effect = TimeoutError("offline")
        other = set_hermes_home_override(str(Path(self.temp.name) / "other"))
        try:
            self.assertIsNone(self.resolve())
        finally:
            reset_hermes_home_override(other)
        self.assertEqual(self.resolve(), 872000)

    def test_non_gpt_declines_without_request(self):
        self.assertIsNone(self.resolve("claude-opus-5-5"))
        self.http.assert_not_called()

    def test_disabled_plugin_declines_without_reading_catalog(self):
        with patch("hermes_cli.config.load_config_readonly", return_value={"plugins": {"disabled": ["gpt-auto"]}}):
            self.assertIsNone(self.resolve())
        self.http.assert_not_called()

    def test_state_corruption_does_not_stop_fresh_catalog_resolution(self):
        path = PluginState("gpt-auto").path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]")
        self.assertEqual(self.resolve(), 872000)


if __name__ == "__main__":
    unittest.main()
