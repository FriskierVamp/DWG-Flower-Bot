"""
db/queries.py
Dreamweaving Garden Bot — SQLite data layer.

Database file location priority:
  1. DB_PATH env var (explicit override)
  2. /data/dwg.db  (Railway Volume — mount at /data)
  3. ./dwg.db      (local fallback for development)

Tables:
  GLOBAL (no guild_id):
    flowers           — master flower list (admin-managed)
    vases             — master vase list (admin-managed)

  PER-SERVER (all have guild_id):
    guild_config      — channels, roles from /setup
    members           — registered players
    player_collection — flower + vase ownership per player (item_type: 'flower'|'vase')
    league_entries    — league standings snapshots
    league_locks      — weekly participation locks
    contributions     — contribution log
"""

import os
import sqlite3
import logging
import threading
from typing import Optional

log = logging.getLogger("dwg.db")

# ── Rarity config ──────────────────────────────────────────────────
RARITY_ORDER: dict[str, int] = {
    "Shine": 0,
    "Star":  1,
    "Rare":  2,
    "Fine":  3,
    "Basic": 4,
}
VALID_RARITIES: set[str] = set(RARITY_ORDER.keys())

_RARITY_ALIASES: dict[str, str] = {
    "shine": "Shine",
    "star":  "Star",
    "rare":  "Rare",
    "fine":  "Fine",
    "basic": "Basic",
}

def normalize_rarity(raw: str) -> str:
    return _RARITY_ALIASES.get(str(raw).strip().lower(), str(raw).strip().title())


# ── DB path resolution ─────────────────────────────────────────────
def _resolve_db_path() -> str:
    if path := os.getenv("DB_PATH"):
        return path
    if os.path.isdir("/data"):
        return "/data/dwg.db"
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dwg.db")

DB_PATH = _resolve_db_path()
log.info("SQLite database path: %s", DB_PATH)

_local = threading.local()

def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


# ══════════════════════════════════════════════════════════════════
# SCHEMA
# ══════════════════════════════════════════════════════════════════

