"""
db/queries.py
Dreamweaving Garden Bot — Common database queries
All queries are guild-scoped to support multiple servers cleanly.
"""

import json
import sqlite3
from db.schema import get_db, init_db  # re-exported so bot.py can import from here


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


def update_player_ign(guild_id: str, discord_id: str, new_ign: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            """UPDATE players SET ign = ?
               WHERE guild_id = ? AND discord_id = ?""",
            (new_ign.strip(), str(guild_id), str(discord_id)),
        )
        return cur.rowcount > 0


def set_player_vip(guild_id: str, discord_id: str, is_vip: bool) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE players SET is_vip = ? WHERE guild_id = ? AND discord_id = ?",
            (1 if is_vip else 0, str(guild_id), str(discord_id)),
        )
        return cur.rowcount > 0


def get_player_vip(guild_id: str, discord_id: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT is_vip FROM players WHERE guild_id = ? AND discord_id = ?",
            (str(guild_id), str(discord_id)),
        ).fetchone()
        return bool(row["is_vip"]) if row else False


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
    """Returns True on success, False if already tracked OR flower doesn't exist."""
    if not get_flower(flower_name):
        return False
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


def get_player_missing_flowers(guild_id: str, discord_id: str) -> list[str]:
    """Return flower names from the master list that this player does not have."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT f.name FROM flowers f
               WHERE NOT EXISTS (
                   SELECT 1 FROM player_flowers pf
                   WHERE pf.guild_id = ? AND pf.discord_id = ? AND pf.flower_name = f.name
               )
               ORDER BY f.name COLLATE NOCASE""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [r["name"] for r in rows]


def get_player_flowers_with_points(guild_id: str, discord_id: str) -> list[dict]:
    """Return player's flowers with rarity and base_points. Used for /my flowers display."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT pf.flower_name AS name, f.rarity, f.base_points
               FROM player_flowers pf
               JOIN flowers f ON f.name = pf.flower_name
               WHERE pf.guild_id = ? AND pf.discord_id = ?
               ORDER BY f.base_points DESC, pf.flower_name COLLATE NOCASE""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [dict(r) for r in rows]


def get_player_missing_flowers_with_points(guild_id: str, discord_id: str) -> list[dict]:
    """Return missing flowers with rarity and base_points. Used for /my missing flowers display."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT f.name, f.rarity, f.base_points FROM flowers f
               WHERE NOT EXISTS (
                   SELECT 1 FROM player_flowers pf
                   WHERE pf.guild_id = ? AND pf.discord_id = ? AND pf.flower_name = f.name
               )
               ORDER BY f.base_points DESC, f.name COLLATE NOCASE""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [dict(r) for r in rows]


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


def find_vase_match(query: str) -> str | None:
    """Fuzzy vase name match — exact first, then starts-with, then contains."""
    query = query.strip().lower()
    vases = get_all_vases()
    names = [v["name"] for v in vases]

    exact = next((n for n in names if n.lower() == query), None)
    if exact:
        return exact
    starts = next((n for n in names if n.lower().startswith(query)), None)
    if starts:
        return starts
    contains = next((n for n in names if query in n.lower()), None)
    return contains


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


def get_vase_names_for_autocomplete() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT name FROM master_vases ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [r["name"] for r in rows]


# ------------------------------------------------------------------
# PLAYER VASES
# ------------------------------------------------------------------

def get_player_vases(guild_id: str, discord_id: str) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT vase_name FROM player_vases
               WHERE guild_id = ? AND discord_id = ?
               ORDER BY vase_name COLLATE NOCASE""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [r["vase_name"] for r in rows]


def add_player_vase(guild_id: str, discord_id: str, vase_name: str,
                    source_type: str = "manual", logged_by: str = None) -> bool:
    """Returns True on success, False if already tracked OR vase doesn't exist."""
    if not get_vase(vase_name):
        return False
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO player_vases
                   (guild_id, discord_id, vase_name, source_type, logged_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(guild_id), str(discord_id), vase_name, source_type, logged_by),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def remove_player_vase(guild_id: str, discord_id: str, vase_name: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            """DELETE FROM player_vases
               WHERE guild_id = ? AND discord_id = ? AND vase_name = ?""",
            (str(guild_id), str(discord_id), vase_name),
        )
        return cur.rowcount > 0


