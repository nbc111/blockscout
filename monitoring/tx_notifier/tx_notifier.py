#!/usr/bin/env python3
"""
定时检查 Blockscout Postgres 的 transactions 表，一旦发现新交易就推送飞书通知。
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg2
import psycopg2.extras
import requests

getcontext().prec = 60


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        raise SystemExit(f"环境变量 {name} 不是有效整数：{value}")


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        raise SystemExit(f"环境变量 {name} 不是有效小数：{value}")


@dataclass
class Config:
    dsn: str
    poll_interval: float
    batch_size: int
    webhook: str
    webhook_timeout: float
    state_file: Path
    min_value_wei: int
    watch_addresses: Tuple[str, ...]
    explorer_url: Optional[str]
    verbose: bool
    coin_symbol: str
    timezone_name: str
    timezone_obj: ZoneInfo


def load_config() -> Config:
    webhook = os.getenv("TX_NOTIFIER_FEISHU_WEBHOOK")
    if not webhook:
        raise SystemExit("必须提供 TX_NOTIFIER_FEISHU_WEBHOOK")

    dsn = os.getenv("TX_NOTIFIER_DB_DSN")
    if not dsn:
        host = os.getenv("TX_NOTIFIER_DB_HOST", "localhost")
        port = env_int("TX_NOTIFIER_DB_PORT", 5432)
        dbname = os.getenv("TX_NOTIFIER_DB_NAME", "blockscout")
        user = os.getenv("TX_NOTIFIER_DB_USER", "blockscout")
        password = os.getenv("TX_NOTIFIER_DB_PASSWORD")
        if not password:
            raise SystemExit("必须提供 TX_NOTIFIER_DB_PASSWORD 或完整 TX_NOTIFIER_DB_DSN")
        sslmode = os.getenv("TX_NOTIFIER_DB_SSLMODE")
        parts = [
            f"host={host}",
            f"port={port}",
            f"dbname={dbname}",
            f"user={user}",
            f"password={password}",
        ]
        if sslmode:
            parts.append(f"sslmode={sslmode}")
        dsn = " ".join(parts)

    state_path = Path(
        os.getenv(
            "TX_NOTIFIER_STATE_FILE",
            Path(__file__).with_suffix(".state.json").as_posix(),
        )
    )

    watch_addresses = tuple(
        addr.strip().lower()
        for addr in os.getenv("TX_NOTIFIER_WATCH_ADDRESSES", "").split(",")
        if addr.strip()
    )

    timezone_name = os.getenv("TX_NOTIFIER_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"
    try:
        timezone_obj = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise SystemExit(f"无法加载时区 {timezone_name}: {exc}") from exc

    return Config(
        dsn=dsn,
        poll_interval=max(env_float("TX_NOTIFIER_POLL_INTERVAL", 5.0), 1.0),
        batch_size=max(env_int("TX_NOTIFIER_BATCH_SIZE", 200), 1),
        webhook=webhook.strip(),
        webhook_timeout=env_float("TX_NOTIFIER_WEBHOOK_TIMEOUT", 5.0),
        state_file=state_path,
        min_value_wei=max(env_int("TX_NOTIFIER_MIN_VALUE_WEI", 0), 0),
        watch_addresses=watch_addresses,
        explorer_url=os.getenv("TX_NOTIFIER_EXPLORER_URL"),
        verbose=env_bool("TX_NOTIFIER_VERBOSE", False),
        coin_symbol=os.getenv("TX_NOTIFIER_COIN_SYMBOL", "NBC").strip() or "NBC",
        timezone_name=timezone_name,
        timezone_obj=timezone_obj,
    )


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def normalize_hex(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    raw = raw.lower()
    if raw.startswith("0x"):
        return raw
    return "0x" + raw


def load_state(path: Path) -> Tuple[Optional[str], Optional[str]]:
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("last_inserted_at"), data.get("last_hash")
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("无法读取状态文件 %s：%s，将重新开始", path, exc)
        return None, None


def save_state(path: Path, inserted_at: Optional[str], tx_hash: Optional[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_inserted_at": inserted_at, "last_hash": tx_hash}
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    tmp_path.replace(path)


def init_state(conn, path: Path) -> Tuple[Optional[str], Optional[str]]:
    last_inserted_at, last_hash = load_state(path)
    if last_inserted_at:
        return last_inserted_at, last_hash

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            "SELECT inserted_at, encode(hash, 'hex') AS hash_hex "
            "FROM transactions ORDER BY inserted_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            last_inserted_at = row["inserted_at"].isoformat()
            last_hash = row["hash_hex"]
            save_state(path, last_inserted_at, last_hash)
            logging.info("初始化状态至最新交易 %s", last_hash)
        else:
            logging.info("transactions 表为空，等待第一笔交易")
    return last_inserted_at, last_hash


def fetch_new_transactions(
    conn,
    since_ts: Optional[str],
    since_hash: Optional[str],
    limit: int,
) -> List[dict]:
    conditions: List[str] = []
    params: List[object] = []

    if since_ts:
        conditions.append(
            "(t.inserted_at > %s OR (t.inserted_at = %s AND t.hash > decode(%s, 'hex')))"
        )
        params.extend([since_ts, since_ts, since_hash or ""])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT
            encode(t.hash, 'hex') AS hash_hex,
            encode(t.from_address_hash, 'hex') AS from_address,
            encode(t.to_address_hash, 'hex') AS to_address,
            encode(t.created_contract_address_hash, 'hex') AS contract_address,
            t.block_number,
            t.nonce,
            t.value,
            t.inserted_at
        FROM transactions t
        {where_clause}
        ORDER BY t.inserted_at ASC
        LIMIT %s
    """
    params.append(limit)

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def format_value(value: Decimal) -> Tuple[int, str]:
    wei = int(value)
    eth = Decimal(wei) / Decimal(10**18)
    return wei, f"{eth.normalize():f}"