def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = _get_conn()
    conn.executescript("""
        -- ── GLOBAL ────────────────────────────────────────────────

        CREATE TABLE IF NOT EXISTS flowers (
            name         TEXT PRIMARY KEY COLLATE NOCASE,
            rarity       TEXT NOT NULL DEFAULT 'Basic',
            base_points  INTEGER NOT NULL DEFAULT 0,
            upgrade_cost INTEGER NOT NULL DEFAULT 0,
            source       TEXT NOT NULL DEFAULT 'Unknown',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS vases (
            name         TEXT PRIMARY KEY COLLATE NOCASE,
            rarity       TEXT NOT NULL DEFAULT 'Basic',
            base_points  INTEGER NOT NULL DEFAULT 0,
            upgrade_cost INTEGER NOT NULL DEFAULT 0,
            source       TEXT NOT NULL DEFAULT 'Unknown',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── PER-SERVER ─────────────────────────────────────────────

        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id         TEXT PRIMARY KEY,
            log_channel_id   TEXT,
            leader_role_ids  TEXT NOT NULL DEFAULT '[]',
            seedling_role_id TEXT,
            member_role_id   TEXT,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS members (
            guild_id      TEXT NOT NULL,
            discord_id    TEXT NOT NULL,
            ign           TEXT NOT NULL,
            registered_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (guild_id, discord_id)
        );

        -- item_type is strictly 'flower' or 'vase'
        -- item_name is validated in code against flowers/vases master tables
        CREATE TABLE IF NOT EXISTS player_collection (
            guild_id   TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            item_type  TEXT NOT NULL CHECK(item_type IN ('flower','vase')),
            item_name  TEXT NOT NULL COLLATE NOCASE,
            added_at   TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (guild_id, discord_id, item_type, item_name)
        );

        CREATE TABLE IF NOT EXISTS league_entries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id   TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            rank       INTEGER,
            points     INTEGER NOT NULL DEFAULT 0,
            season     TEXT NOT NULL DEFAULT '',
            logged_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS league_locks (
            guild_id   TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            locked_at  TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (guild_id, discord_id)
        );

        CREATE TABLE IF NOT EXISTS contributions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id   TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            amount     INTEGER NOT NULL DEFAULT 0,
            note       TEXT NOT NULL DEFAULT '',
            logged_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    log.info("Database initialised at %s", DB_PATH)


# ══════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════

def _master_table(item_type: str) -> str:
    """Return the master table name for a given item_type."""
    if item_type == "flower":
        return "flowers"
    if item_type == "vase":
        return "vases"
    raise ValueError(f"Unknown item_type: {item_type!r}")


def _item_exists(item_type: str, name: str) -> bool:
    """Check the appropriate master table for existence."""
    table = _master_table(item_type)
    row = _get_conn().execute(
        f"SELECT 1 FROM {table} WHERE name = ?", (name,)
    ).fetchone()
    return row is not None


# ══════════════════════════════════════════════════════════════════
# MASTER LIST — shared helpers used by both flowers and vases
# ══════════════════════════════════════════════════════════════════

def _get_all(item_type: str) -> list[dict]:
    table = _master_table(item_type)
    rows = _get_conn().execute(
        f"SELECT name, rarity, base_points, upgrade_cost, source FROM {table} ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def _get_one(item_type: str, name: str) -> Optional[dict]:
    table = _master_table(item_type)
    row = _get_conn().execute(
        f"SELECT name, rarity, base_points, upgrade_cost, source FROM {table} WHERE name = ?",
        (name,)
    ).fetchone()
    return dict(row) if row else None


def _upsert_master(item_type: str, name: str, rarity: str,
                   base_points: int, upgrade_cost: int, source: str) -> None:
    table = _master_table(item_type)
    norm = normalize_rarity(rarity)
    conn = _get_conn()
    conn.execute(f"""
        INSERT INTO {table} (name, rarity, base_points, upgrade_cost, source)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            rarity       = excluded.rarity,
            base_points  = excluded.base_points,
            upgrade_cost = excluded.upgrade_cost,
            source       = excluded.source,
            updated_at   = datetime('now')
    """, (name, norm, int(base_points), int(upgrade_cost), source))
    conn.commit()


def _delete_master(item_type: str, name: str) -> bool:
    table = _master_table(item_type)
    conn = _get_conn()
    cur = conn.execute(f"DELETE FROM {table} WHERE name = ?", (name,))
    conn.commit()
    return cur.rowcount > 0


def _autocomplete(item_type: str, query: str = "") -> list[str]:
    table = _master_table(item_type)
    rows = _get_conn().execute(
        f"SELECT name FROM {table} WHERE name LIKE ? ORDER BY name LIMIT 25",
        (f"%{query}%",)
    ).fetchall()
    return [r["name"] for r in rows]


# ══════════════════════════════════════════════════════════════════
# FLOWERS  (master list)
# ══════════════════════════════════════════════════════════════════

def get_all_flowers() -> list[dict]:
    return _get_all("flower")

def get_flower(name: str) -> Optional[dict]:
    return _get_one("flower", name)

def upsert_flower(name: str, rarity: str, base_points: int,
                  upgrade_cost: int, source: str) -> None:
    _upsert_master("flower", name, rarity, base_points, upgrade_cost, source)

def delete_flower(name: str) -> bool:
    return _delete_master("flower", name)

def get_flower_names_for_autocomplete(query: str = "") -> list[str]:
    return _autocomplete("flower", query)


# ══════════════════════════════════════════════════════════════════
# VASES  (master list — same fields as flowers)
# ══════════════════════════════════════════════════════════════════

def get_all_vases() -> list[dict]:
    return _get_all("vase")

def get_vase(name: str) -> Optional[dict]:
    return _get_one("vase", name)

def upsert_vase(name: str, rarity: str, base_points: int,
                upgrade_cost: int, source: str) -> None:
    _upsert_master("vase", name, rarity, base_points, upgrade_cost, source)

def delete_vase(name: str) -> bool:
    return _delete_master("vase", name)

def get_vase_names_for_autocomplete(query: str = "") -> list[str]:
    return _autocomplete("vase", query)


# ══════════════════════════════════════════════════════════════════
# GUILD CONFIG
# ══════════════════════════════════════════════════════════════════

def get_guild_config(guild_id: str) -> Optional[dict]:
    import json
    row = _get_conn().execute(
        "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["leader_role_ids"] = json.loads(d["leader_role_ids"])
    return d


def upsert_guild_config(guild_id: str, **fields) -> None:
    import json
    existing = get_guild_config(guild_id) or {}
    merged = {**existing, **fields}
    leader_ids = merged.get("leader_role_ids", [])
    conn = _get_conn()
    conn.execute("""
        INSERT INTO guild_config (guild_id, log_channel_id, leader_role_ids,
                                  seedling_role_id, member_role_id)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            log_channel_id   = excluded.log_channel_id,
            leader_role_ids  = excluded.leader_role_ids,
            seedling_role_id = excluded.seedling_role_id,
            member_role_id   = excluded.member_role_id,
            updated_at       = datetime('now')
    """, (
        guild_id,
        merged.get("log_channel_id"),
        json.dumps(leader_ids if isinstance(leader_ids, list) else [leader_ids]),
        merged.get("seedling_role_id"),
        merged.get("member_role_id"),
    ))
    conn.commit()


# ══════════════════════════════════════════════════════════════════
# MEMBERS
# ══════════════════════════════════════════════════════════════════

def find_player(guild_id: str, discord_id: str) -> Optional[dict]:
    row = _get_conn().execute(
        "SELECT * FROM members WHERE guild_id = ? AND discord_id = ?",
        (guild_id, discord_id)
    ).fetchone()
    return dict(row) if row else None


def find_player_by_ign(guild_id: str, ign: str) -> Optional[dict]:
    row = _get_conn().execute(
        "SELECT * FROM members WHERE guild_id = ? AND ign LIKE ?",
        (guild_id, ign)
    ).fetchone()
    return dict(row) if row else None


def get_all_members(guild_id: str) -> list[dict]:
    rows = _get_conn().execute(
        "SELECT * FROM members WHERE guild_id = ? ORDER BY ign",
        (guild_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_member(guild_id: str, discord_id: str, ign: str) -> None:
    conn = _get_conn()
    conn.execute("""
        INSERT INTO members (guild_id, discord_id, ign)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, discord_id) DO UPDATE SET
            ign        = excluded.ign,
            updated_at = datetime('now')
    """, (guild_id, discord_id, ign))
    conn.commit()


def delete_member(guild_id: str, discord_id: str) -> bool:
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM members WHERE guild_id = ? AND discord_id = ?",
        (guild_id, discord_id)
    )
    conn.commit()
    return cur.rowcount > 0


# ══════════════════════════════════════════════════════════════════
# PLAYER COLLECTION  (flowers + vases combined)
# Validation: item must exist in master table before insert.
# ══════════════════════════════════════════════════════════════════

def add_to_collection(guild_id: str, discord_id: str,
                      item_type: str, item_name: str) -> tuple[bool, str]:
    """
    Add a flower or vase to a player's collection.
    Returns (success, message).
    Validates item exists in master table before inserting.
    """
    if not _item_exists(item_type, item_name):
        kind = item_type.capitalize()
        return False, f"{kind} **{item_name}** doesn't exist in the master list."
    try:
        conn = _get_conn()
        conn.execute("""
            INSERT OR IGNORE INTO player_collection
                (guild_id, discord_id, item_type, item_name)
            VALUES (?, ?, ?, ?)
        """, (guild_id, discord_id, item_type, item_name))
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            return False, f"You already have **{item_name}** in your collection."
        conn.commit()
        return True, f"Added **{item_name}** to your collection."
    except sqlite3.Error as e:
        log.error("add_to_collection error: %s", e)
        return False, "Database error. Please try again."


def remove_from_collection(guild_id: str, discord_id: str,
                           item_type: str, item_name: str) -> bool:
    conn = _get_conn()
    cur = conn.execute("""
        DELETE FROM player_collection
        WHERE guild_id = ? AND discord_id = ? AND item_type = ? AND item_name = ?
    """, (guild_id, discord_id, item_type, item_name))
    conn.commit()
    return cur.rowcount > 0


def get_player_collection(guild_id: str, discord_id: str,
                          item_type: Optional[str] = None) -> list[dict]:
    """Get a player's collection. Optionally filter by item_type ('flower' or 'vase')."""
    if item_type:
        rows = _get_conn().execute("""
            SELECT pc.item_type, pc.item_name, pc.added_at,
                   m.rarity, m.base_points, m.upgrade_cost, m.source
            FROM player_collection pc
            LEFT JOIN flowers m ON pc.item_name = m.name AND pc.item_type = 'flower'
            WHERE pc.guild_id = ? AND pc.discord_id = ? AND pc.item_type = ?
            ORDER BY pc.item_type, pc.item_name
        """, (guild_id, discord_id, item_type)).fetchall()
    else:
        rows = _get_conn().execute("""
            SELECT item_type, item_name, added_at
            FROM player_collection
            WHERE guild_id = ? AND discord_id = ?
            ORDER BY item_type, item_name
        """, (guild_id, discord_id)).fetchall()
    return [dict(r) for r in rows]


