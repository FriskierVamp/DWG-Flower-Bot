"""
db/schema.py
Dreamweaving Garden Bot — Database Schema
All tables include guild_id so the bot can serve multiple servers cleanly.
"""

import sqlite3
import os
import logging

log = logging.getLogger("dwg.db")

DB_DIR  = os.getenv("DB_DIR", "/data" if os.path.isdir("/data") else ".")
DB_PATH = os.path.join(DB_DIR, "dreamweaving.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL") # safe for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = get_db()
    cur  = conn.cursor()

    # ------------------------------------------------------------------
    # GUILD CONFIG
    # Stores per-server settings set during /setup.
    # leader_role_ids: JSON array of Discord role IDs that grant leader access.
    # new_role_id / member_role_id: the two roles swapped on /register.
    # log_channel_id: channel where screenshot logs are posted publicly.
    # setup_complete: 0/1 flag — bot refuses most commands until this is 1.
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS guild_config (
        guild_id        TEXT PRIMARY KEY,
        guild_name      TEXT,
        leader_role_ids TEXT NOT NULL DEFAULT '[]',
        new_role_id     TEXT,
        member_role_id  TEXT,
        log_channel_id  TEXT,
        setup_complete  INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    # ------------------------------------------------------------------
    # PLAYERS
    # One row per registered player per guild.
    # discord_id: the user's permanent Discord snowflake ID.
    # ign: in-game name supplied at /register.
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        TEXT NOT NULL,
        discord_id      TEXT NOT NULL,
        discord_name    TEXT,
        ign             TEXT NOT NULL,
        registered_at   TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(guild_id, discord_id)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_players_guild ON players(guild_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_players_discord ON players(guild_id, discord_id)")

    # ------------------------------------------------------------------
    # MASTER FLOWER LIST
    # Global — not per-guild. Managed via the Flask admin dashboard.
    # upgraded_points is always base_points * 2; stored for query convenience.
    # upgrade_cost is in diamonds.
    # rarity: Basic, Fine, Rare, Star, Shine (title case, normalized on insert)
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
    # MASTER VASE LIST
    # Global — not per-guild. Managed via the Flask admin dashboard.
    # Mirrors the flowers table structure.
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
    # Tracks which flowers each player owns.
    # source_type: 'screenshot' or 'manual' — how the entry was created.
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_flowers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        TEXT NOT NULL,
        discord_id      TEXT NOT NULL,
        flower_name     TEXT NOT NULL,
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
    # VASES
    # Per-player vase inventory per guild.
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vases (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        TEXT NOT NULL,
        discord_id      TEXT NOT NULL,
        vase_type       TEXT NOT NULL,
        quantity        INTEGER NOT NULL DEFAULT 1,
        source_type     TEXT NOT NULL DEFAULT 'manual',
        logged_by       TEXT,
        logged_at       TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vases_guild ON vases(guild_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vases_player ON vases(guild_id, discord_id)")

    # ------------------------------------------------------------------
    # LEAGUE LOG
    # Tracks league standing snapshots per player per season.
    # Multiple entries allowed — each screenshot/manual entry is a new row.
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
    # Tracks contribution entries per player.
    # amount: numeric contribution value from the game.
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
    # LEAGUE COMPETITION STATE
    # Tracks per-player state during an active league event week.
    # Replaces TCF's comp_locked / comp_stats JSON blob.
    # flowers_used: JSON array of flower names used this week.
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

    conn.commit()
    conn.close()
    log.info("Database ready: %s", DB_PATH)


# ------------------------------------------------------------------
# HELPER — guild config accessors
# ------------------------------------------------------------------

def get_guild_config(guild_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (str(guild_id),)
        ).fetchone()
        return dict(row) if row else None


def is_setup_complete(guild_id: str) -> bool:
    cfg = get_guild_config(str(guild_id))
    return bool(cfg and cfg.get("setup_complete"))


def get_leader_role_ids(guild_id: str) -> list[int]:
    import json
    cfg = get_guild_config(str(guild_id))
    if not cfg:
        return []
    try:
        return [int(r) for r in json.loads(cfg.get("leader_role_ids", "[]"))]
    except (ValueError, TypeError):
        return []


def upsert_guild_config(guild_id: str, **kwargs) -> None:
    """Insert or update specific guild config fields."""
    import json
    cfg = get_guild_config(str(guild_id))

    # Serialize list fields
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