def should_notify(tx: dict, cfg: Config) -> bool:
    wei, _ = format_value(tx["value"])
    if wei < cfg.min_value_wei:
        return False

    if not cfg.watch_addresses:
        return True

    from_addr = normalize_hex(tx["from_address"])
    to_addr = normalize_hex(tx["to_address"])
    contract_addr = normalize_hex(tx["contract_address"])
    return any(
        addr in cfg.watch_addresses
        for addr in filter(
            None, (from_addr, to_addr, contract_addr)
        )
    )


def build_message(tx: dict, cfg: Config) -> dict:
    wei, eth_text = format_value(tx["value"])
    tx_hash = normalize_hex(tx["hash_hex"])
    from_addr = normalize_hex(tx["from_address"])
    to_addr = normalize_hex(tx["to_address"]) or "(contract creation)"
    created = normalize_hex(tx["contract_address"])
    ts_local = tx["inserted_at"].astimezone(cfg.timezone_obj)
    offset = ts_local.utcoffset()
    if offset is None:
        offset = timezone.utc.utcoffset(datetime.now(timezone.utc))
    offset_hours = int(offset.total_seconds() // 3600)
    offset_minutes = int((abs(offset.total_seconds()) % 3600) // 60)
    offset_sign = "+" if offset_hours >= 0 else "-"
    offset_str = f"UTC{offset_sign}{abs(offset_hours):02d}:{offset_minutes:02d}"
    timestamp = ts_local.strftime(f"%Y-%m-%d %H:%M:%S {cfg.timezone_name} ({offset_str})")
    link = f"{cfg.explorer_url.rstrip('/')}/tx/{tx_hash}" if cfg.explorer_url else tx_hash

    lines = [
        "[交易提醒]",
        f"区块: {tx['block_number']}",
        f"Tx: {tx_hash}",
        f"From: {from_addr}",
        f"To: {to_addr}",
        f"Value: {eth_text} {cfg.coin_symbol} ({wei} wei)",
        f"时间: {timestamp}",
        f"链接: {link}",
    ]
    if created:
        lines.insert(5, f"新合约: {created}")

    return {"msg_type": "text", "content": {"text": "\n".join(lines)}}


def send_to_feishu(payload: dict, cfg: Config) -> None:
    resp = requests.post(cfg.webhook, json=payload, timeout=cfg.webhook_timeout)
    if resp.status_code != 200:
        logging.warning(
            "飞书返回异常 status=%s body=%s", resp.status_code, resp.text[:200]
        )


def loop(conn, cfg: Config) -> None:
    since_ts, since_hash = init_state(conn, cfg.state_file)
    logging.info("开始轮询，间隔 %.1fs", cfg.poll_interval)

    while True:
        try:
            rows = fetch_new_transactions(conn, since_ts, since_hash, cfg.batch_size)
            if rows:
                logging.debug("本次获取到 %d 条交易", len(rows))
            for row in rows:
                if not should_notify(row, cfg):
                    since_ts = row["inserted_at"].isoformat()
                    since_hash = row["hash_hex"]
                    continue
                payload = build_message(row, cfg)
                send_to_feishu(payload, cfg)
                since_ts = row["inserted_at"].isoformat()
                since_hash = row["hash_hex"]
                save_state(cfg.state_file, since_ts, since_hash)
            time.sleep(cfg.poll_interval)
        except psycopg2.Error as exc:
            logging.exception("数据库错误：%s，5 秒后重试", exc)
            time.sleep(5)
            conn.reset()
        except requests.RequestException as exc:
            logging.exception("飞书推送失败：%s", exc)
            time.sleep(cfg.poll_interval)
        except KeyboardInterrupt:
            logging.info("收到中断信号，退出")
            break


def main() -> None:
    cfg = load_config()
    setup_logging(cfg.verbose)

    def handle_signal(signum, _frame):
        logging.info("收到信号 %s，准备退出", signum)
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logging.info("连接数据库...")
    with psycopg2.connect(cfg.dsn) as conn:
        loop(conn, cfg)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pylint: disable=broad-except
        logging.exception("程序异常退出：%s", exc)
        sys.exit(1)