def get_collection_item_names(guild_id: str, discord_id: str,
                               item_type: str) -> list[str]:
    """Just the names — used for autocomplete on /track remove."""
    rows = _get_conn().execute("""
        SELECT item_name FROM player_collection
        WHERE guild_id = ? AND discord_id = ? AND item_type = ?
        ORDER BY item_name
    """, (guild_id, discord_id, item_type)).fetchall()
    return [r["item_name"] for r in rows]


def who_has_item(guild_id: str, item_type: str, item_name: str) -> list[dict]:
    """Which members in a guild have a specific flower or vase."""
    rows = _get_conn().execute("""
        SELECT m.ign, m.discord_id
        FROM player_collection pc
        JOIN members m ON m.guild_id = pc.guild_id AND m.discord_id = pc.discord_id
        WHERE pc.guild_id = ? AND pc.item_type = ? AND pc.item_name = ?
        ORDER BY m.ign
    """, (guild_id, item_type, item_name)).fetchall()
    return [dict(r) for r in rows]


def get_missing_from_master(guild_id: str, discord_id: str,
                             item_type: str) -> list[dict]:
    """Items in the master list that a player does NOT have."""
    table = _master_table(item_type)
    rows = _get_conn().execute(f"""
        SELECT m.name, m.rarity, m.base_points, m.upgrade_cost, m.source
        FROM {table} m
        WHERE m.name NOT IN (
            SELECT item_name FROM player_collection
            WHERE guild_id = ? AND discord_id = ? AND item_type = ?
        )
        ORDER BY m.name
    """, (guild_id, discord_id, item_type)).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════