def get_players_with_vase(guild_id: str, vase_name: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.discord_id, p.ign, p.discord_name
               FROM player_vases pv
               JOIN players p ON p.guild_id = pv.guild_id AND p.discord_id = pv.discord_id
               WHERE pv.guild_id = ? AND pv.vase_name = ?
               ORDER BY p.ign COLLATE NOCASE""",
            (str(guild_id), vase_name),
        ).fetchall()
        return [dict(r) for r in rows]


def get_guild_missing_vases(guild_id: str) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT mv.name FROM master_vases mv
               WHERE NOT EXISTS (
                   SELECT 1 FROM player_vases pv
                   WHERE pv.guild_id = ? AND pv.vase_name = mv.name
               )
               ORDER BY mv.name COLLATE NOCASE""",
            (str(guild_id),),
        ).fetchall()
        return [r["name"] for r in rows]


def get_player_missing_vases(guild_id: str, discord_id: str) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT mv.name FROM master_vases mv
               WHERE NOT EXISTS (
                   SELECT 1 FROM player_vases pv
                   WHERE pv.guild_id = ? AND pv.discord_id = ? AND pv.vase_name = mv.name
               )
               ORDER BY mv.name COLLATE NOCASE""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [r["name"] for r in rows]


def get_player_vases_with_points(guild_id: str, discord_id: str) -> list[dict]:
    """Return player's vases with rarity and base_points. Used for /my vases display."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT pv.vase_name AS name, mv.rarity, mv.base_points
               FROM player_vases pv
               JOIN master_vases mv ON mv.name = pv.vase_name
               WHERE pv.guild_id = ? AND pv.discord_id = ?
               ORDER BY mv.base_points DESC, pv.vase_name COLLATE NOCASE""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [dict(r) for r in rows]


def get_player_missing_vases_with_points(guild_id: str, discord_id: str) -> list[dict]:
    """Return missing vases with rarity and base_points. Used for /my missing vases display."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT mv.name, mv.rarity, mv.base_points FROM master_vases mv
               WHERE NOT EXISTS (
                   SELECT 1 FROM player_vases pv
                   WHERE pv.guild_id = ? AND pv.discord_id = ? AND pv.vase_name = mv.name
               )
               ORDER BY mv.base_points DESC, mv.name COLLATE NOCASE""",
            (str(guild_id), str(discord_id)),
        ).fetchall()
        return [dict(r) for r in rows]


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


def reset_league_week(guild_id: str, week_start: str) -> int:
    """Wipe all league state for the given week. Returns rows deleted."""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM league_state WHERE guild_id = ? AND week_start = ?",
            (str(guild_id), week_start),
        )
        return cur.rowcount


# ------------------------------------------------------------------
# LEAGUE CALL — top flowers for the call announcement
# ------------------------------------------------------------------

def get_top_flowers_for_league_call(guild_id: str, top_n: int = 2) -> list[dict]:
    """
    Return the top N distinct flowers (by effective points) held by any player
    in the guild, along with all players who hold each flower and whether they
    have it upgraded.

    Each returned dict has:
        flower_name   str
        base_points   int
        effective_pts int   (base_points * 2 if upgraded, else base_points)
        is_upgraded   bool
        holders       list[dict]  — each: {discord_id, ign, discord_name}
        other_holders list[dict]  — same shape; same flower, different upgrade status
                                    (present so the caller can mention them separately)
    """
    with get_db() as conn:
        # Pull every (player, flower, upgrade-status, points) combo for this guild
        rows = conn.execute(
            """
            SELECT
                pf.discord_id,
                pf.flower_name,
                pf.is_upgraded,
                CASE WHEN pf.is_upgraded THEN f.base_points * 2
                     ELSE f.base_points END AS effective_pts,
                f.base_points,
                p.ign,
                p.discord_name
            FROM player_flowers pf
            JOIN flowers f ON f.name = pf.flower_name
            JOIN players p ON p.guild_id = pf.guild_id AND p.discord_id = pf.discord_id
            WHERE pf.guild_id = ?
            ORDER BY effective_pts DESC, pf.flower_name COLLATE NOCASE
            """,
            (str(guild_id),),
        ).fetchall()

    # Group by (flower_name, is_upgraded) to find unique scoring combos
    from collections import defaultdict
    combos: dict[tuple, dict] = {}  # (flower_name, is_upgraded) -> aggregated entry

    for row in rows:
        key = (row["flower_name"], bool(row["is_upgraded"]))
        if key not in combos:
            combos[key] = {
                "flower_name":   row["flower_name"],
                "base_points":   row["base_points"],
                "effective_pts": row["effective_pts"],
                "is_upgraded":   bool(row["is_upgraded"]),
                "holders":       [],
            }
        combos[key]["holders"].append({
            "discord_id":   row["discord_id"],
            "ign":          row["ign"],
            "discord_name": row["discord_name"],
        })

    # Sort combos by effective_pts descending, then flower name for stability
    sorted_combos = sorted(
        combos.values(),
        key=lambda c: (-c["effective_pts"], c["flower_name"].lower()),
    )

    return sorted_combos[:top_n]


# ------------------------------------------------------------------
# LEAGUE CALL — classify holders of a chosen flower by where it ranks
# ------------------------------------------------------------------

def get_league_call_holders(guild_id: str, flower_name: str, is_upgraded: bool) -> dict:
    """
    For a chosen flower + upgrade tier, find every guild member who owns it,
    then rank it against each person's full flower collection to classify them:

      best        — this flower is their single highest-scoring flower (ping)
      second_best — this flower ties or ranks 2nd in their collection (ping)
      rest        — they own it but it falls below their top 2 (list only)

    The chosen flower's effective_pts = base_points * 2 if is_upgraded else base_points.
    Each holder's other flowers are scored at their own upgrade status.

    Returns:
        {
            "flower_name":   str,
            "base_points":   int,
            "effective_pts": int,
            "is_upgraded":   bool,
            "best":          list[dict],   # {discord_id, ign, discord_name}
            "second_best":   list[dict],
            "rest":          list[dict],
        }
    """
    with get_db() as conn:
        # 1. Resolve the chosen flower's base points
        flower_row = conn.execute(
            "SELECT base_points FROM flowers WHERE LOWER(name) = LOWER(?)",
            (flower_name.strip(),),
        ).fetchone()
        if not flower_row:
            return {}

        base_pts     = flower_row["base_points"]
        chosen_pts   = base_pts * 2 if is_upgraded else base_pts

        # 2. Pull every (player, flower, effective_pts) for the guild in one query
        all_rows = conn.execute(
            """
            SELECT
                pf.discord_id,
                pf.flower_name,
                pf.is_upgraded,
                CASE WHEN pf.is_upgraded THEN f.base_points * 2
                     ELSE f.base_points END AS effective_pts,
                p.ign,
                p.discord_name
            FROM player_flowers pf
            JOIN flowers f ON f.name = pf.flower_name
            JOIN players p
              ON p.guild_id = pf.guild_id AND p.discord_id = pf.discord_id
            WHERE pf.guild_id = ?
            """,
            (str(guild_id),),
        ).fetchall()

    # 3. Find everyone who owns the chosen flower (upgrade status is a call-time
    #    declaration by the caller — we don't filter by the player's stored is_upgraded)
    holders = {
        r["discord_id"]: {"discord_id": r["discord_id"], "ign": r["ign"], "discord_name": r["discord_name"]}
        for r in all_rows
        if r["flower_name"].lower() == flower_name.strip().lower()
    }

    if not holders:
        return {
            "flower_name":   flower_name,
            "base_points":   base_pts,
            "effective_pts": chosen_pts,
            "is_upgraded":   is_upgraded,
            "best":          [],
            "second_best":   [],
            "rest":          [],
        }

    # 4. For each holder, build a sorted list of their flower points and find
    #    where chosen_pts ranks (1st or 2nd)
    from collections import defaultdict
    player_scores: dict[str, list[int]] = defaultdict(list)
    for r in all_rows:
        if r["discord_id"] in holders:
            player_scores[r["discord_id"]].append(r["effective_pts"])

    best, second_best, rest = [], [], []

    for discord_id, player in holders.items():
        scores = sorted(player_scores[discord_id], reverse=True)
        # scores[0] = their best, scores[1] = second best (if exists)
        if not scores:
            rest.append(player)
            continue

        top1 = scores[0]
        top2 = scores[1] if len(scores) > 1 else None

        if chosen_pts >= top1:
            # It IS their best (or tied for best)
            best.append(player)
        elif top2 is not None and chosen_pts >= top2:
            # It's their second best (or tied for second)
            second_best.append(player)
        else:
            rest.append(player)

    # Sort each group by IGN
    key = lambda p: p["ign"].lower()
    return {
        "flower_name":   flower_name,
        "base_points":   base_pts,
        "effective_pts": chosen_pts,
        "is_upgraded":   is_upgraded,
        "best":          sorted(best, key=key),
        "second_best":   sorted(second_best, key=key),
        "rest":          sorted(rest, key=key),
    }
