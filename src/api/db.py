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

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    broker_symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    sl REAL NOT NULL,
    tp REAL NOT NULL,
    risk_reward REAL NOT NULL,
    calculated_lot REAL NOT NULL,
    risk_amount REAL NOT NULL,
    confidence INTEGER NOT NULL DEFAULT 80,
    timeframe TEXT NOT NULL DEFAULT 'H1', -- H1, H4, D1
    status TEXT NOT NULL DEFAULT 'pending', -- pending, executed, paper_active, rejected, expired
    reasoning TEXT,
    order_id INTEGER REFERENCES orders(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER REFERENCES signals(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    lot REAL NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    sl REAL NOT NULL,
    tp REAL NOT NULL,
    risk_amount REAL NOT NULL,
    pnl REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'open', -- open, closed_tp, closed_sl, closed_manual
    timeframe TEXT NOT NULL DEFAULT 'H1',
    opened_at TEXT NOT NULL,
    closed_at TEXT
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
                "agent_token": secrets.token_hex(20),
                "env_mode_override": "auto",
                "github_repo_url": "",
                "github_branch": "master",
                "github_token": "",
                "vps_public_url": "",
                "strategy_balance": "46250.0",
                "strategy_risk_percent": "1.0",
                "strategy_min_rr": "2.0",
                "strategy_symbol_suffix": ".pro",
                "strategy_auto_execute": "0",
                "strategy_autopilot_enabled": "1",
                "strategy_watchlist": "XAUUSD,EURUSD,GBPUSD,USDJPY,NAS100",
                "strategy_favorites": "XAUUSD,EURUSD,GBPUSD,USDJPY,NAS100",
                "strategy_timeframe": "H1",
                "strategy_paper_trading": "1",
                "strategy_max_daily_loss": "925.0",
                "strategy_last_autopilot_run": "",
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

    # --- Paper Positions ---
    def create_paper_position(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO paper_positions (signal_id, symbol, side, lot, entry_price, current_price, sl, tp, risk_amount, pnl, status, timeframe, opened_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                (
                    data.get("signal_id"),
                    data["symbol"].upper(),
                    data["side"].upper(),
                    float(data["lot"]),
                    float(data["entry_price"]),
                    float(data.get("current_price", data["entry_price"])),
                    float(data["sl"]),
                    float(data["tp"]),
                    float(data.get("risk_amount", 462.5)),
                    float(data.get("pnl", 0.0)),
                    data.get("timeframe", "H1"),
                    now,
                ),
            )
            return dict(conn.execute("SELECT * FROM paper_positions WHERE id = ?", (cur.lastrowid,)).fetchone())

    def list_paper_positions(self, status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute("SELECT * FROM paper_positions WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM paper_positions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def update_paper_position_price(self, position_id: int, current_price: float, pnl: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE paper_positions SET current_price = ?, pnl = ? WHERE id = ? AND status = 'open'",
                (current_price, round(pnl, 2), position_id),
            )

    def close_paper_position(self, position_id: int, close_price: float, close_status: str = "closed_manual") -> Optional[dict[str, Any]]:
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM paper_positions WHERE id = ?", (position_id,)).fetchone()
            if not row:
                return None
            pos = dict(row)
            entry = float(pos["entry_price"])
            lot = float(pos["lot"])
            side = pos["side"]
            symbol = pos["symbol"]

            # Calculate PnL
            diff = (close_price - entry) if side == "BUY" else (entry - close_price)
            if "XAUUSD" in symbol or "GOLD" in symbol:
                pnl = diff * 100.0 * lot
            elif any(symbol.startswith(p) or symbol.endswith(p) for p in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]):
                pip_size = 0.01 if "JPY" in symbol else 0.0001
                pips = diff / pip_size
                pnl = pips * 10.0 * lot
            else:
                pnl = diff * lot

            conn.execute(
                "UPDATE paper_positions SET status = ?, current_price = ?, pnl = ?, closed_at = ? WHERE id = ?",
                (close_status, close_price, round(pnl, 2), now, position_id),
            )
            # Update strategy balance
            curr_bal = float(self.get_setting("strategy_balance", "46250.0"))
            new_bal = round(curr_bal + pnl, 2)
            self.set_setting("strategy_balance", str(new_bal))

            return dict(conn.execute("SELECT * FROM paper_positions WHERE id = ?", (position_id,)).fetchone())

    def get_paper_stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            open_count = conn.execute("SELECT COUNT(*) AS c FROM paper_positions WHERE status = 'open'").fetchone()["c"]
            closed_rows = conn.execute("SELECT pnl, status FROM paper_positions WHERE status != 'open'").fetchall()
            closed_trades = [dict(r) for r in closed_rows]
            total_closed = len(closed_trades)
            wins = sum(1 for t in closed_trades if t["pnl"] > 0)
            losses = sum(1 for t in closed_trades if t["pnl"] < 0)
            win_rate = round((wins / total_closed * 100), 1) if total_closed > 0 else 0.0
            total_realized_pnl = round(sum(t["pnl"] for t in closed_trades), 2)
            
            return {
                "open_count": open_count,
                "total_trades": total_closed,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "realized_pnl": total_realized_pnl,
            }

    # --- Signals ---
    def create_signal(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO signals (ticker, broker_symbol, side, entry_price, sl, tp, risk_reward, calculated_lot, risk_amount, confidence, timeframe, status, reasoning, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["ticker"].upper(),
                    data.get("broker_symbol", data["ticker"]).upper(),
                    data["side"].upper(),
                    float(data["entry_price"]),
                    float(data["sl"]),
                    float(data["tp"]),
                    float(data.get("risk_reward", 2.0)),
                    float(data.get("calculated_lot", 0.1)),
                    float(data.get("risk_amount", 462.5)),
                    int(data.get("confidence", 80)),
                    data.get("timeframe", "H1"),
                    data.get("status", "pending"),
                    data.get("reasoning", ""),
                    now,
                ),
            )
            return dict(conn.execute("SELECT * FROM signals WHERE id = ?", (cur.lastrowid,)).fetchone())

    def list_signals(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_signal(self, signal_id: int) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
            return dict(row) if row else None

    def update_signal_status(self, signal_id: int, status: str, order_id: Optional[int] = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE signals SET status = ?, order_id = COALESCE(?, order_id) WHERE id = ?",
                (status, order_id, signal_id),
            )

    def get_today_signal_stats(self) -> dict[str, Any]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM signals WHERE created_at LIKE ?", (f"{today}%",)).fetchone()["c"]
            executed = conn.execute("SELECT COUNT(*) AS c FROM signals WHERE created_at LIKE ? AND status = 'executed'", (f"{today}%",)).fetchone()["c"]
            pending = conn.execute("SELECT COUNT(*) AS c FROM signals WHERE created_at LIKE ? AND status = 'pending'", (f"{today}%",)).fetchone()["c"]
            return {"total": total, "executed": executed, "pending": pending}

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