# LEAGUE ENTRIES
# ══════════════════════════════════════════════════════════════════

def log_league_entry(guild_id: str, discord_id: str,
                     rank: Optional[int], points: int, season: str = "") -> None:
    conn = _get_conn()
    conn.execute("""
        INSERT INTO league_entries (guild_id, discord_id, rank, points, season)
        VALUES (?, ?, ?, ?, ?)
    """, (guild_id, discord_id, rank, int(points), season))
    conn.commit()


def get_latest_league_entry(guild_id: str, discord_id: str) -> Optional[dict]:
    row = _get_conn().execute("""
        SELECT * FROM league_entries
        WHERE guild_id = ? AND discord_id = ?
        ORDER BY logged_at DESC LIMIT 1
    """, (guild_id, discord_id)).fetchone()
    return dict(row) if row else None


def get_guild_league_standings(guild_id: str, season: str = "") -> list[dict]:
    """Latest entry per player, optionally filtered by season."""
    rows = _get_conn().execute("""
        SELECT le.discord_id, m.ign, le.rank, le.points, le.season, le.logged_at
        FROM league_entries le
        JOIN members m ON m.guild_id = le.guild_id AND m.discord_id = le.discord_id
        WHERE le.guild_id = ?
          AND (? = '' OR le.season = ?)
          AND le.logged_at = (
              SELECT MAX(logged_at) FROM league_entries le2
              WHERE le2.guild_id = le.guild_id AND le2.discord_id = le.discord_id
          )
        ORDER BY le.points DESC
    """, (guild_id, season, season)).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════
# LEAGUE LOCKS
# ══════════════════════════════════════════════════════════════════

def lock_player(guild_id: str, discord_id: str) -> None:
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO league_locks (guild_id, discord_id)
        VALUES (?, ?)
    """, (guild_id, discord_id))
    conn.commit()


def unlock_player(guild_id: str, discord_id: str) -> bool:
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM league_locks WHERE guild_id = ? AND discord_id = ?",
        (guild_id, discord_id)
    )
    conn.commit()
    return cur.rowcount > 0


def is_locked(guild_id: str, discord_id: str) -> bool:
    row = _get_conn().execute(
        "SELECT 1 FROM league_locks WHERE guild_id = ? AND discord_id = ?",
        (guild_id, discord_id)
    ).fetchone()
    return row is not None


def get_locked_players(guild_id: str) -> list[str]:
    rows = _get_conn().execute(
        "SELECT discord_id FROM league_locks WHERE guild_id = ?", (guild_id,)
    ).fetchall()
    return [r["discord_id"] for r in rows]


def reset_all_locks(guild_id: str) -> int:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM league_locks WHERE guild_id = ?", (guild_id,))
    conn.commit()
    return cur.rowcount


# ══════════════════════════════════════════════════════════════════
# CONTRIBUTIONS
# ══════════════════════════════════════════════════════════════════

def log_contribution(guild_id: str, discord_id: str,
                     amount: int, note: str = "") -> None:
    conn = _get_conn()
    conn.execute("""
        INSERT INTO contributions (guild_id, discord_id, amount, note)
        VALUES (?, ?, ?, ?)
    """, (guild_id, discord_id, int(amount), note))
    conn.commit()


def get_player_contributions(guild_id: str, discord_id: str) -> list[dict]:
    rows = _get_conn().execute("""
        SELECT amount, note, logged_at FROM contributions
        WHERE guild_id = ? AND discord_id = ?
        ORDER BY logged_at DESC
    """, (guild_id, discord_id)).fetchall()
    return [dict(r) for r in rows]


def get_guild_contribution_totals(guild_id: str) -> list[dict]:
    """Leaderboard — total contributions per player."""
    rows = _get_conn().execute("""
        SELECT m.ign, m.discord_id, SUM(c.amount) as total
        FROM contributions c
        JOIN members m ON m.guild_id = c.guild_id AND m.discord_id = c.discord_id
        WHERE c.guild_id = ?
        GROUP BY c.discord_id
        ORDER BY total DESC
    """, (guild_id,)).fetchall()
    return [dict(r) for r in rows]
