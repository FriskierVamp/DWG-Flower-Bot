"""
db/queries.py
Dreamweaving Garden Bot — Common database queries
All queries are guild-scoped to support multiple servers cleanly.
"""

import json
import sqlite3
from db.schema import get_db


# ------------------------------------------------------------------
# PLAYERS
# ------------------------------------------------------------------

def find_player(guild_id: str, discord_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM players WHERE guild_id = ? AND discord_id = ?",
            (str(guild_id), str(discord_id)),
        ).fetchone()
        return dict(row) if row else None


def find_player_by_ign(guild_id: str, ign: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM players WHERE guild_id = ? AND LOWER(ign) = LOWER(?)",
            (str(guild_id), ign.strip()),
        ).fetchone()
        return dict(row) if row else None


def get_all_players(guild_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM players WHERE guild_id = ? ORDER BY ign COLLATE NOCASE",
            (str(guild_id),),
        ).fetchall()
        return [dict(r) for r in rows]


def register_player(guild_id: str, discord_id: str, discord_name: str, ign: str) -> bool:
    """Insert a new player. Returns True on success, False if already registered."""
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO players (guild_id, discord_id, discord_name, ign)
                   VALUES (?, ?, ?, ?)""",
                (str(guild_id), str(discord_id), discord_name, ign.strip()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def remove_player(guild_id: str, discord_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM players WHERE guild_id = ? AND discord_id = ?",
            (str(guild_id), str(discord_id)),
        )
        return cur.rowcount > 0


# ------------------------------------------------------------------
# FLOWERS (master list — global, not per-guild)
# ------------------------------------------------------------------

VALID_RARITIES = {"Basic", "Fine", "Rare", "Star", "Shine"}
RARITY_ORDER   = {"Shine": 0, "Star": 1, "Rare": 2, "Fine": 3, "Basic": 4}


def normalize_rarity(value: str) -> str:
    cleaned = value.strip().title()
    return cleaned if cleaned in VALID_RARITIES else value.strip().title()


def get_all_flowers() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, name, rarity, base_points,
                      (base_points * 2) AS upgraded_points,
                      upgrade_cost, source, created_at, updated_at
               FROM flowers ORDER BY name COLLATE NOCASE"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_flower(name: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT id, name, rarity, base_points,
                      (base_points * 2) AS upgraded_points,
                      upgrade_cost, source
               FROM flowers WHERE LOWER(name) = LOWER(?)""",
            (name.strip(),),
        ).fetchone()
        return dict(row) if row else None


def find_flower_match(query: str) -> str | None:
    """Fuzzy flower name match — exact first, then starts-with, then contains."""
    query = query.strip().lower()
    flowers = get_all_flowers()
    names = [f["name"] for f in flowers]

    exact = next((n for n in names if n.lower() == query), None)
    if exact:
        return exact
    starts = next((n for n in names if n.lower().startswith(query)), None)
    if starts:
        return starts
    contains = next((n for n in names if query in n.lower()), None)
    return contains


