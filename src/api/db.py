"""Minimal SQLite persistence layer (WAL mode, zero ORM overhead)."""

from __future__ import annotations

import pathlib
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    serial TEXT,
    usb_vid TEXT NOT NULL DEFAULT '04e8',
    usb_pid TEXT NOT NULL DEFAULT '6860',
    screen_width INTEGER NOT NULL DEFAULT 720,
    screen_height INTEGER NOT NULL DEFAULT 1560,
    profile_path TEXT NOT NULL DEFAULT 'profiles/galaxy_a11_mt5.json',
    status TEXT NOT NULL DEFAULT 'offline',
    battery INTEGER,
    aoa_version INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    login TEXT NOT NULL,
    server TEXT NOT NULL,
    account_type TEXT NOT NULL DEFAULT 'Demo',
    balance REAL NOT NULL DEFAULT 0.0,
    max_lot REAL NOT NULL DEFAULT 0.10,
    daily_max_orders INTEGER NOT NULL DEFAULT 5,
    daily_max_loss REAL NOT NULL DEFAULT 50.0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    lot REAL NOT NULL,
    sl REAL,
    tp REAL,
    status TEXT NOT NULL DEFAULT 'queued',
    scheduled_at TEXT,
    executed_at TEXT,
    latency_ms INTEGER,
    ocr_lot REAL,
    error TEXT,
    idempotency_key TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL DEFAULT 'INFO',
    device_id INTEGER,
    order_id INTEGER,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | pathlib.Path = "data/treader.db") -> None:
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            defaults = {
                "kill_switch": "0",
                "dry_run": "1",
                "webhook_secret": secrets.token_hex(16),
            }
            for k, v in defaults.items():
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # --- Settings ---
    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # --- Devices ---
    def list_devices(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM devices ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]

    def get_device(self, device_id: int) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
            return dict(row) if row else None

    def create_device(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        serial = data.get("serial")
        vid = data.get("usb_vid", "04e8").lower()
        pid = data.get("usb_pid", "6860").lower()
        with self._connect() as conn:
            existing = None
            if serial:
                existing = conn.execute("SELECT * FROM devices WHERE serial = ?", (serial,)).fetchone()
            if existing is None:
                existing = conn.execute(
                    "SELECT * FROM devices WHERE lower(usb_vid) = ? AND lower(usb_pid) = ?",
                    (vid, pid),
                ).fetchone()
            if existing is not None:
                conn.execute(
                    "UPDATE devices SET serial = COALESCE(?, serial), status = 'ready' WHERE id = ?",
                    (serial, existing["id"]),
                )
                return dict(conn.execute("SELECT * FROM devices WHERE id = ?", (existing["id"],)).fetchone())

            cur = conn.execute(
                """INSERT INTO devices (name, serial, usb_vid, usb_pid, screen_width, screen_height, profile_path, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', ?)""",
                (
                    data["name"], serial, vid, pid,
                    data.get("screen_width", 720), data.get("screen_height", 1560),
                    data.get("profile_path", "profiles/galaxy_a11_mt5.json"), now,
                ),
            )
            return dict(conn.execute("SELECT * FROM devices WHERE id = ?", (cur.lastrowid,)).fetchone())

    def update_device_status(
        self, device_id: int, status: str, battery: Optional[int] = None, aoa_version: Optional[int] = None
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE devices SET status = ?, battery = COALESCE(?, battery), aoa_version = COALESCE(?, aoa_version) WHERE id = ?",
                (status, battery, aoa_version, device_id),
            )

    def delete_device(self, device_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            return cur.rowcount > 0

    # --- Accounts ---
    def count_today_orders(self, account_id: Optional[int] = None) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as conn:
            if account_id is None:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM orders WHERE created_at LIKE ? AND status = 'filled'",
                    (f"{today}%",),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM orders WHERE account_id = ? AND created_at LIKE ? AND status = 'filled'",
                    (account_id, f"{today}%",),
                ).fetchone()
            return int(row["c"])

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM accounts ORDER BY id ASC").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["enabled"] = bool(d["enabled"])
                d["today_orders"] = self.count_today_orders(d["id"])
                out.append(d)
            return out

    def get_account(self, account_id: int) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["enabled"] = bool(d["enabled"])
            d["today_orders"] = self.count_today_orders(d["id"])
            return d

    def create_account(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO accounts (device_id, label, login, server, account_type, balance, max_lot, daily_max_orders, daily_max_loss, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["device_id"], data["label"], data["login"], data["server"],
                    data.get("account_type", "Demo"), data.get("balance", 0.0),
                    data.get("max_lot", 0.10), data.get("daily_max_orders", 5),
                    data.get("daily_max_loss", 50.0), now,
                ),
            )
            new_id = int(cur.lastrowid)
        return self.get_account(new_id)  # type: ignore[return-value]

    def update_account(self, account_id: int, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        fields = {k: (int(v) if k == "enabled" else v) for k, v in patch.items() if v is not None}
        if not fields:
            return self.get_account(account_id)
        clause = ", ".join(f"{k} = ?" for k in fields)
        with self._connect() as conn:
            conn.execute(f"UPDATE accounts SET {clause} WHERE id = ?", (*fields.values(), account_id))
        return self.get_account(account_id)

    def delete_account(self, account_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            return cur.rowcount > 0

    # --- Orders ---
    def create_order(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        status = "scheduled" if data.get("scheduled_at") else "queued"
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO orders (account_id, device_id, symbol, side, lot, sl, tp, status, scheduled_at, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["account_id"], data["device_id"], data["symbol"].upper(), data["side"],
                    data["lot"], data.get("sl"), data.get("tp"), status,
                    data.get("scheduled_at"), data["idempotency_key"], now,
                ),
            )
            new_id = int(cur.lastrowid)
        return self.get_order(new_id)  # type: ignore[return-value]

    def get_order(self, order_id: int) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT o.*, a.label AS account_label
                   FROM orders o LEFT JOIN accounts a ON o.account_id = a.id
                   WHERE o.id = ?""",
                (order_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_order_by_key(self, idempotency_key: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM orders WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            return self.get_order(int(row["id"])) if row else None

    def list_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT o.*, a.label AS account_label
                   FROM orders o LEFT JOIN accounts a ON o.account_id = a.id
                   ORDER BY o.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def due_scheduled_orders(self, now_iso: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT o.*, a.label AS account_label
                   FROM orders o LEFT JOIN accounts a ON o.account_id = a.id
                   WHERE o.status = 'scheduled' AND o.scheduled_at <= ?
                   ORDER BY o.scheduled_at ASC""",
                (now_iso,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_order(self, order_id: int, **fields: Any) -> Optional[dict[str, Any]]:
        if not fields:
            return self.get_order(order_id)
        clause = ", ".join(f"{k} = ?" for k in fields)
        with self._connect() as conn:
            conn.execute(f"UPDATE orders SET {clause} WHERE id = ?", (*fields.values(), order_id))
        return self.get_order(order_id)

    def delete_order(self, order_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
            return cur.rowcount > 0

    # --- Audit Logs ---
    def add_log(
        self, message: str, level: str = "INFO", device_id: Optional[int] = None, order_id: Optional[int] = None
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO audit_logs (level, device_id, order_id, message, created_at) VALUES (?, ?, ?, ?, ?)",
                (level, device_id, order_id, message, now),
            )
            return dict(conn.execute("SELECT * FROM audit_logs WHERE id = ?", (cur.lastrowid,)).fetchone())

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
