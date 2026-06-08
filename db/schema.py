"""
db/schema.py
Dreamweaving Garden Bot — Database Schema
All tables include guild_id so the bot can serve multiple servers cleanly.
"""

import sqlite3
import os
import json
import logging

log = logging.getLogger("dwg.db")

DB_DIR  = os.getenv("DB_DIR", "/data" if os.path.isdir("/data") else ".")
DB_PATH = os.path.join(DB_DIR, "dreamweaving.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = get_db()
    cur  = conn.cursor()

    # ------------------------------------------------------------------
    # GUILD CONFIG
    # Per-server settings written by /setup.
    # approved = 1 means this guild is whitelisted to use the bot.
    # A guild is considered "set up" when leader_role_ids is non-empty.
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS guild_config (
        guild_id        TEXT PRIMARY KEY,
        guild_name      TEXT,
        leader_role_ids TEXT NOT NULL DEFAULT '[]',
        new_role_id     TEXT,
        member_role_id  TEXT,
        approved        INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    # ------------------------------------------------------------------
    # PLAYERS
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        TEXT NOT NULL,
        discord_id      TEXT NOT NULL,
        discord_name    TEXT,
        ign             TEXT NOT NULL,
        is_vip          INTEGER NOT NULL DEFAULT 0,
        registered_at   TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(guild_id, discord_id)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_players_guild ON players(guild_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_players_discord ON players(guild_id, discord_id)")

    # ------------------------------------------------------------------
    # MASTER FLOWER LIST (global, managed via dashboard)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS flowers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL UNIQUE,
        rarity          TEXT NOT NULL,
        base_points     INTEGER NOT NULL DEFAULT 0,
        upgraded_points INTEGER GENERATED ALWAYS AS (base_points * 2) VIRTUAL,
        upgrade_cost    INTEGER NOT NULL DEFAULT 0,
        source          TEXT NOT NULL DEFAULT 'Unknown',
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_flowers_rarity ON flowers(rarity)")

    # ------------------------------------------------------------------
    # MASTER VASE LIST (global, managed via dashboard)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS master_vases (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL UNIQUE,
        rarity          TEXT NOT NULL,
        base_points     INTEGER NOT NULL DEFAULT 0,
        upgraded_points INTEGER GENERATED ALWAYS AS (base_points * 2) VIRTUAL,
        upgrade_cost    INTEGER NOT NULL DEFAULT 0,
        source          TEXT NOT NULL DEFAULT 'Unknown',
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_master_vases_rarity ON master_vases(rarity)")

    # ------------------------------------------------------------------
    # PLAYER FLOWERS
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_flowers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        TEXT NOT NULL,
        discord_id      TEXT NOT NULL,
        flower_name     TEXT NOT NULL,
        is_upgraded     INTEGER NOT NULL DEFAULT 0,
        source_type     TEXT NOT NULL DEFAULT 'manual',
        logged_by       TEXT,
        logged_at       TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(guild_id, discord_id, flower_name),
        FOREIGN KEY(flower_name) REFERENCES flowers(name) ON UPDATE CASCADE
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pf_guild ON player_flowers(guild_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pf_player ON player_flowers(guild_id, discord_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pf_flower ON player_flowers(flower_name)")

    # ------------------------------------------------------------------
    # PLAYER VASES — mirrors player_flowers
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_vases (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        TEXT NOT NULL,
        discord_id      TEXT NOT NULL,
        vase_name       TEXT NOT NULL,
        source_type     TEXT NOT NULL DEFAULT 'manual',
        logged_by       TEXT,
        logged_at       TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(guild_id, discord_id, vase_name),
        FOREIGN KEY(vase_name) REFERENCES master_vases(name) ON UPDATE CASCADE
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pv_guild ON player_vases(guild_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pv_player ON player_vases(guild_id, discord_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pv_vase ON player_vases(vase_name)")

    # ------------------------------------------------------------------
    # LEAGUE LOG
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS league_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        TEXT NOT NULL,
        discord_id      TEXT NOT NULL,
        season          TEXT,
        rank            INTEGER,
        points          INTEGER,
        source_type     TEXT NOT NULL DEFAULT 'manual',
        logged_by       TEXT,
        logged_at       TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_league_guild ON league_log(guild_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_league_player ON league_log(guild_id, discord_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_league_season ON league_log(guild_id, season)")

    # ------------------------------------------------------------------
    # CONTRIBUTIONS
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS contributions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        TEXT NOT NULL,
        discord_id      TEXT NOT NULL,
        amount          INTEGER NOT NULL DEFAULT 0,
        contribution_date TEXT,
        note            TEXT,
        source_type     TEXT NOT NULL DEFAULT 'manual',
        logged_by       TEXT,
        logged_at       TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contrib_guild ON contributions(guild_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contrib_player ON contributions(guild_id, discord_id)")

    # ------------------------------------------------------------------
    # LEAGUE COMPETITION STATE (weekly event tracking)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS league_state (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        TEXT NOT NULL,
        discord_id      TEXT NOT NULL,
        week_start      TEXT NOT NULL,
        flowers_used    TEXT NOT NULL DEFAULT '[]',
        is_locked       INTEGER NOT NULL DEFAULT 0,
        locked_at       TEXT,
        UNIQUE(guild_id, discord_id, week_start)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ls_guild ON league_state(guild_id, week_start)")

    # ------------------------------------------------------------------
    # MIGRATIONS — safe to run on existing databases
    # ------------------------------------------------------------------
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(player_flowers)")}
    if "is_upgraded" not in existing_cols:
        cur.execute("ALTER TABLE player_flowers ADD COLUMN is_upgraded INTEGER NOT NULL DEFAULT 0")
        log.info("Migration: added is_upgraded column to player_flowers")

    player_cols = {row[1] for row in cur.execute("PRAGMA table_info(players)")}
    if "is_vip" not in player_cols:
        cur.execute("ALTER TABLE players ADD COLUMN is_vip INTEGER NOT NULL DEFAULT 0")
        log.info("Migration: added is_vip column to players")

    cfg_cols = {row[1] for row in cur.execute("PRAGMA table_info(guild_config)")}
    if "approved" not in cfg_cols:
        cur.execute("ALTER TABLE guild_config ADD COLUMN approved INTEGER NOT NULL DEFAULT 0")
        log.info("Migration: added approved column to guild_config")

    conn.commit()
    conn.close()
    log.info("Database ready: %s", DB_PATH)


# ------------------------------------------------------------------
# GUILD CONFIG HELPERS
# ------------------------------------------------------------------

def get_guild_config(guild_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (str(guild_id),)
        ).fetchone()
        return dict(row) if row else None


def is_setup_complete(guild_id: str) -> bool:
    """A guild is set up once leader roles are configured."""
    return bool(get_leader_role_ids(str(guild_id)))


def is_approved(guild_id: str) -> bool:
    """Returns True if this guild is whitelisted to use the bot."""
    cfg = get_guild_config(str(guild_id))
    return bool(cfg and cfg.get("approved"))


def get_leader_role_ids(guild_id: str) -> list[int]:
    cfg = get_guild_config(str(guild_id))
    if not cfg:
        return []
    try:
        return [int(r) for r in json.loads(cfg.get("leader_role_ids", "[]"))]
    except (ValueError, TypeError):
        return []


def upsert_guild_config(guild_id: str, **kwargs) -> None:
    """Insert or update specific guild config fields."""
    cfg = get_guild_config(str(guild_id))

    for key in ("leader_role_ids",):
        if key in kwargs and isinstance(kwargs[key], list):
            kwargs[key] = json.dumps(kwargs[key])

    if cfg is None:
        fields = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" for _ in kwargs)
        values = list(kwargs.values())
        with get_db() as conn:
            conn.execute(
                f"INSERT INTO guild_config (guild_id, {fields}) VALUES (?, {placeholders})",
                [str(guild_id)] + values,
            )
    else:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values())
        with get_db() as conn:
            conn.execute(
                f"UPDATE guild_config SET {sets}, updated_at = datetime('now') WHERE guild_id = ?",
                values + [str(guild_id)],
            )
