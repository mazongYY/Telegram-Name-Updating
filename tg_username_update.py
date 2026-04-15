#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import os
import random
import signal
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, tzinfo
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from emoji import emojize
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError, SessionPasswordNeededError
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest


DEFAULT_CONFIG_PATH = Path("config.local.json")
DEFAULT_SESSION_NAME = "api_auth"


class RandomSource(Protocol):
    def random(self) -> float:
        ...


CLOCK_ALIASES = [
    "clock12",
    "clock1230",
    "clock1",
    "clock130",
    "clock2",
    "clock230",
    "clock3",
    "clock330",
    "clock4",
    "clock430",
    "clock5",
    "clock530",
    "clock6",
    "clock630",
    "clock7",
    "clock730",
    "clock8",
    "clock830",
    "clock9",
    "clock930",
    "clock10",
    "clock1030",
    "clock11",
    "clock1130",
]

DIZZY = emojize(":dizzy:", language="alias")
CAKE = emojize(":cake:", language="alias")

LOGGER = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def start_health_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    LOGGER.info("Health check server started on port %s", port)


@dataclass(slots=True)
class FileConfig:
    api_id: int
    api_hash: str
    phone_number: str
    timezone: str = "Asia/Shanghai"
    session_name: str = DEFAULT_SESSION_NAME
    update_interval: int = 30
    first_name: str | None = None
    username: str | None = None
    last_name_prefix: str = ""
    last_name_suffix: str = ""
    proxy_type: str | None = None
    proxy_host: str | None = None
    proxy_port: int | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None
    proxy_rdns: bool = True
    two_step_password: str | None = None
    run_on_start: bool = True
    reset_last_name_on_exit: bool = False
    dry_run: bool = False
    log_level: str = "INFO"


@dataclass(slots=True)
class AppConfig:
    api_id: int
    api_hash: str
    phone_number: str
    timezone: tzinfo
    session_name: str = DEFAULT_SESSION_NAME
    update_interval: int = 30
    first_name: str | None = None
    username: str | None = None
    last_name_prefix: str = ""
    last_name_suffix: str = ""
    proxy: dict[str, object] | None = None
    two_step_password: str | None = None
    run_on_start: bool = True
    reset_last_name_on_exit: bool = False
    dry_run: bool = False
    log_level: str = "INFO"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram 名称自动更新工具")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="配置文件路径，默认使用 config.local.json",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="重新生成配置文件后退出，不启动更新循环。",
    )
    return parser.parse_args()


