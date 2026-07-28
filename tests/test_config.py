import pytest
from unittest.mock import patch


def test_config_loads():
    env = {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_KEY": "test-key",
        "TELEGRAM_BOT_TOKEN": "123:test",
        "TELEGRAM_ALLOWED_USER_ID": "42",
    }
    with patch.dict("os.environ", env):
        import importlib
        import app.core.config as cfg
        importlib.reload(cfg)
        assert cfg.SUPABASE_URL == "https://test.supabase.co"
        assert cfg.TELEGRAM_ALLOWED_USER_ID == 42
