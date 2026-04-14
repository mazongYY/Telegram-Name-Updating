import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tg_username_update import (
    AppConfig,
    FileConfig,
    build_app_config,
    build_last_name,
    build_profile_payload,
    format_utc_offset,
    load_file_config,
    parse_proxy_from_file_config,
    save_file_config,
    seconds_until_next_run,
)


class FixedRandom:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


class TelegramNameUpdatingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.timezone = ZoneInfo("Asia/Shanghai")
        self.now = datetime(2026, 4, 8, 10, 35, 12, 250000, tzinfo=self.timezone)
        self.config = AppConfig(
            api_id=1,
            api_hash="hash",
            phone_number="+8613800000000",
            timezone=self.timezone,
            first_name="Tester",
            last_name_prefix="[",
            last_name_suffix="]",
        )

    def test_format_utc_offset(self) -> None:
        self.assertEqual(format_utc_offset(timedelta(hours=8)), "UTC+8")
        self.assertEqual(format_utc_offset(timedelta(hours=-5, minutes=-30)), "UTC-05:30")
        self.assertEqual(format_utc_offset(None), "UTC")

    def test_seconds_until_next_run(self) -> None:
        wait_seconds = seconds_until_next_run(self.now, 30)
        self.assertAlmostEqual(wait_seconds, 17.75, places=2)

    def test_build_last_name_time_bucket(self) -> None:
        value = build_last_name(self.now, FixedRandom(0.05))
        self.assertIn("10时35分", value)

    def test_build_last_name_weekday_bucket_has_no_period(self) -> None:
        value = build_last_name(self.now, FixedRandom(0.20))
        self.assertIn("Wed", value)
        self.assertNotIn("PM", value)
        self.assertNotIn("AM", value)

    def test_build_last_name_simple_time_bucket(self) -> None:
        value = build_last_name(self.now, FixedRandom(0.40))
        self.assertEqual(value[:5], "10:35")
        self.assertNotIn("UTC+8", value)

    def test_build_last_name_fun_bucket(self) -> None:
        value = build_last_name(self.now, FixedRandom(0.95))
        self.assertTrue(value)

    def test_build_profile_payload_applies_prefix_suffix(self) -> None:
        payload = build_profile_payload(self.config, self.now, FixedRandom(0.05))
        self.assertEqual(payload["first_name"], "Tester")
        self.assertTrue(payload["last_name"].startswith("["))
        self.assertTrue(payload["last_name"].endswith("]"))

    def test_parse_proxy_from_file_config_returns_none(self) -> None:
        file_config = FileConfig(api_id=1, api_hash="hash", phone_number="+8613800000000")
        self.assertIsNone(parse_proxy_from_file_config(file_config))

    def test_parse_proxy_from_file_config_builds_dict(self) -> None:
        file_config = FileConfig(
            api_id=1,
            api_hash="hash",
            phone_number="+8613800000000",
            proxy_type="socks5",
            proxy_host="127.0.0.1",
            proxy_port=1080,
            proxy_username="user",
            proxy_password="pass",
            proxy_rdns=False,
        )
        proxy = parse_proxy_from_file_config(file_config)
        self.assertIsNotNone(proxy)
        self.assertEqual(proxy["proxy_type"], "socks5")
        self.assertEqual(proxy["addr"], "127.0.0.1")
        self.assertEqual(proxy["port"], 1080)
        self.assertEqual(proxy["username"], "user")
        self.assertEqual(proxy["password"], "pass")
        self.assertFalse(proxy["rdns"])

    def test_save_and_load_file_config(self) -> None:
        file_config = FileConfig(
            api_id=24838427,
            api_hash="hash",
            phone_number="+8617000000000",
            timezone="Asia/Shanghai",
            session_name="api_auth",
            proxy_type="socks5",
            proxy_host="127.0.0.1",
            proxy_port=7897,
            log_level="DEBUG",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.local.json"
            save_file_config(config_path, file_config)
            loaded = load_file_config(config_path)
            self.assertEqual(loaded.api_id, 24838427)
            self.assertEqual(loaded.phone_number, "+8617000000000")
            self.assertEqual(loaded.proxy_port, 7897)
            self.assertEqual(loaded.log_level, "DEBUG")

            raw = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["phone_number"], "+8617000000000")

    def test_build_app_config(self) -> None:
        file_config = FileConfig(
            api_id=24838427,
            api_hash="hash",
            phone_number="+8617000000000",
            timezone="Asia/Shanghai",
            session_name="api_auth",
            update_interval=45,
            proxy_type="socks5",
            proxy_host="127.0.0.1",
            proxy_port=7897,
            dry_run=True,
        )
        app_config = build_app_config(file_config)
        self.assertEqual(app_config.api_id, 24838427)
        self.assertEqual(app_config.phone_number, "+8617000000000")
        self.assertEqual(app_config.update_interval, 45)
        self.assertTrue(app_config.dry_run)
        self.assertEqual(app_config.proxy["port"], 7897)


if __name__ == "__main__":
    unittest.main()
