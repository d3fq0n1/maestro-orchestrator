import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from maestro.keyring import (
    PROVIDERS,
    KeyStatus,
    mask_key,
    get_key,
    list_keys,
    set_key,
    remove_key,
    validate_key,
    validate_all_keys,
    _upsert_env_file,
    _remove_from_env_file,
)


class TestMaskKey(unittest.TestCase):
    """Verify key masking for display."""

    def test_empty_string(self):
        self.assertEqual(mask_key(""), "")

    def test_short_key(self):
        result = mask_key("abc")
        self.assertEqual(result, "ab*")
        self.assertNotIn("c", result[2:])

    def test_normal_key(self):
        key = "sk-abc123xyz789end"
        masked = mask_key(key)
        self.assertTrue(masked.startswith("sk-a"))
        self.assertTrue(masked.endswith("end"))
        self.assertIn("*", masked)
        # Should not leak the middle
        self.assertNotIn("123xyz", masked)

    def test_exact_boundary(self):
        # 10 chars -> short path
        masked = mask_key("1234567890")
        self.assertEqual(masked[:2], "12")

    def test_long_key(self):
        key = "sk-ant-api03-abcdefgh12345678"
        masked = mask_key(key)
        self.assertEqual(masked[:4], "sk-a")
        self.assertEqual(masked[-4:], "5678")


class TestEnvFileHelpers(unittest.TestCase):
    """Verify .env file read/write operations."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.env_path = Path(self._tmpdir) / ".env"

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_upsert_creates_new_file(self):
        _upsert_env_file(self.env_path, "TEST_KEY", "value123")
        self.assertTrue(self.env_path.exists())
        content = self.env_path.read_text()
        self.assertIn("TEST_KEY=value123", content)

    def test_upsert_updates_existing_key(self):
        self.env_path.write_text("TEST_KEY=old_value\nOTHER=keep\n")
        _upsert_env_file(self.env_path, "TEST_KEY", "new_value")
        content = self.env_path.read_text()
        self.assertIn("TEST_KEY=new_value", content)
        self.assertNotIn("old_value", content)
        self.assertIn("OTHER=keep", content)

    def test_upsert_appends_new_key(self):
        self.env_path.write_text("EXISTING=yes\n")
        _upsert_env_file(self.env_path, "NEW_KEY", "added")
        content = self.env_path.read_text()
        self.assertIn("EXISTING=yes", content)
        self.assertIn("NEW_KEY=added", content)

    def test_remove_key(self):
        self.env_path.write_text("KEEP=yes\nREMOVE_ME=gone\nALSO_KEEP=yes\n")
        _remove_from_env_file(self.env_path, "REMOVE_ME")
        content = self.env_path.read_text()
        self.assertNotIn("REMOVE_ME", content)
        self.assertIn("KEEP=yes", content)
        self.assertIn("ALSO_KEEP=yes", content)

    def test_remove_from_nonexistent_file(self):
        # Should not raise
        _remove_from_env_file(Path(self._tmpdir) / "nope.env", "KEY")


class TestKeyOperations(unittest.TestCase):
    """Verify in-memory key get/set/remove/list."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.env_path = Path(self._tmpdir) / ".env"
        # Save and clear all provider env vars
        self._saved = {}
        for info in PROVIDERS.values():
            var = info["env_var"]
            self._saved[var] = os.environ.pop(var, None)

    def tearDown(self):
        import shutil
        # Restore original env vars
        for var, val in self._saved.items():
            if val is not None:
                os.environ[var] = val
            else:
                os.environ.pop(var, None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_get_key_missing(self):
        self.assertIsNone(get_key("openai"))

    def test_set_and_get_key(self):
        status = set_key("openai", "sk-test-key-123", env_path=self.env_path)
        self.assertTrue(status.configured)
        self.assertEqual(status.provider, "openai")
        self.assertIn("*", status.masked_value)

        # Should be in os.environ now
        self.assertEqual(get_key("openai"), "sk-test-key-123")

        # Should be in the .env file
        content = self.env_path.read_text()
        self.assertIn("OPENAI_API_KEY=sk-test-key-123", content)

    def test_remove_key(self):
        set_key("anthropic", "sk-ant-test", env_path=self.env_path)
        self.assertEqual(get_key("anthropic"), "sk-ant-test")

        status = remove_key("anthropic", env_path=self.env_path)
        self.assertFalse(status.configured)
        self.assertIsNone(get_key("anthropic"))

    def test_list_keys_all_missing(self):
        statuses = list_keys()
        self.assertEqual(len(statuses), len(PROVIDERS))
        for s in statuses:
            self.assertFalse(s.configured)

    def test_list_keys_some_configured(self):
        os.environ["OPENAI_API_KEY"] = "sk-test123"
        statuses = list_keys()
        openai_status = [s for s in statuses if s.provider == "openai"][0]
        self.assertTrue(openai_status.configured)
        anthropic_status = [s for s in statuses if s.provider == "anthropic"][0]
        self.assertFalse(anthropic_status.configured)

    def test_set_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            set_key("unknown_provider", "key")

    def test_remove_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            remove_key("unknown_provider")

    def test_placeholder_values_not_configured(self):
        os.environ["OPENAI_API_KEY"] = "your-openai-key-here"
        statuses = list_keys()
        openai_status = [s for s in statuses if s.provider == "openai"][0]
        self.assertFalse(openai_status.configured)


class TestKeyValidation(unittest.TestCase):
    """Verify validate_key returns correct structure (without hitting real APIs)."""

    def setUp(self):
        self._saved = {}
        for info in PROVIDERS.values():
            var = info["env_var"]
            self._saved[var] = os.environ.pop(var, None)

    def tearDown(self):
        for var, val in self._saved.items():
            if val is not None:
                os.environ[var] = val
            else:
                os.environ.pop(var, None)

    def test_validate_unconfigured_key(self):
        status = asyncio.run(validate_key("openai"))
        self.assertFalse(status.configured)
        self.assertFalse(status.valid)
        self.assertIn("not configured", status.error)

    def test_validate_all_returns_all_providers(self):
        statuses = asyncio.run(validate_all_keys())
        self.assertEqual(len(statuses), len(PROVIDERS))
        providers = {s.provider for s in statuses}
        self.assertEqual(providers, set(PROVIDERS.keys()))

    def test_validate_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            asyncio.run(validate_key("nonexistent"))


class TestProviderRegistry(unittest.TestCase):
    """Verify the PROVIDERS constant is well-formed."""

    def test_all_providers_have_required_fields(self):
        for name, info in PROVIDERS.items():
            self.assertIn("env_var", info, f"{name} missing env_var")
            self.assertIn("label", info, f"{name} missing label")
            self.assertIn("test_url", info, f"{name} missing test_url")

    def test_provider_count(self):
        self.assertEqual(len(PROVIDERS), 4)


if __name__ == "__main__":
    unittest.main()