def normalize_optional_text(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None


def prompt_required(label: str, *, secret: bool = False) -> str:
    if not sys.stdin.isatty():
        raise RuntimeError(f"{label} 未提供，且当前不是交互式终端。")

    prompt = f"{label}: "
    value = getpass.getpass(prompt) if secret else input(prompt)
    value = value.strip()
    if not value:
        raise RuntimeError(f"{label} 不能为空。")
    return value


def prompt_optional(label: str, *, secret: bool = False) -> str | None:
    if not sys.stdin.isatty():
        return None

    prompt = f"{label}（可留空）: "
    value = getpass.getpass(prompt) if secret else input(prompt)
    return normalize_optional_text(value)


def prompt_with_default(label: str, default: str) -> str:
    if not sys.stdin.isatty():
        return default

    value = input(f"{label} [{default}]: ").strip()
    return value or default


def prompt_bool(label: str, default: bool) -> bool:
    if not sys.stdin.isatty():
        return default

    suffix = "Y/n" if default else "y/N"
    value = input(f"{label} [{suffix}]: ").strip().lower()
    if not value:
        return default
    if value in {"y", "yes", "1", "true"}:
        return True
    if value in {"n", "no", "0", "false"}:
        return False
    raise RuntimeError(f"{label} 输入无效，请输入 y 或 n。")


def prompt_int(label: str, default: int | None = None) -> int:
    default_text = "" if default is None else f" [{default}]"
    raw = prompt_required(f"{label}{default_text}") if default is None else prompt_with_default(label, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{label} 必须是整数。") from exc


def resolve_timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(
            f"无法识别时区 {name!r}。请设置有效的 IANA 时区，例如 Asia/Shanghai。"
        ) from exc


def parse_proxy_from_file_config(config: FileConfig) -> dict[str, object] | None:
    if not config.proxy_host and not config.proxy_port:
        return None
    if not config.proxy_host or not config.proxy_port:
        raise RuntimeError("代理配置不完整，必须同时提供 proxy_host 和 proxy_port。")

    proxy: dict[str, object] = {
        "proxy_type": config.proxy_type or "socks5",
        "addr": config.proxy_host,
        "port": config.proxy_port,
        "rdns": config.proxy_rdns,
    }
    if config.proxy_username:
        proxy["username"] = config.proxy_username
    if config.proxy_password:
        proxy["password"] = config.proxy_password
    return proxy


def build_app_config(config: FileConfig) -> AppConfig:
    if config.update_interval <= 0:
        raise RuntimeError("update_interval 必须大于 0。")

    return AppConfig(
        api_id=config.api_id,
        api_hash=config.api_hash,
        phone_number=config.phone_number,
        timezone=resolve_timezone(config.timezone),
        session_name=config.session_name,
        update_interval=config.update_interval,
        first_name=config.first_name,
        username=config.username,
        last_name_prefix=config.last_name_prefix,
        last_name_suffix=config.last_name_suffix,
        proxy=parse_proxy_from_file_config(config),
        two_step_password=config.two_step_password,
        run_on_start=config.run_on_start,
        reset_last_name_on_exit=config.reset_last_name_on_exit,
        dry_run=config.dry_run,
        log_level=config.log_level.upper(),
    )


def load_file_config(config_path: Path) -> FileConfig:
    if not config_path.exists():
        raise RuntimeError(f"配置文件不存在：{config_path}")

    data = json.loads(config_path.read_text(encoding="utf-8"))
    return FileConfig(
        api_id=int(data["api_id"]),
        api_hash=str(data["api_hash"]),
        phone_number=str(data["phone_number"]),
        timezone=str(data.get("timezone", "Asia/Shanghai")),
        session_name=str(data.get("session_name", DEFAULT_SESSION_NAME)),
        update_interval=int(data.get("update_interval", 30)),
        first_name=normalize_optional_text(str(data.get("first_name", "") or "")),
        username=normalize_optional_text(str(data.get("username", "") or "")),
        last_name_prefix=str(data.get("last_name_prefix", "")),
        last_name_suffix=str(data.get("last_name_suffix", "")),
        proxy_type=normalize_optional_text(str(data.get("proxy_type", "") or "")),
        proxy_host=normalize_optional_text(str(data.get("proxy_host", "") or "")),
        proxy_port=int(data["proxy_port"]) if data.get("proxy_port") not in (None, "") else None,
        proxy_username=normalize_optional_text(str(data.get("proxy_username", "") or "")),
        proxy_password=normalize_optional_text(str(data.get("proxy_password", "") or "")),
        proxy_rdns=bool(data.get("proxy_rdns", True)),
        two_step_password=normalize_optional_text(str(data.get("two_step_password", "") or "")),
        run_on_start=bool(data.get("run_on_start", True)),
        reset_last_name_on_exit=bool(data.get("reset_last_name_on_exit", False)),
        dry_run=bool(data.get("dry_run", False)),
        log_level=str(data.get("log_level", "INFO")),
    )


def save_file_config(config_path: Path, config: FileConfig) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeError(f"环境变量 {name} 的布尔值无效：{value!r}")


def load_env_file_config() -> FileConfig | None:
    api_id_raw = os.getenv("TG_API_ID")
    api_hash = normalize_optional_text(os.getenv("TG_API_HASH", ""))
    phone_number = normalize_optional_text(os.getenv("TG_PHONE_NUMBER", ""))
    if api_id_raw is None or api_hash is None or phone_number is None:
        return None

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("环境变量 TG_API_ID 必须是整数。") from exc

    proxy_port_raw = normalize_optional_text(os.getenv("TG_PROXY_PORT", ""))
    proxy_port = int(proxy_port_raw) if proxy_port_raw else None

    return FileConfig(
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone_number,
        timezone=os.getenv("TG_TIMEZONE", "Asia/Shanghai"),
        session_name=os.getenv("TG_SESSION_NAME", DEFAULT_SESSION_NAME),
        update_interval=int(os.getenv("TG_UPDATE_INTERVAL", "30")),
        first_name=normalize_optional_text(os.getenv("TG_FIRST_NAME", "")),
        username=normalize_optional_text(os.getenv("TG_USERNAME", "")),
        last_name_prefix=os.getenv("TG_LAST_NAME_PREFIX", ""),
        last_name_suffix=os.getenv("TG_LAST_NAME_SUFFIX", ""),
        proxy_type=normalize_optional_text(os.getenv("TG_PROXY_TYPE", "")),
        proxy_host=normalize_optional_text(os.getenv("TG_PROXY_HOST", "")),
        proxy_port=proxy_port,
        proxy_username=normalize_optional_text(os.getenv("TG_PROXY_USERNAME", "")),
        proxy_password=normalize_optional_text(os.getenv("TG_PROXY_PASSWORD", "")),
        proxy_rdns=parse_bool_env("TG_PROXY_RDNS", True),
        two_step_password=normalize_optional_text(os.getenv("TG_TWO_STEP_PASSWORD", "")),
        run_on_start=parse_bool_env("TG_RUN_ON_START", True),
        reset_last_name_on_exit=parse_bool_env("TG_RESET_LAST_NAME_ON_EXIT", False),
        dry_run=parse_bool_env("TG_DRY_RUN", False),
        log_level=os.getenv("TG_LOG_LEVEL", "INFO"),
    )


def prompt_create_file_config(config_path: Path) -> FileConfig:
    print(f"未找到配置文件，开始初始化：{config_path}")
    api_id = prompt_int("TG_API_ID")
    api_hash = prompt_required("TG_API_HASH", secret=True)
    phone_number = prompt_required("Telegram 手机号")

    timezone_name = prompt_with_default("时区", "Asia/Shanghai")
    resolve_timezone(timezone_name)
    session_name = prompt_with_default("session 名称", DEFAULT_SESSION_NAME)
    update_interval = prompt_int("更新间隔（秒）", 30)

    first_name = prompt_optional("固定 first_name")
    username = prompt_optional("固定 username")
    last_name_prefix = prompt_optional("last_name 前缀") or ""
    last_name_suffix = prompt_optional("last_name 后缀") or ""

    use_proxy = prompt_bool("是否使用代理", True)
    proxy_type = None
    proxy_host = None
    proxy_port = None
    proxy_username = None
    proxy_password = None
    proxy_rdns = True
    if use_proxy:
        proxy_type = prompt_with_default("代理类型", "socks5")
        proxy_host = prompt_required("代理地址")
        proxy_port = prompt_int("代理端口")
        proxy_username = prompt_optional("代理用户名")
        proxy_password = prompt_optional("代理密码", secret=True)
        proxy_rdns = prompt_bool("是否由代理解析 DNS", True)

    save_password = prompt_bool("是否将二次验证密码保存到配置文件（不推荐）", False)
    two_step_password = prompt_optional("Telegram 二次验证密码", secret=True) if save_password else None

    config = FileConfig(
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone_number,
        timezone=timezone_name,
        session_name=session_name,
        update_interval=update_interval,
        first_name=first_name,
        username=username,
        last_name_prefix=last_name_prefix,
        last_name_suffix=last_name_suffix,
        proxy_type=proxy_type,
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        proxy_username=proxy_username,
        proxy_password=proxy_password,
        proxy_rdns=proxy_rdns,
        two_step_password=two_step_password,
    )
    save_file_config(config_path, config)
    print(f"配置文件已生成：{config_path}")
    return config


def ensure_file_config(config_path: Path, *, force_recreate: bool = False) -> FileConfig:
    if force_recreate:
        return prompt_create_file_config(config_path)
    if config_path.exists():
        return load_file_config(config_path)

    env_config = load_env_file_config()
    if env_config is not None:
        LOGGER.info("未找到配置文件，使用环境变量配置启动。")
        return env_config

    if not sys.stdin.isatty():
        raise RuntimeError(
            "配置文件不存在且未提供必要环境变量。请至少设置 TG_API_ID、TG_API_HASH、TG_PHONE_NUMBER。"
        )
    return prompt_create_file_config(config_path)


def configure_logging(level_name: str, log_path: Path | None = None) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )


def safe_text(value: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        value.encode(encoding)
        return value
    except UnicodeEncodeError:
        return ascii(value)


def format_utc_offset(offset: timedelta | None) -> str:
    if offset is None:
        return "UTC"

    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    if minutes == 0:
        return f"UTC{sign}{hours}"
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def seconds_until_next_run(now: datetime, interval_seconds: int) -> float:
    current = now.timestamp()
    target = ((int(current) // interval_seconds) + 1) * interval_seconds
    return max(0.1, target - current)


def get_clock_emoji(now: datetime) -> str:
    shift = 1 if now.minute >= 30 else 0
    alias = CLOCK_ALIASES[(now.hour % 12) * 2 + shift]
    return emojize(f":{alias}:", language="alias")


def build_last_name(now: datetime, rng: RandomSource | None = None) -> str:
    generator = rng or random
    hour = now.strftime("%H")
    minute = now.strftime("%M")
    weekday = now.strftime("%a")
    clock_emoji = get_clock_emoji(now)

    roll = generator.random()
    if roll < 0.10:
        return f"{hour}时{minute}分 {clock_emoji}"
    if roll < 0.30:
        return f"{hour}:{minute} {weekday} {clock_emoji}"
    if roll < 0.60:
        return f"{hour}:{minute} {clock_emoji}"
    if roll < 0.90:
        return DIZZY
    return CAKE


def build_profile_payload(
    config: AppConfig,
    now: datetime,
    rng: RandomSource | None = None,
) -> dict[str, str]:
    last_name = build_last_name(now, rng)
    payload = {
        "last_name": f"{config.last_name_prefix}{last_name}{config.last_name_suffix}",
    }
    if config.first_name is not None:
        payload["first_name"] = config.first_name
    return payload


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    def _request_stop(signum: int, _frame: object) -> None:
        LOGGER.info("收到退出信号 %s，准备停止。", signum)
        stop_event.set()

    for candidate in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if candidate is None:
            continue
        signal.signal(candidate, _request_stop)


async def ensure_authorized(client: TelegramClient, config: AppConfig) -> None:
    if await client.is_user_authorized():
        return
    if not sys.stdin.isatty():
        raise RuntimeError(
            "当前 session 未授权且运行在非交互环境。请先在本地完成一次登录，生成并挂载 "
            f"{config.session_name}.session 文件。"
        )

    LOGGER.info("当前 session 未授权，开始登录账号：%s", config.phone_number)
    sent = await client.send_code_request(config.phone_number)
    code = prompt_required("Telegram 验证码")
    try:
        await client.sign_in(
            phone=config.phone_number,
            code=code,
            phone_code_hash=sent.phone_code_hash,
        )
    except SessionPasswordNeededError:
        password = config.two_step_password or prompt_required(
            "Telegram 二次验证密码",
            secret=True,
        )
        await client.sign_in(password=password)
    LOGGER.info("Telegram 登录成功，会话已保存到 %s.session", config.session_name)


class ProfileUpdater:
    def __init__(self, client: TelegramClient, config: AppConfig) -> None:
        self.client = client
        self.config = config
        self.last_profile_payload: dict[str, str] | None = None
        self.username_synced = False

    async def ensure_username(self) -> None:
        if not self.config.username or self.username_synced:
            return

        me = await self.client.get_me()
        current_username = getattr(me, "username", None)
        if current_username == self.config.username:
            self.username_synced = True
            LOGGER.info("用户名已是目标值：%s", self.config.username)
            return

        if self.config.dry_run:
            LOGGER.info(
                "Dry-run: 将用户名从 %s 调整为 %s",
                current_username,
                self.config.username,
            )
            self.username_synced = True
            return

        await self.client(UpdateUsernameRequest(self.config.username))
        self.username_synced = True
        LOGGER.info("用户名已更新为：%s", self.config.username)

    async def update_profile(self, payload: dict[str, str]) -> None:
        if payload == self.last_profile_payload:
            LOGGER.debug("本次生成的资料与上次一致，跳过更新。")
            return

        if self.config.dry_run:
            LOGGER.info(
                "Dry-run: 资料将更新为 first_name=%s, last_name=%s",
                safe_text(payload.get("first_name", "")),
                safe_text(payload["last_name"]),
            )
            self.last_profile_payload = payload
            return

        await self.client(UpdateProfileRequest(**payload))
        self.last_profile_payload = payload
        LOGGER.info("资料已更新 -> %s", safe_text(payload["last_name"]))

    async def reset_last_name(self) -> None:
        if not self.config.reset_last_name_on_exit:
            return

        payload: dict[str, str] = {"last_name": ""}
        if self.config.first_name is not None:
            payload["first_name"] = self.config.first_name

        if self.config.dry_run:
            LOGGER.info("Dry-run: 退出时会将 last_name 重置为空。")
            return

        await self.client(UpdateProfileRequest(**payload))
        LOGGER.info("退出时已重置 last_name。")

    async def run(self, stop_event: asyncio.Event) -> None:
        await self.client.connect()
        await ensure_authorized(self.client, self.config)

        me = await self.client.get_me()
        display_name = " ".join(
            part
            for part in [getattr(me, "first_name", None), getattr(me, "last_name", None)]
            if part
        ).strip() or getattr(me, "username", None) or str(me.id)
        LOGGER.info("已登录 Telegram 账号：%s", safe_text(display_name))

        await self.ensure_username()

        if self.config.run_on_start:
            await self.run_once(datetime.now(self.config.timezone))

        while not stop_event.is_set():
            now = datetime.now(self.config.timezone)
            wait_seconds = seconds_until_next_run(now, self.config.update_interval)
            LOGGER.debug("距离下一次更新还有 %.2f 秒。", wait_seconds)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
                break
            except asyncio.TimeoutError:
                pass

            await self.ensure_username()
            await self.run_once(datetime.now(self.config.timezone))

    async def run_once(self, now: datetime) -> None:
        try:
            payload = build_profile_payload(self.config, now)
            await self.update_profile(payload)
        except FloodWaitError as exc:
            wait_seconds = exc.seconds + 1
            LOGGER.warning("触发 FloodWait，暂停 %s 秒后重试。", wait_seconds)
            await asyncio.sleep(wait_seconds)
        except RPCError as exc:
            LOGGER.warning("Telegram RPC 错误：%s", exc)
        except Exception:
            LOGGER.exception("更新 Telegram 资料时发生未预期异常。")


async def async_main(config_path: Path, *, init_only: bool = False) -> None:
    file_config = ensure_file_config(config_path, force_recreate=init_only)
    if init_only:
        return

    config = build_app_config(file_config)
    configure_logging(
        config.log_level,
        config_path.resolve().parent / "logs" / "tg_username_update.log",
    )
    health_port = int(os.getenv("PORT", "7860"))
    start_health_server(health_port)

    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)

    client = TelegramClient(
        config.session_name,
        config.api_id,
        config.api_hash,
        proxy=config.proxy,
    )
    updater = ProfileUpdater(client, config)

    try:
        await updater.run(stop_event)
    finally:
        try:
            if client.is_connected():
                await updater.reset_last_name()
        finally:
            await client.disconnect()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    try:
        asyncio.run(async_main(config_path, init_only=args.init_config))
    except KeyboardInterrupt:
        LOGGER.info("收到 KeyboardInterrupt，程序结束。")
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
