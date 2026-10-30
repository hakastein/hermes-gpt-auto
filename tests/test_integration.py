"""Native provider discovery and context lookup against an isolated Hermes home."""
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hermes_constants import set_hermes_home_override, reset_hermes_home_override

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://chatgpt.com/backend-api/codex"


class NativeIntegrationTests(unittest.TestCase):
    def test_discovered_profile_resolves_plain_model_without_changing_auth_or_picker(self):
        from providers import get_provider_profile
        from providers.base import ProviderProfile
        from agent.model_metadata import get_model_context_length
        from hermes_cli import codex_models

        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as home:
            target = Path(home) / "plugins" / "gpt-auto"
            target.mkdir(parents=True)
            for name in ("__init__.py", "plugin.yaml"):
                shutil.copy2(ROOT / name, target / name)
            binding = set_hermes_home_override(home)
            try:
                before = codex_models._finalize_codex_models
                profile = get_provider_profile("openai-codex")
                self.assertEqual(type(profile).__name__, "AutoContextCodex")
                self.assertEqual((profile.base_url, profile.api_mode, profile.auth_type),
                                 (BASE, "codex_responses", "oauth_external"))
                response = SimpleNamespace(status=200, json=lambda: {"models": [
                    {"slug": "gpt-6.1-sol", "context_window": 500000, "max_context_window": 872000}
                ]})
                with patch("hermes_cli.plugin_provider_requests.credentialed_provider_request", return_value=response) as http:
                    self.assertEqual(get_model_context_length("gpt-6.1-sol", base_url=BASE,
                                     provider="openai-codex", api_key="test-not-a-secret"), 872000)
                    self.assertEqual(get_model_context_length("gpt-6.1-sol", base_url=BASE,
                                     provider="openai-codex", config_context_length=300000), 300000)
                    self.assertEqual(http.call_count, 1)
                self.assertIs(codex_models._finalize_codex_models, before)
                other_binding = set_hermes_home_override(str(Path(home) / "other-profile"))
                try:
                    other = get_provider_profile("openai-codex")
                    self.assertIs(type(other), ProviderProfile)
                    self.assertIsNone(other.get_model_context_length("gpt-6.1-sol"))
                finally:
                    reset_hermes_home_override(other_binding)
            finally:
                reset_hermes_home_override(binding)


if __name__ == "__main__":
    unittest.main()