def upsert_flower(name: str, rarity: str, base_points: int,
                  upgrade_cost: int, source: str) -> None:
    rarity = normalize_rarity(rarity)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO flowers (name, rarity, base_points, upgrade_cost, source)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   rarity       = excluded.rarity,
                   base_points  = excluded.base_points,
                   upgrade_cost = excluded.upgrade_cost,
                   source       = excluded.source,
                   updated_at   = datetime('now')""",
            (name.strip(), rarity, base_points, upgrade_cost, source.strip()),
        )


def delete_flower(name: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM flowers WHERE LOWER(name) = LOWER(?)", (name.strip(),))
        return cur.rowcount > 0


def get_flower_names_for_autocomplete() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT name FROM flowers ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [r["name"] for r in rows]


# ------------------------------------------------------------------
# PLAYER FLOWERS
# ------------------------------------------------------------------

def get_player_flowers(guild_id: str, discord_id: str) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT flower_name FROM player_flowers
               WHERE guild_id = ? AND discord_id = ?
               ORDER BY flower_name COLLATE NOCASE""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [r["flower_name"] for r in rows]


def add_player_flower(guild_id: str, discord_id: str, flower_name: str,
                      source_type: str = "manual", logged_by: str = None) -> bool:
    """Returns True on success, False if already tracked."""
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO player_flowers
                   (guild_id, discord_id, flower_name, source_type, logged_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(guild_id), str(discord_id), flower_name, source_type, logged_by),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def remove_player_flower(guild_id: str, discord_id: str, flower_name: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            """DELETE FROM player_flowers
               WHERE guild_id = ? AND discord_id = ? AND flower_name = ?""",
            (str(guild_id), str(discord_id), flower_name),
        )
        return cur.rowcount > 0


def get_players_with_flower(guild_id: str, flower_name: str) -> list[dict]:
    """Return all players in a guild who have a specific flower."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.discord_id, p.ign, p.discord_name
               FROM player_flowers pf
               JOIN players p ON p.guild_id = pf.guild_id AND p.discord_id = pf.discord_id
               WHERE pf.guild_id = ? AND pf.flower_name = ?
               ORDER BY p.ign COLLATE NOCASE""",
            (str(guild_id), flower_name),
        ).fetchall()
        return [dict(r) for r in rows]


def get_guild_missing_flowers(guild_id: str) -> list[str]:
    """Return flower names that no player in the guild has."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT f.name FROM flowers f
               WHERE NOT EXISTS (
                   SELECT 1 FROM player_flowers pf
                   WHERE pf.guild_id = ? AND pf.flower_name = f.name
               )
               ORDER BY f.name COLLATE NOCASE""",
            (str(guild_id),),
        ).fetchall()
        return [r["name"] for r in rows]


# ------------------------------------------------------------------
# VASES
# ------------------------------------------------------------------

def get_player_vases(guild_id: str, discord_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM vases WHERE guild_id = ? AND discord_id = ?
               ORDER BY vase_type COLLATE NOCASE""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_vase(guild_id: str, discord_id: str, vase_type: str,
                quantity: int, source_type: str = "manual",
                logged_by: str = None) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO vases (guild_id, discord_id, vase_type, quantity, source_type, logged_by)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, discord_id, vase_type) DO UPDATE SET
                   quantity   = excluded.quantity,
                   source_type = excluded.source_type,
                   logged_by  = excluded.logged_by,
                   updated_at = datetime('now')""",
            (str(guild_id), str(discord_id), vase_type.strip(),
             quantity, source_type, logged_by),
        )


# ------------------------------------------------------------------
# MASTER VASE LIST (global — mirrors flower list for admin dashboard)
# ------------------------------------------------------------------

def get_all_vases() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, name, rarity, base_points,
                      (base_points * 2) AS upgraded_points,
                      upgrade_cost, source, created_at, updated_at
               FROM master_vases ORDER BY name COLLATE NOCASE"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_vase(name: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT id, name, rarity, base_points,
                      (base_points * 2) AS upgraded_points,
                      upgrade_cost, source
               FROM master_vases WHERE LOWER(name) = LOWER(?)""",
            (name.strip(),),
        ).fetchone()
        return dict(row) if row else None


def upsert_master_vase(name: str, rarity: str, base_points: int,
                       upgrade_cost: int, source: str) -> None:
    rarity = normalize_rarity(rarity)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO master_vases (name, rarity, base_points, upgrade_cost, source)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   rarity       = excluded.rarity,
                   base_points  = excluded.base_points,
                   upgrade_cost = excluded.upgrade_cost,
                   source       = excluded.source,
                   updated_at   = datetime('now')""",
            (name.strip(), rarity, base_points, upgrade_cost, source.strip()),
        )


def delete_vase(name: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM master_vases WHERE LOWER(name) = LOWER(?)", (name.strip(),))
        return cur.rowcount > 0


# ------------------------------------------------------------------
# LEAGUE LOG
# ------------------------------------------------------------------

def log_league_entry(guild_id: str, discord_id: str, season: str,
                     rank: int, points: int, source_type: str = "manual",
                     logged_by: str = None) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO league_log
               (guild_id, discord_id, season, rank, points, source_type, logged_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(guild_id), str(discord_id), season, rank, points,
             source_type, logged_by),
        )


def get_latest_league_entry(guild_id: str, discord_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM league_log WHERE guild_id = ? AND discord_id = ?
               ORDER BY logged_at DESC LIMIT 1""",
            (str(guild_id), str(discord_id)),
        ).fetchone()
        return dict(row) if row else None


def get_guild_league_standings(guild_id: str, season: str = None) -> list[dict]:
    """Latest league entry per player for a given season (or most recent)."""
    with get_db() as conn:
        if season:
            rows = conn.execute(
                """SELECT p.ign, p.discord_id, l.rank, l.points, l.season, l.logged_at
                   FROM league_log l
                   JOIN players p ON p.guild_id = l.guild_id AND p.discord_id = l.discord_id
                   WHERE l.guild_id = ? AND l.season = ?
                   GROUP BY l.discord_id HAVING MAX(l.logged_at)
                   ORDER BY l.rank ASC""",
                (str(guild_id), season),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT p.ign, p.discord_id, l.rank, l.points, l.season, l.logged_at
                   FROM league_log l
                   JOIN players p ON p.guild_id = l.guild_id AND p.discord_id = l.discord_id
                   WHERE l.guild_id = ?
                   GROUP BY l.discord_id HAVING MAX(l.logged_at)
                   ORDER BY l.rank ASC""",
                (str(guild_id),),
            ).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------------
# CONTRIBUTIONS
# ------------------------------------------------------------------

def log_contribution(guild_id: str, discord_id: str, amount: int,
                     contribution_date: str = None, note: str = None,
                     source_type: str = "manual", logged_by: str = None) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO contributions
               (guild_id, discord_id, amount, contribution_date, note, source_type, logged_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(guild_id), str(discord_id), amount, contribution_date,
             note, source_type, logged_by),
        )


def get_player_contributions(guild_id: str, discord_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM contributions WHERE guild_id = ? AND discord_id = ?
               ORDER BY logged_at DESC""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [dict(r) for r in rows]


def get_guild_contribution_totals(guild_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.ign, p.discord_id, SUM(c.amount) AS total
               FROM contributions c
               JOIN players p ON p.guild_id = c.guild_id AND p.discord_id = c.discord_id
               WHERE c.guild_id = ?
               GROUP BY c.discord_id
               ORDER BY total DESC""",
            (str(guild_id),),
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------------
# LEAGUE STATE (weekly event tracking)
# ------------------------------------------------------------------

def get_league_state(guild_id: str, discord_id: str, week_start: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM league_state
               WHERE guild_id = ? AND discord_id = ? AND week_start = ?""",
            (str(guild_id), str(discord_id), week_start),
        ).fetchone()
        return dict(row) if row else None


def set_league_lock(guild_id: str, discord_id: str, week_start: str,
                    locked: bool = True) -> None:
    import datetime
    locked_at = datetime.datetime.utcnow().isoformat() if locked else None
    with get_db() as conn:
        conn.execute(
            """INSERT INTO league_state (guild_id, discord_id, week_start, is_locked, locked_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, discord_id, week_start) DO UPDATE SET
                   is_locked = excluded.is_locked,
                   locked_at = excluded.locked_at""",
            (str(guild_id), str(discord_id), week_start, int(locked), locked_at),
        )


def get_guild_league_state(guild_id: str, week_start: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT ls.*, p.ign FROM league_state ls
               JOIN players p ON p.guild_id = ls.guild_id AND p.discord_id = ls.discord_id
               WHERE ls.guild_id = ? AND ls.week_start = ?""",
            (str(guild_id), week_start),
        ).fetchall()
        return [dict(r) for r in rows]
