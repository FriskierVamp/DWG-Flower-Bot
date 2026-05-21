"""
admin/dashboard.py
Dreamweaving Garden Bot — Flask admin dashboard
Rethemed to match DWG artwork: soft pastels, warm cream, cozy garden aesthetic.
"""

import os
import hmac
import json
import logging
import threading
import secrets
from functools import wraps

from flask import Flask, jsonify, request, render_template_string, session, redirect, url_for

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.queries import (
    get_all_flowers, upsert_flower, delete_flower, get_flower,
    get_all_vases,  upsert_master_vase as upsert_vase,   delete_vase,   get_vase,
    normalize_rarity, VALID_RARITIES, RARITY_ORDER,
)

log          = logging.getLogger("dwg.admin")
admin_app    = Flask(__name__)
admin_app.secret_key = os.getenv("FLASK_SECRET", secrets.token_hex(32))
ADMIN_SECRET = os.getenv("ADMIN_PASSWORD", "changeme")
ADMIN_PORT   = int(os.getenv("ADMIN_PORT", 5000))


# ------------------------------------------------------------------
# AUTH — session based
# ------------------------------------------------------------------

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ------------------------------------------------------------------
# API ROUTES
# ------------------------------------------------------------------

@admin_app.route("/api/flowers", methods=["GET"])
@require_login
def api_get_flowers():
    flowers = get_all_flowers()
    flowers.sort(key=lambda f: (
        RARITY_ORDER.get(normalize_rarity(f["rarity"]), 99),
        f["name"].lower()
    ))
    return jsonify(flowers)


@admin_app.route("/api/flowers", methods=["POST"])
@require_login
def api_add_flower():
    data = request.get_json(silent=True) or {}
    name         = str(data.get("name", "")).strip()
    rarity       = str(data.get("rarity", "")).strip()
    base_points  = data.get("base_points", 0)
    upgrade_cost = data.get("upgrade_cost", 0)
    source       = str(data.get("source", "Unknown")).strip()

    if not name:
        return jsonify({"error": "Flower name is required."}), 400
    if normalize_rarity(rarity) not in VALID_RARITIES:
        return jsonify({"error": f"Invalid rarity. Must be one of: {', '.join(sorted(VALID_RARITIES, key=lambda r: RARITY_ORDER.get(r,99)))}"}), 400
    try:
        base_points  = int(base_points)
        upgrade_cost = int(upgrade_cost)
    except (TypeError, ValueError):
        return jsonify({"error": "base_points and upgrade_cost must be integers."}), 400

    upsert_flower(name, rarity, base_points, upgrade_cost, source)
    return jsonify({"status": "ok", "name": name})


@admin_app.route("/api/flowers/<path:name>", methods=["PUT"])
@require_login
def api_update_flower(name: str):
    data = request.get_json(silent=True) or {}
    from db.queries import get_flower
    existing = get_flower(name)
    if not existing:
        return jsonify({"error": f'Flower "{name}" not found.'}), 404

    rarity       = str(data.get("rarity",       existing["rarity"])).strip()
    base_points  = data.get("base_points",  existing["base_points"])
    upgrade_cost = data.get("upgrade_cost", existing["upgrade_cost"])
    source       = str(data.get("source",   existing["source"])).strip()

    if normalize_rarity(rarity) not in VALID_RARITIES:
        return jsonify({"error": "Invalid rarity."}), 400
    try:
        base_points  = int(base_points)
        upgrade_cost = int(upgrade_cost)
    except (TypeError, ValueError):
        return jsonify({"error": "base_points and upgrade_cost must be integers."}), 400

    upsert_flower(name, rarity, base_points, upgrade_cost, source)
    return jsonify({"status": "ok", "name": name})


@admin_app.route("/api/flowers/<path:name>", methods=["DELETE"])
@require_login
def api_delete_flower(name: str):
    deleted = delete_flower(name)
    if not deleted:
        return jsonify({"error": f'Flower "{name}" not found.'}), 404
    return jsonify({"status": "ok", "name": name})




# ------------------------------------------------------------------
# BULK IMPORT — accepts CSV/TSV text parsed client-side from Excel
# Columns: Flower Name, Type, How to Obtain, Points, Cost to upgrade
# ------------------------------------------------------------------

@admin_app.route("/api/flowers/bulk", methods=["POST"])
@require_login
def api_bulk_import():
    data  = request.get_json(silent=True) or {}
    rows  = data.get("rows", [])
    if not rows:
        return jsonify({"error": "No rows provided."}), 400

    imported = 0
    skipped  = 0
    errors   = []

    for i, row in enumerate(rows):
        name   = str(row.get("name",   "")).strip()
        rarity = str(row.get("rarity", "")).strip()
        source = str(row.get("source", "Unknown")).strip() or "Unknown"

        raw_pts  = str(row.get("points",       "")).strip()
        raw_cost = str(row.get("upgrade_cost", "")).strip()

        try:
            base_points  = int(float(raw_pts))  if raw_pts  else 0
        except ValueError:
            base_points  = 0
        try:
            upgrade_cost = int(float(raw_cost)) if raw_cost else 0
        except ValueError:
            upgrade_cost = 0

        if not name:
            skipped += 1
            continue

        norm = normalize_rarity(rarity)
        if norm not in VALID_RARITIES:
            errors.append(f"Row {i+1}: '{name}' has invalid rarity '{rarity}' — skipped.")
            skipped += 1
            continue

        upsert_flower(name, norm, base_points, upgrade_cost, source)
        imported += 1

    return jsonify({
        "status":   "ok",
        "imported": imported,
        "skipped":  skipped,
        "errors":   errors,
    })
@admin_app.route("/api/rarities", methods=["GET"])
@require_login
def api_rarities():
    rarities = sorted(VALID_RARITIES, key=lambda r: RARITY_ORDER.get(r, 99))
    return jsonify(rarities)


# ------------------------------------------------------------------
# VASE API ROUTES  (mirrors flower routes exactly)
# ------------------------------------------------------------------

@admin_app.route("/api/vases", methods=["GET"])
@require_login
def api_get_vases():
    vases = get_all_vases()
    vases.sort(key=lambda v: (
        RARITY_ORDER.get(normalize_rarity(v["rarity"]), 99),
        v["name"].lower()
    ))
    return jsonify(vases)


@admin_app.route("/api/vases", methods=["POST"])
@require_login
def api_add_vase():
    data         = request.get_json(silent=True) or {}
    name         = str(data.get("name", "")).strip()
    rarity       = str(data.get("rarity", "")).strip()
    base_points  = data.get("base_points", 0)
    upgrade_cost = data.get("upgrade_cost", 0)
    source       = str(data.get("source", "Unknown")).strip()

    if not name:
        return jsonify({"error": "Vase name is required."}), 400
    if normalize_rarity(rarity) not in VALID_RARITIES:
        return jsonify({"error": f"Invalid rarity. Must be one of: {', '.join(sorted(VALID_RARITIES, key=lambda r: RARITY_ORDER.get(r,99)))}"}), 400
    try:
        base_points  = int(base_points)
        upgrade_cost = int(upgrade_cost)
    except (TypeError, ValueError):
        return jsonify({"error": "base_points and upgrade_cost must be integers."}), 400

    upsert_vase(name, rarity, base_points, upgrade_cost, source)
    return jsonify({"status": "ok", "name": name})


@admin_app.route("/api/vases/<path:name>", methods=["PUT"])
@require_login
def api_update_vase(name: str):
    data     = request.get_json(silent=True) or {}
    existing = get_vase(name)
    if not existing:
        return jsonify({"error": f'Vase "{name}" not found.'}), 404

    rarity       = str(data.get("rarity",       existing["rarity"])).strip()
    base_points  = data.get("base_points",  existing["base_points"])
    upgrade_cost = data.get("upgrade_cost", existing["upgrade_cost"])
    source       = str(data.get("source",   existing["source"])).strip()

    if normalize_rarity(rarity) not in VALID_RARITIES:
        return jsonify({"error": "Invalid rarity."}), 400
    try:
        base_points  = int(base_points)
        upgrade_cost = int(upgrade_cost)
    except (TypeError, ValueError):
        return jsonify({"error": "base_points and upgrade_cost must be integers."}), 400

    upsert_vase(name, rarity, base_points, upgrade_cost, source)
    return jsonify({"status": "ok", "name": name})


@admin_app.route("/api/vases/<path:name>", methods=["DELETE"])
@require_login
def api_delete_vase(name: str):
    deleted = delete_vase(name)
    if not deleted:
        return jsonify({"error": f'Vase "{name}" not found.'}), 404
    return jsonify({"status": "ok", "name": name})


@admin_app.route("/api/vases/bulk", methods=["POST"])
@require_login
def api_bulk_import_vases():
    data  = request.get_json(silent=True) or {}
    rows  = data.get("rows", [])
    if not rows:
        return jsonify({"error": "No rows provided."}), 400

    imported = 0
    skipped  = 0
    errors   = []

    for i, row in enumerate(rows):
        name   = str(row.get("name",   "")).strip()
        rarity = str(row.get("rarity", "")).strip()
        source = str(row.get("source", "Unknown")).strip() or "Unknown"

        raw_pts  = str(row.get("points",       "")).strip()
        raw_cost = str(row.get("upgrade_cost", "")).strip()

        try:
            base_points  = int(float(raw_pts))  if raw_pts  else 0
        except ValueError:
            base_points  = 0
        try:
            upgrade_cost = int(float(raw_cost)) if raw_cost else 0
        except ValueError:
            upgrade_cost = 0

        if not name:
            skipped += 1
            continue

        norm = normalize_rarity(rarity)
        if norm not in VALID_RARITIES:
            errors.append(f"Row {i+1}: '{name}' has invalid rarity '{rarity}' — skipped.")
            skipped += 1
            continue

        upsert_vase(name, norm, base_points, upgrade_cost, source)
        imported += 1

    return jsonify({
        "status":   "ok",
        "imported": imported,
        "skipped":  skipped,
        "errors":   errors,
    })


# ------------------------------------------------------------------
# SERVERS API
# ------------------------------------------------------------------

@admin_app.route("/api/servers", methods=["GET"])
@require_login
def api_get_servers():
    from db.schema import get_db
    from db.queries import get_all_players
    with get_db() as conn:
        rows = conn.execute(
            """SELECT guild_id, guild_name, created_at, updated_at
               FROM guild_config
               ORDER BY guild_name COLLATE NOCASE"""
        ).fetchall()
    servers = []
    for r in rows:
        d = dict(r)
        d["member_count"] = len(get_all_players(d["guild_id"]))
        servers.append(d)
    return jsonify(servers)


@admin_app.route("/api/servers/<guild_id>", methods=["GET"])
@require_login
def api_get_server_detail(guild_id: str):
    """Full server detail: config + activity stats."""
    import json as _json
    from db.schema  import get_db, get_guild_config
    from db.queries import get_all_players

    cfg = get_guild_config(guild_id)
    if not cfg:
        return jsonify({"error": "Server not found"}), 404

    # Parse leader role IDs (stored as JSON array of strings)
    try:
        leader_role_ids = _json.loads(cfg.get("leader_role_ids", "[]") or "[]")
    except (ValueError, TypeError):
        leader_role_ids = []

    # Activity stats
    with get_db() as conn:
        flower_count = conn.execute(
            "SELECT COUNT(*) AS c FROM player_flowers WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()["c"]
        vase_count = conn.execute(
            "SELECT COUNT(*) AS c FROM player_vases WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()["c"]
        contrib_row = conn.execute(
            """SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total
               FROM contributions WHERE guild_id = ?""",
            (str(guild_id),),
        ).fetchone()
        league_count = conn.execute(
            "SELECT COUNT(*) AS c FROM league_log WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()["c"]
        latest_season_row = conn.execute(
            """SELECT season FROM league_log
               WHERE guild_id = ? AND season IS NOT NULL
               ORDER BY logged_at DESC LIMIT 1""",
            (str(guild_id),),
        ).fetchone()
        latest_register_row = conn.execute(
            """SELECT registered_at FROM players
               WHERE guild_id = ? ORDER BY registered_at DESC LIMIT 1""",
            (str(guild_id),),
        ).fetchone()

    return jsonify({
        "guild_id":        cfg["guild_id"],
        "guild_name":      cfg.get("guild_name") or "",
        "leader_role_ids": [str(r) for r in leader_role_ids],
        "new_role_id":     cfg.get("new_role_id")    or "",
        "member_role_id":  cfg.get("member_role_id") or "",
        "created_at":      cfg.get("created_at"),
        "updated_at":      cfg.get("updated_at"),
        "stats": {
            "member_count":          len(get_all_players(guild_id)),
            "flowers_tracked":       flower_count,
            "vases_tracked":         vase_count,
            "contributions_logged":  contrib_row["n"],
            "contributions_total":   contrib_row["total"],
            "league_entries":        league_count,
            "latest_season":         (latest_season_row["season"] if latest_season_row else None),
            "latest_registration":   (latest_register_row["registered_at"][:10] if latest_register_row else None),
        },
    })


@admin_app.route("/api/servers/<guild_id>/config", methods=["PUT"])
@require_login
def api_update_server_config(guild_id: str):
    """Update editable guild_config fields. Only role-related fields are editable."""
    from db.schema import get_guild_config, upsert_guild_config

    if not get_guild_config(guild_id):
        return jsonify({"error": "Server not found"}), 404

    data = request.get_json(silent=True) or {}

    # Whitelist: only these fields are editable from the dashboard
    updates = {}

    # Leader roles — accept list of strings, validate each is digits
    if "leader_role_ids" in data:
        raw = data["leader_role_ids"]
        if not isinstance(raw, list):
            return jsonify({"error": "leader_role_ids must be a list"}), 400
        cleaned = []
        for item in raw:
            s = str(item).strip()
            if not s:
                continue
            if not s.isdigit():
                return jsonify({"error": f"Invalid role ID: {s}"}), 400
            cleaned.append(s)
        if not cleaned:
            return jsonify({"error": "At least one leader role is required"}), 400
        updates["leader_role_ids"] = cleaned  # upsert serializes lists to JSON

    # New role + member role — single role ID each, must be digits
    for key in ("new_role_id", "member_role_id"):
        if key in data:
            v = str(data[key]).strip()
            if v and not v.isdigit():
                return jsonify({"error": f"Invalid role ID for {key}: {v}"}), 400
            updates[key] = v or None

    # Sanity: new_role and member_role must differ if both set
    new_id = updates.get("new_role_id")
    mem_id = updates.get("member_role_id")
    if new_id and mem_id and new_id == mem_id:
        return jsonify({"error": "'New' role and 'Member' role must be different"}), 400

    if not updates:
        return jsonify({"status": "noop"}), 200

    upsert_guild_config(guild_id, **updates)
    return jsonify({"status": "ok"})


@admin_app.route("/api/servers/<guild_id>/members", methods=["GET"])
@require_login
def api_get_server_members(guild_id: str):
    from db.queries import get_all_players, get_player_flowers, get_player_vases
    players = get_all_players(guild_id)
    result = []
    for p in players:
        flowers = get_player_flowers(guild_id, p["discord_id"])
        vases   = get_player_vases(guild_id, p["discord_id"])
        result.append({
            "discord_id":    p["discord_id"],
            "discord_name":  p.get("discord_name", ""),
            "ign":           p["ign"],
            "registered_at": p["registered_at"][:10],
            "flower_count":  len(flowers),
            "vase_count":    len(vases),
        })
    return jsonify(result)


# ------------------------------------------------------------------
# LOGIN PAGE
# ------------------------------------------------------------------

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Dreamweaving Garden · Sign In</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;0,700;1,500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --cream:     #fdf6ee;
  --parchment: #f5ede0;
  --pink:      #f0a8c0;
  --pink-soft: #fce4ec;
  --pink-mid:  #f7ccd8;
  --lavender:  #d8bef0;
  --lav-soft:  #ede8f8;
  --mint:      #b8d9b0;
  --mint-soft: #dff0db;
  --sky:       #b8d8f0;
  --sky-soft:  #e0f0fc;
  --wood:      #c8905a;
  --text:      #4a3020;
  --text2:     #7a5c40;
  --text3:     #b09070;
  --border:    #f0d8c8;
  --white:     #fffaf5;
  --font-d:    'Playfair Display',Georgia,serif;
  --font-b:    'DM Sans',system-ui,sans-serif;
  --r:         16px;
}
body{
  font-family:var(--font-b);
  min-height:100vh;
  display:flex;align-items:center;justify-content:center;
  background:var(--cream);
  background-image:
    radial-gradient(ellipse at 15% 15%, rgba(240,168,192,.25) 0%, transparent 50%),
    radial-gradient(ellipse at 85% 85%, rgba(184,217,176,.25) 0%, transparent 50%),
    radial-gradient(ellipse at 85% 10%, rgba(216,190,240,.2)  0%, transparent 40%);
}

/* floating petals */
.petal{position:fixed;pointer-events:none;font-size:1.2rem;opacity:0;
  animation:fall linear infinite}
@keyframes fall{
  0%  {transform:translateY(-20px) rotate(0deg);  opacity:.7}
  100%{transform:translateY(110vh) rotate(360deg);opacity:0}
}

.wrap{
  width:100%;max-width:440px;padding:16px;
  display:flex;flex-direction:column;align-items:center;gap:24px;
}

/* banner image area */
.banner-art{
  width:100%;border-radius:20px;overflow:hidden;
  box-shadow:0 8px 32px rgba(180,120,100,.18);
  border:3px solid var(--pink-mid);
  aspect-ratio:3/1;
  background:linear-gradient(135deg,#fce4ec,#e8f5e9,#e3f2fd);
  display:flex;align-items:center;justify-content:center;
  font-size:2.5rem;letter-spacing:.2em;
}

.card{
  width:100%;
  background:var(--white);
  border:2px solid var(--pink-mid);
  border-radius:var(--r);
  padding:40px 36px 32px;
  box-shadow:0 4px 24px rgba(180,120,100,.12), 0 1px 4px rgba(180,120,100,.08);
  position:relative;overflow:hidden;
}
.card::before{
  content:'';position:absolute;top:0;left:0;right:0;height:4px;
  background:linear-gradient(90deg,var(--pink),var(--lavender),var(--mint),var(--sky));
  border-radius:var(--r) var(--r) 0 0;
}
.card::after{
  content:'🌸';position:absolute;top:12px;right:16px;font-size:1.4rem;opacity:.35;
}

.logo{
  font-family:var(--font-d);font-size:1.65rem;font-weight:700;
  color:var(--text);text-align:center;line-height:1.2;margin-bottom:4px;
}
.logo span{color:var(--pink);}
.tagline{
  text-align:center;font-size:.78rem;color:var(--text3);
  letter-spacing:.1em;text-transform:uppercase;margin-bottom:32px;
}

.field-wrap{margin-bottom:20px}
label{
  display:block;font-size:.72rem;font-weight:500;letter-spacing:.08em;
  text-transform:uppercase;color:var(--text2);margin-bottom:8px;
}
input[type=password]{
  width:100%;background:var(--parchment);
  border:1.5px solid var(--border);border-radius:10px;
  padding:13px 16px;font-size:.95rem;color:var(--text);
  font-family:var(--font-b);outline:none;
  transition:border-color .2s,box-shadow .2s;
}
input[type=password]:focus{
  border-color:var(--pink);
  box-shadow:0 0 0 3px rgba(240,168,192,.2);
  background:var(--white);
}

form button[type=submit]{
  width:100%;padding:13px;border:none;border-radius:10px;
  background:linear-gradient(135deg,var(--pink),#e898b8);
  color:var(--white);font-size:.95rem;font-weight:600;
  font-family:var(--font-b);cursor:pointer;
  box-shadow:0 3px 12px rgba(240,168,192,.4);
  transition:opacity .15s,transform .12s,box-shadow .15s;
}
form button[type=submit]:hover{opacity:.9;transform:translateY(-1px);box-shadow:0 5px 16px rgba(240,168,192,.5)}
form button[type=submit]:active{transform:none}

.error{
  margin-top:14px;padding:11px 14px;border-radius:9px;
  font-size:.84rem;text-align:center;
  background:#fdf0f3;color:#c05070;
  border:1.5px solid #f5c0cc;
}

.flowers-row{
  display:flex;justify-content:center;gap:8px;
  font-size:1.3rem;opacity:.5;margin-top:4px;
}
.note{text-align:center;font-size:.73rem;color:var(--text3);margin-top:20px}
</style>
</head>
<body>

<!-- floating petals -->
<div class="petal" style="left:8%;animation-duration:7s;animation-delay:0s">🌸</div>
<div class="petal" style="left:22%;animation-duration:9s;animation-delay:2s">🌼</div>
<div class="petal" style="left:55%;animation-duration:8s;animation-delay:1s">🌸</div>
<div class="petal" style="left:72%;animation-duration:11s;animation-delay:3s">🌷</div>
<div class="petal" style="left:88%;animation-duration:7.5s;animation-delay:.5s">🌸</div>

<div class="wrap">
  <div class="banner-art">
    <img src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/login-banner.png" alt="Dreamweaving Garden" style="width:100%;height:100%;object-fit:cover;display:block;"/>
  </div>

  <div class="card">
    <div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:4px">
      <img src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/icon.png" alt="icon" style="width:44px;height:44px;border-radius:50%;border:2px solid var(--pink-mid);box-shadow:0 2px 8px rgba(240,168,192,.3)"/>
      <div class="logo">Dreamweaving <span>Garden</span></div>
    </div>
    <div class="tagline">✦ Flower Manager · Admin ✦</div>

    <form method="POST" action="/login">
      <div class="field-wrap">
        <label for="password">Admin Password</label>
        <input type="password" id="password" name="password"
               placeholder="Enter your password…"
               autofocus autocomplete="current-password"/>
      </div>
      {% if error %}
      <div class="error">🌺 {{ error }}</div>
      {% endif %}
      <button type="submit">Sign In to Garden ✦</button>
    </form>

    <div class="flowers-row">🌸 🌼 🌷 🌿 🌸</div>
    <div class="note">Dreamweaving Garden • Grow together, bloom brighter</div>
  </div>
</div>
</body>
</html>"""


# ------------------------------------------------------------------
# DASHBOARD HTML — full pastel retheme
# ------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>DWG · Flower Manager</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;0,700;1,500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --cream:      #fdf6ee;
  --parchment:  #f5ede0;
  --parchment2: #ede0d0;
  --white:      #fffaf5;
  --pink:       #f0a8c0;
  --pink-soft:  #fce4ec;
  --pink-mid:   #f7ccd8;
  --pink-deep:  #e07898;
  --lav:        #d0aee8;
  --lav-soft:   #ede8f8;
  --mint:       #9ecf98;
  --mint-soft:  #dff0db;
  --sky:        #98c8e8;
  --sky-soft:   #daeef8;
  --peach:      #f7c898;
  --peach-soft: #fdeede;
  --wood:       #c8905a;
  --wood-soft:  #f0dcc8;
  --text:       #4a3020;
  --text2:      #7a5c40;
  --text3:      #b09878;
  --border:     #f0d8c8;
  --border2:    #e8c8b8;
  --shine-c:    #e8b830;
  --star-c:     #c080e0;
  --rare-c:     #60a8e0;
  --fine-c:     #68b880;
  --basic-c:    #a09878;
  --font-d:     'Playfair Display',Georgia,serif;
  --font-b:     'DM Sans',system-ui,sans-serif;
  --r:          14px;
  --r-sm:       9px;
}
html{font-size:15px}
body{
  background:var(--cream);color:var(--text);font-family:var(--font-b);min-height:100vh;
  background-image:
    radial-gradient(ellipse at 0% 0%,   rgba(240,168,192,.15) 0%,transparent 45%),
    radial-gradient(ellipse at 100% 100%,rgba(158,207,152,.15) 0%,transparent 45%),
    radial-gradient(ellipse at 100% 0%,  rgba(208,174,232,.12) 0%,transparent 40%);
}

/* ── LAYOUT ── */
.shell{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
.sidebar{
  background:var(--white);border-right:1.5px solid var(--border);
  padding:28px 20px;display:flex;flex-direction:column;gap:8px;
  position:sticky;top:0;height:100vh;overflow-y:auto;
}
.main{padding:36px 44px;overflow-y:auto}

/* ── SIDEBAR ── */
.logo{
  font-family:var(--font-d);font-size:1.25rem;font-weight:700;
  color:var(--text);line-height:1.25;margin-bottom:4px;
}
.logo .accent{color:var(--pink-deep)}
.logo-sub{font-size:.7rem;color:var(--text3);letter-spacing:.1em;
  text-transform:uppercase;margin-bottom:4px;font-family:var(--font-b)}
.logo-divider{height:1.5px;background:linear-gradient(90deg,var(--pink-mid),var(--lav-soft),var(--mint-soft));
  border-radius:2px;margin:12px 0}

.stat-card{
  background:var(--parchment);border:1.5px solid var(--border);
  border-radius:var(--r-sm);padding:12px 14px;margin-bottom:6px;
}
.stat-card .val{font-family:var(--font-d);font-size:1.7rem;font-weight:600;color:var(--pink-deep)}
.stat-card .lbl{font-size:.73rem;color:var(--text2);margin-top:1px}

.sidebar-label{font-size:.67rem;font-weight:500;letter-spacing:.11em;
  text-transform:uppercase;color:var(--text3);padding:0 4px;margin-bottom:4px;margin-top:6px}

.rarity-pills{display:flex;flex-direction:column;gap:5px;margin-bottom:8px}
.rpill{display:flex;align-items:center;padding:8px 12px;border-radius:var(--r-sm);
  font-size:.8rem;font-weight:500;cursor:pointer;border:1.5px solid transparent;
  transition:all .15s;text-align:left;background:var(--parchment);color:var(--text2)}
.rpill:hover{transform:translateX(2px);border-color:var(--border2)}
.rpill.all{background:var(--pink-soft);color:var(--pink-deep);border-color:var(--pink-mid)}
.rpill.Shine{background:#fef9e7;color:#b8860b;border-color:#f0d070}
.rpill.Star{background:#f5eeff;color:#8040c0;border-color:#d0a8f0}
.rpill.Rare{background:#eaf4fd;color:#2878b0;border-color:#90c8f0}
.rpill.Fine{background:#edfaed;color:#287828;border-color:#80c880}
.rpill.Basic{background:var(--parchment);color:var(--text2);border-color:var(--border2)}
.rpill.active{font-weight:600;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.rpill .count{font-size:.7rem;margin-left:auto;opacity:.65}

.signout{
  display:block;padding:9px 14px;border-radius:var(--r-sm);margin-top:auto;
  background:var(--pink-soft);color:var(--pink-deep);border:1.5px solid var(--pink-mid);
  font-size:.8rem;font-weight:500;text-decoration:none;text-align:center;
  transition:all .15s;
}
.signout:hover{background:var(--pink-mid);transform:translateY(-1px)}

/* ── HEADER ── */
.banner{
  width:100%;border-radius:18px;overflow:hidden;margin-bottom:28px;
  border:2px solid var(--pink-mid);
  background:linear-gradient(135deg,var(--pink-soft),var(--lav-soft),var(--mint-soft),var(--sky-soft));
  padding:22px 32px;position:relative;
}
.banner::after{content:'🌸 🌼 🌷 🌿 🌸';position:absolute;right:24px;top:50%;
  transform:translateY(-50%);font-size:1.4rem;opacity:.4;letter-spacing:.3em}
.banner-title{font-family:var(--font-d);font-size:1.7rem;font-weight:700;color:var(--text)}
.banner-sub{font-size:.83rem;color:var(--text2);margin-top:5px}

/* ── STATUS ── */
.status-bar{min-height:40px;margin-bottom:14px}
.toast{display:inline-flex;align-items:center;gap:8px;padding:10px 16px;
  border-radius:var(--r-sm);font-size:.84rem;animation:fadeIn .2s ease}
.toast.ok{background:var(--mint-soft);color:#287828;border:1.5px solid #b0d8b0}
.toast.err{background:var(--pink-soft);color:var(--pink-deep);border:1.5px solid var(--pink-mid)}
@keyframes fadeIn{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}

/* ── PANEL ── */
.panel{
  background:var(--white);border:1.5px solid var(--border);
  border-radius:var(--r);padding:26px 28px 22px;margin-bottom:28px;
  box-shadow:0 2px 12px rgba(180,120,80,.07);
}
.panel-top{height:3px;margin:-26px -28px 22px;
  background:linear-gradient(90deg,var(--pink),var(--lav),var(--mint),var(--sky));
  border-radius:var(--r) var(--r) 0 0}
.panel-title{font-family:var(--font-d);font-size:1.05rem;font-weight:600;
  color:var(--text);margin-bottom:18px}

.form-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1.5fr auto;gap:13px;align-items:end}
.field label{display:block;font-size:.7rem;font-weight:500;letter-spacing:.09em;
  text-transform:uppercase;color:var(--text2);margin-bottom:6px}
.field input,.field select{
  width:100%;background:var(--parchment);border:1.5px solid var(--border);
  border-radius:var(--r-sm);padding:10px 13px;font-size:.88rem;color:var(--text);
  font-family:var(--font-b);transition:border-color .15s,box-shadow .15s;outline:none;
}
.field input:focus,.field select:focus{
  border-color:var(--pink);background:var(--white);
  box-shadow:0 0 0 3px rgba(240,168,192,.2);
}
.field input::placeholder{color:var(--text3)}
.field select option{background:var(--white)}
.calc-row{display:flex;align-items:center;gap:10px;margin-top:12px}
.calc-label{font-size:.75rem;color:var(--text2)}
.calc-pill{background:var(--peach-soft);border:1.5px solid var(--peach);color:var(--wood);
  border-radius:999px;padding:4px 14px;font-size:.82rem;font-weight:500}

/* ── BUTTONS ── */
.btn{padding:10px 18px;border:1.5px solid transparent;border-radius:var(--r-sm);
  cursor:pointer;font-size:.83rem;font-weight:500;font-family:var(--font-b);
  transition:all .15s;white-space:nowrap}
.btn:hover{transform:translateY(-1px)}
.btn:active{transform:none}
.btn-primary{background:linear-gradient(135deg,var(--pink),#e898b8);color:var(--white);
  box-shadow:0 2px 8px rgba(240,168,192,.35);border-color:transparent}
.btn-secondary{background:var(--parchment);color:var(--text2);border-color:var(--border2)}
.btn-danger{background:var(--pink-soft);color:var(--pink-deep);border-color:var(--pink-mid)}
.btn-success{background:var(--mint-soft);color:#287828;border-color:#90c890}
.btn-sm{padding:6px 12px;font-size:.76rem}
.btn-group{display:flex;gap:8px;align-items:center}

/* ── TOOLBAR ── */
.toolbar{display:flex;align-items:center;gap:12px;margin-bottom:18px;flex-wrap:wrap}
.search-wrap{position:relative;flex:1;min-width:200px}
.search-wrap input{width:100%;padding-left:36px}
.search-icon{position:absolute;left:12px;top:50%;transform:translateY(-50%);
  color:var(--text3);pointer-events:none}
.count-badge{font-size:.77rem;color:var(--text2)}

/* ── TABLE ── */
.table-wrap{
  border:1.5px solid var(--border);border-radius:var(--r);overflow:hidden;
  box-shadow:0 2px 12px rgba(180,120,80,.06);
}
table{width:100%;border-collapse:collapse;background:var(--white)}
thead th{
  background:var(--parchment);padding:11px 16px;text-align:left;
  font-size:.7rem;font-weight:500;letter-spacing:.09em;text-transform:uppercase;
  color:var(--text2);border-bottom:1.5px solid var(--border);white-space:nowrap;
}
tbody tr{border-bottom:1px solid var(--border);transition:background .12s}
tbody tr:last-child{border-bottom:none}
tbody tr:hover{background:var(--parchment)}
tbody td{padding:12px 16px;font-size:.87rem;vertical-align:middle}

.flower-name{font-weight:500;color:var(--text)}
.rarity-badge{display:inline-block;padding:3px 11px;border-radius:999px;
  font-size:.7rem;font-weight:600;letter-spacing:.04em;border:1.5px solid transparent}
.rarity-badge.Shine{background:#fef9e7;color:#b8860b;border-color:#f0d070}
.rarity-badge.Star{background:#f5eeff;color:#8040c0;border-color:#d0a8f0}
.rarity-badge.Rare{background:#eaf4fd;color:#2878b0;border-color:#90c8f0}
.rarity-badge.Fine{background:#edfaed;color:#287828;border-color:#80c880}
.rarity-badge.Basic{background:var(--parchment);color:var(--text2);border-color:var(--border2)}

.pts-base{font-weight:500;color:var(--text)}
.pts-up{font-weight:600;color:var(--wood)}
.diamond{color:var(--sky);font-size:.85em}
.source-tag{font-size:.77rem;color:var(--text2)}
.actions{display:flex;gap:6px}

.empty-state{padding:56px 20px;text-align:center;color:var(--text3)}
.empty-state .icon{font-size:2.5rem;margin-bottom:10px;opacity:.5}
.empty-state p{font-size:.88rem}

/* ── MINI STATS (server detail) ── */
.mini-stat{background:#fff;border:1.5px solid var(--pink-mid);border-radius:10px;
  padding:12px 10px;text-align:center}
.mini-stat-val{font-family:var(--font-d);font-size:1.4rem;font-weight:700;color:var(--text);line-height:1.1}
.mini-stat-lbl{font-size:.68rem;color:var(--text2);margin-top:4px;text-transform:uppercase;letter-spacing:.04em}

/* ── INLINE EDIT ── */
.edit-row{display:none}
.edit-row.open{display:table-row}
.edit-row td{background:var(--parchment);padding:16px;border-bottom:1.5px solid var(--border)}
.edit-form{display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1.5fr auto;gap:12px;align-items:end}

/* ── DELETE MODAL ── */
.modal-overlay{position:fixed;inset:0;background:rgba(74,48,32,.35);backdrop-filter:blur(2px);
  display:flex;align-items:center;justify-content:center;z-index:100;
  opacity:0;pointer-events:none;transition:opacity .2s}
.modal-overlay.open{opacity:1;pointer-events:all}
.modal{background:var(--white);border:2px solid var(--pink-mid);border-radius:var(--r);
  padding:32px;max-width:400px;width:90%;
  transform:translateY(8px);transition:transform .2s;
  box-shadow:0 8px 32px rgba(180,120,80,.15)}
.modal-overlay.open .modal{transform:none}
.modal h3{font-family:var(--font-d);font-size:1.2rem;margin-bottom:10px;color:var(--pink-deep)}
.modal p{font-size:.88rem;color:var(--text2);margin-bottom:24px;line-height:1.6}
.modal .btn-group{justify-content:flex-end}


/* ── IMPORT PANEL ── */
.import-zone{
  border:2px dashed var(--pink-mid);border-radius:var(--r);
  padding:28px;text-align:center;background:var(--pink-soft);
  transition:all .2s;cursor:pointer;
}
.import-zone:hover,.import-zone.drag{
  border-color:var(--pink);background:var(--pink-mid);
}
.import-zone input[type=file]{display:none}
.import-zone .icon{font-size:2rem;margin-bottom:8px;display:block}
.import-zone .hint{font-size:.82rem;color:var(--text2);margin-top:6px}
.progress-wrap{display:none;margin-top:16px}
.progress-bar{height:8px;border-radius:4px;background:var(--border);overflow:hidden}
.progress-fill{height:100%;width:0;border-radius:4px;
  background:linear-gradient(90deg,var(--pink),var(--mint));transition:width .3s}
.import-results{margin-top:14px;padding:14px;border-radius:var(--r-sm);
  font-size:.84rem;display:none}
.import-results.ok{background:var(--mint-soft);color:#287828;border:1.5px solid #90c890}
.import-results.warn{background:var(--peach-soft);color:#a05020;border:1.5px solid var(--peach)}
@media(max-width:900px){
  .shell{grid-template-columns:1fr}
  .sidebar{position:static;height:auto}
  .main{padding:24px 18px}
  .form-grid,.edit-form{grid-template-columns:1fr 1fr}
  .form-grid>:last-child,.edit-form>:last-child{grid-column:1/-1}
  .banner::after{display:none}
}
</style>
</head>
<body>
<div class="shell">

  <!-- SIDEBAR -->
  <aside class="sidebar">
    <div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:4px">
      <img src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/icon.png" alt="icon" style="width:44px;height:44px;border-radius:50%;border:2px solid var(--pink-mid);box-shadow:0 2px 8px rgba(240,168,192,.3)"/>
      <div class="logo">Dreamweaving <span class="accent">Garden</span></div>
    </div>
    <div class="logo-sub">✦ Flower Manager ✦</div>
    <div class="logo-divider"></div>

    <div class="stat-card">
      <div class="val" id="sTotal">—</div>
      <div class="lbl">Flowers in master list</div>
    </div>

    <div class="logo-divider"></div>
    <div class="sidebar-label">Master Lists</div>
    <div style="display:flex;flex-direction:column;gap:5px;margin-bottom:8px">
      <button class="rpill all active" id="tab-flowers" onclick="switchTab('flowers',this)">🌸 Flowers <span class="count" id="tab-cnt-flowers"></span></button>
      <button class="rpill Basic" id="tab-vases" onclick="switchTab('vases',this)">🏺 Vases <span class="count" id="tab-cnt-vases"></span></button>
    </div>

    <div class="logo-divider"></div>
    <div class="sidebar-label">Management</div>
    <div style="display:flex;flex-direction:column;gap:5px;margin-bottom:8px">
      <button class="rpill Basic" id="tab-servers" onclick="switchTab('servers',this)">🌿 Servers</button>
    </div>

    <div class="logo-divider"></div>
    <div class="sidebar-label">Filter by Rarity</div>
    <div class="rarity-pills">
      <button class="rpill all active" onclick="setFilter('all',this)">
        🌸 All Flowers <span class="count" id="cnt-all"></span>
      </button>
      <button class="rpill Shine" onclick="setFilter('Shine',this)">
        ✦ Shine <span class="count" id="cnt-Shine"></span>
      </button>
      <button class="rpill Star" onclick="setFilter('Star',this)">
        ★ Star <span class="count" id="cnt-Star"></span>
      </button>
      <button class="rpill Rare" onclick="setFilter('Rare',this)">
        ◆ Rare <span class="count" id="cnt-Rare"></span>
      </button>
      <button class="rpill Fine" onclick="setFilter('Fine',this)">
        ◇ Fine <span class="count" id="cnt-Fine"></span>
      </button>
      <button class="rpill Basic" onclick="setFilter('Basic',this)">
        · Basic <span class="count" id="cnt-Basic"></span>
      </button>
    </div>

    <div class="logo-divider"></div>
    <a href="/logout" class="signout">🌿 Sign Out</a>
  </aside>

  <!-- MAIN -->
  <main class="main">

    <!-- BANNER -->
    <div class="banner" style="padding:0;background:none;border:2px solid var(--pink-mid);border-radius:18px;overflow:hidden;box-shadow:0 4px 20px rgba(180,120,80,.12);position:relative;">
      <img src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/banner.png" alt="Dreamweaving Garden" style="width:100%;display:block;max-height:180px;object-fit:cover;object-position:center 40%"/>
      <div style="position:absolute;bottom:0;left:0;right:0;padding:14px 24px;background:linear-gradient(transparent,rgba(253,246,238,.92));border-top:1px solid rgba(240,168,192,.2)">
        <div style="display:flex;align-items:center;gap:10px">
          <img src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/icon.png" alt="icon" style="width:36px;height:36px;border-radius:50%;border:2px solid var(--pink-mid)"/>
          <div>
            <div style="display:flex;align-items:center;gap:12px"><div style="font-family:var(--font-d);font-size:1.2rem;font-weight:700;color:var(--text)" id="bannerTitle">Flower Master List</div><button class="btn btn-secondary btn-sm" onclick="toggleImport()" id="importToggle">📥 Bulk Import</button></div>
            <div style="font-size:.78rem;color:var(--text2)" id="bannerSub">Add, edit, and manage flowers for Dreamweaving Garden league events.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- STATUS -->
    <div class="status-bar" id="statusBar"></div>

    <!-- ADD FORM -->
    <div class="panel">
      <div class="panel-top"></div>
      <div class="panel-title" id="formTitle">🌱 Add New Flower</div>
      <div class="form-grid">
        <div class="field">
          <label id="nameLbl">Flower Name</label>
          <input id="fName" placeholder="e.g. Moonbloom Rose" maxlength="100"/>
        </div>
        <div class="field">
          <label>Rarity</label>
          <select id="fRarity">
            <option value="Shine">✦ Shine</option>
            <option value="Star">★ Star</option>
            <option value="Rare">◆ Rare</option>
            <option value="Fine">◇ Fine</option>
            <option value="Basic" selected>· Basic</option>
          </select>
        </div>
        <div class="field">
          <label>Base Points</label>
          <input id="fPoints" type="number" min="0" placeholder="0" oninput="updateCalc()"/>
        </div>
        <div class="field">
          <label>Upgrade Cost 💎</label>
          <input id="fCost" type="number" min="0" placeholder="0"/>
        </div>
        <div class="field">
          <label>Source</label>
          <input id="fSource" placeholder="Garden, Shop, Event…" maxlength="100"/>
        </div>
        <div class="field">
          <label>&nbsp;</label>
          <div class="btn-group">
            <button class="btn btn-primary" onclick="submitForm()">Add ✦</button>
            <button class="btn btn-secondary" id="btnCancel" onclick="cancelEdit()" style="display:none">Cancel</button>
          </div>
        </div>
      </div>
      <div class="calc-row">
        <span class="calc-label">Upgraded points (×2 diamonds):</span>
        <span class="calc-pill" id="calcVal">—</span>
      </div>
    </div>


    <!-- IMPORT PANEL -->
    <div class="panel" id="importPanel">
      <div class="panel-top"></div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px">
        <div class="panel-title" style="margin:0">📥 Bulk Import from Excel / CSV</div>
        <button class="btn btn-secondary btn-sm" onclick="toggleImport()">Hide</button>
      </div>
      <p style="font-size:.83rem;color:var(--text2);margin-bottom:16px;line-height:1.6">
        Export your spreadsheet as <strong>CSV</strong> (File → Save As → CSV) or copy-paste directly from Excel.<br/>
        Expected columns: <code>Flower Name · Type · How to Obtain · Points · Cost to upgrade</code>
      </p>
      <div class="import-zone" id="dropZone" onclick="document.getElementById('fileInput').click()"
           ondragover="dragOver(event)" ondragleave="dragLeave()" ondrop="dropFile(event)">
        <input type="file" id="fileInput" accept=".csv,.tsv,.txt,.xlsx" onchange="handleFile(event)"/>
        <span class="icon">📂</span>
        <strong>Click to choose file</strong> or drag &amp; drop here<br/>
        <span class="hint">Supports .csv, .tsv, or paste from Excel</span>
      </div>

      <div style="margin-top:14px">
        <div style="font-size:.78rem;color:var(--text2);margin-bottom:8px">Or paste CSV / tab-separated data directly:</div>
        <textarea id="pasteArea" rows="5" placeholder="Paste rows here (tab or comma separated)..."
          style="width:100%;background:var(--parchment);border:1.5px solid var(--border);border-radius:var(--r-sm);
          padding:10px 13px;font-size:.82rem;color:var(--text);font-family:var(--font-b);resize:vertical;outline:none"></textarea>
        <div style="display:flex;gap:10px;margin-top:10px">
          <button class="btn btn-primary" onclick="importFromPaste()">Import Pasted Data</button>
          <button class="btn btn-secondary" onclick="document.getElementById('pasteArea').value=''">Clear</button>
        </div>
      </div>

      <div class="progress-wrap" id="progressWrap">
        <div style="font-size:.8rem;color:var(--text2);margin-bottom:6px" id="progressLabel">Importing...</div>
        <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
      </div>
      <div class="import-results" id="importResults"></div>
    </div>

    <!-- TOOLBAR -->
    <div class="toolbar">
      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input id="search" placeholder="Search flowers…" oninput="render()"/>
      </div>
      <div class="count-badge" id="countBadge"></div>
    </div>

    <!-- TABLE -->
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Flower</th>
            <th>Rarity</th>
            <th>Base pts</th>
            <th>Upgraded pts</th>
            <th>Upgrade cost</th>
            <th>Source</th>
            <th></th>
          </tr>
        </thead>
        <tbody id="flowerRows"></tbody>
      </table>
    </div>
  </main>
</div>

<!-- SERVERS PANEL (hidden by default, shown when servers tab active) -->
<div id="serversPanel" style="display:none">
  <div class="shell">
    <aside class="sidebar">
      <div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:4px">
        <img src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/icon.png" alt="icon" style="width:44px;height:44px;border-radius:50%;border:2px solid var(--pink-mid);box-shadow:0 2px 8px rgba(240,168,192,.3)"/>
        <div class="logo">Dreamweaving <span class="accent">Garden</span></div>
      </div>
      <div class="logo-sub">✦ Flower Manager ✦</div>
      <div class="logo-divider"></div>
      <div class="stat-card">
        <div class="val" id="sTotal2">—</div>
        <div class="lbl">Servers</div>
      </div>
      <div class="logo-divider"></div>
      <div class="sidebar-label">Master Lists</div>
      <div style="display:flex;flex-direction:column;gap:5px;margin-bottom:8px">
        <button class="rpill all" id="tab-flowers2" onclick="switchTab('flowers',document.getElementById('tab-flowers'))">🌸 Flowers</button>
        <button class="rpill Basic" id="tab-vases2" onclick="switchTab('vases',document.getElementById('tab-vases'))">🏺 Vases</button>
      </div>
      <div class="logo-divider"></div>
      <div class="sidebar-label">Management</div>
      <div style="display:flex;flex-direction:column;gap:5px;margin-bottom:8px">
        <button class="rpill all active" id="tab-servers2">🌿 Servers</button>
      </div>
      <div class="logo-divider"></div>
      <a href="/logout" class="signout">🌿 Sign Out</a>
    </aside>
    <main class="main">
      <div class="banner" style="padding:0;background:none;border:2px solid var(--pink-mid);border-radius:18px;overflow:hidden;box-shadow:0 4px 20px rgba(180,120,80,.12);position:relative;">
        <img src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/banner.png" alt="Dreamweaving Garden" style="width:100%;display:block;max-height:180px;object-fit:cover;object-position:center 40%"/>
        <div style="position:absolute;bottom:0;left:0;right:0;padding:14px 24px;background:linear-gradient(transparent,rgba(253,246,238,.92));border-top:1px solid rgba(240,168,192,.2)">
          <div style="display:flex;align-items:center;gap:10px">
            <img src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/icon.png" alt="icon" style="width:36px;height:36px;border-radius:50%;border:2px solid var(--pink-mid)"/>
            <div>
              <div id="serversBannerTitle" style="font-family:var(--font-d);font-size:1.2rem;font-weight:700;color:var(--text)">🌿 Servers</div>
              <div id="serversBannerSub" style="font-size:.78rem;color:var(--text2)">Servers using Dreamweaving Garden Bot</div>
            </div>
          </div>
        </div>
      </div>

      <div class="status-bar" id="serversStatusBar"></div>

      <!-- SERVER LIST VIEW -->
      <div id="serverListView">
        <div class="table-wrap" style="margin-top:16px">
          <table>
            <thead>
              <tr>
                <th>Server Name</th>
                <th>Guild ID</th>
                <th>Members</th>
                <th>Joined</th>
                <th></th>
              </tr>
            </thead>
            <tbody id="serverRows"></tbody>
          </table>
        </div>
      </div>

      <!-- SERVER DETAIL VIEW (shown when a server is clicked) -->
      <div id="serverDetailView" style="display:none">
        <div style="margin-top:16px;margin-bottom:12px;display:flex;align-items:center;gap:12px">
          <button class="btn btn-secondary btn-sm" onclick="showServerList()">← Back to Servers</button>
          <div>
            <div style="font-family:var(--font-d);font-size:1.1rem;font-weight:700;color:var(--text)" id="memberServerName"></div>
            <div style="font-size:.78rem;color:var(--text2)" id="memberServerSub"></div>
          </div>
        </div>

        <!-- ── CONFIGURATION (editable) ────────────────────────── -->
        <div class="card" style="margin-top:8px;padding:20px;border:2px solid var(--pink-mid);border-radius:14px;background:var(--cream)">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
            <h3 style="font-family:var(--font-d);font-size:1.05rem;color:var(--text);margin:0">⚙️ Configuration</h3>
            <span style="font-size:.72rem;color:var(--text2)">Role IDs — get these in Discord by right-clicking a role → Copy ID (Developer Mode on)</span>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
            <div>
              <label style="display:block;font-size:.78rem;font-weight:600;color:var(--text);margin-bottom:4px">'New' Role ID</label>
              <input type="text" id="cfgNewRole" placeholder="e.g. 1234567890123456789" style="width:100%;padding:8px 10px;border:1.5px solid var(--pink-mid);border-radius:8px;font-family:monospace;font-size:.85rem;background:#fff"/>
              <div style="font-size:.7rem;color:var(--text2);margin-top:3px">Role given to players before they /register</div>
            </div>
            <div>
              <label style="display:block;font-size:.78rem;font-weight:600;color:var(--text);margin-bottom:4px">'Member' Role ID</label>
              <input type="text" id="cfgMemberRole" placeholder="e.g. 1234567890123456789" style="width:100%;padding:8px 10px;border:1.5px solid var(--pink-mid);border-radius:8px;font-family:monospace;font-size:.85rem;background:#fff"/>
              <div style="font-size:.7rem;color:var(--text2);margin-top:3px">Role assigned after /register completes</div>
            </div>
          </div>

          <div style="margin-top:14px">
            <label style="display:block;font-size:.78rem;font-weight:600;color:var(--text);margin-bottom:4px">Leader Role IDs <span style="color:var(--text2);font-weight:400">(one per line, at least 1)</span></label>
            <textarea id="cfgLeaderRoles" rows="4" placeholder="1234567890123456789&#10;9876543210987654321" style="width:100%;padding:8px 10px;border:1.5px solid var(--pink-mid);border-radius:8px;font-family:monospace;font-size:.85rem;background:#fff;resize:vertical"></textarea>
            <div style="font-size:.7rem;color:var(--text2);margin-top:3px">Roles with access to /admin commands. Server administrators always pass regardless.</div>
          </div>

          <div class="btn-group" style="margin-top:16px;justify-content:flex-end">
            <button class="btn btn-secondary btn-sm" onclick="resetConfigEdits()">Reset</button>
            <button class="btn btn-primary btn-sm" onclick="saveServerConfig()">💾 Save Changes</button>
          </div>
        </div>

        <!-- ── ACTIVITY STATS (read-only) ──────────────────────── -->
        <div class="card" style="margin-top:14px;padding:18px;border:2px solid var(--pink-mid);border-radius:14px;background:var(--cream)">
          <h3 style="font-family:var(--font-d);font-size:1.05rem;color:var(--text);margin:0 0 12px 0">📊 Activity</h3>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">
            <div class="mini-stat"><div class="mini-stat-val" id="statMembers">—</div><div class="mini-stat-lbl">Members</div></div>
            <div class="mini-stat"><div class="mini-stat-val" id="statFlowers">—</div><div class="mini-stat-lbl">🌸 Flowers Tracked</div></div>
            <div class="mini-stat"><div class="mini-stat-val" id="statVases">—</div><div class="mini-stat-lbl">🏺 Vases Tracked</div></div>
            <div class="mini-stat"><div class="mini-stat-val" id="statLeague">—</div><div class="mini-stat-lbl">League Entries</div></div>
            <div class="mini-stat"><div class="mini-stat-val" id="statContribN">—</div><div class="mini-stat-lbl">Contributions</div></div>
            <div class="mini-stat"><div class="mini-stat-val" id="statContribTotal">—</div><div class="mini-stat-lbl">Total Contributed</div></div>
            <div class="mini-stat"><div class="mini-stat-val" id="statSeason">—</div><div class="mini-stat-lbl">Latest Season</div></div>
            <div class="mini-stat"><div class="mini-stat-val" id="statLatestReg">—</div><div class="mini-stat-lbl">Latest Register</div></div>
          </div>
          <div style="font-size:.7rem;color:var(--text2);margin-top:10px" id="statMetaRow"></div>
        </div>

        <!-- ── MEMBERS ─────────────────────────────────────────── -->
        <div style="margin-top:14px;display:flex;align-items:center;justify-content:space-between">
          <h3 style="font-family:var(--font-d);font-size:1.05rem;color:var(--text);margin:0">👥 Registered Members</h3>
        </div>
        <div class="table-wrap" style="margin-top:8px">
          <table>
            <thead>
              <tr>
                <th>IGN</th>
                <th>Discord Name</th>
                <th>Discord ID</th>
                <th>🌸 Flowers</th>
                <th>🏺 Vases</th>
                <th>Registered</th>
              </tr>
            </thead>
            <tbody id="memberRows"></tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
</div>

<!-- DELETE MODAL -->
<div class="modal-overlay" id="deleteModal">
  <div class="modal">
    <h3 id="deleteTitle">🌺 Remove Item?</h3>
    <p id="deleteMsg"></p>
    <div class="btn-group">
      <button class="btn btn-secondary" onclick="closeDelete()">Keep It</button>
      <button class="btn btn-danger" onclick="confirmDelete()">Remove</button>
    </div>
  </div>
</div>

<script>
const API = (path) => path;

let items        = [];
let activeTab    = 'flowers';
let activeFilter = 'all';
let deleteTarget = null;

const TAB_CFG = {
  flowers: {
    api:         '/api/flowers',
    bulkApi:     '/api/flowers/bulk',
    label:       'Flower',
    addTitle:    '🌱 Add New Flower',
    namePh:      'e.g. Moonbloom Rose',
    bannerTitle: 'Flower Master List',
    bannerSub:   'Add, edit, and manage flowers for Dreamweaving Garden league events.',
    icon:        '🌸',
    addedMsg:    (n) => '🌸 "'+n+'" added to the master list!',
    updatedMsg:  (n) => '🌿 "'+n+'" updated.',
    removedMsg:  (n) => '🌺 "'+n+'" removed from the list.',
  },
  vases: {
    api:         '/api/vases',
    bulkApi:     '/api/vases/bulk',
    label:       'Vase',
    addTitle:    '🏺 Add New Vase',
    namePh:      'e.g. Crystal Bloom Vase',
    bannerTitle: 'Vase Master List',
    bannerSub:   'Add, edit, and manage vases for Dreamweaving Garden.',
    icon:        '🏺',
    addedMsg:    (n) => '🏺 "'+n+'" added to the master list!',
    updatedMsg:  (n) => '🏺 "'+n+'" updated.',
    removedMsg:  (n) => '🏺 "'+n+'" removed from the list.',
  },
};

function cfg(){ return TAB_CFG[activeTab]; }

function esc(s){ return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])) }
function toast(msg,type='ok'){
  const b=document.getElementById('statusBar');
  b.innerHTML='<div class="toast '+type+'">'+esc(msg)+'</div>';
  setTimeout(()=>{b.innerHTML=''},4500);
}
function updateCalc(){
  const v=parseInt(document.getElementById('fPoints').value)||0;
  document.getElementById('calcVal').textContent=v?(v*2)+' pts':'—';
}
function rarityOrder(r){return({'Shine':0,'Star':1,'Rare':2,'Fine':3,'Basic':4}[r]??9)}

function switchTab(tab, el){
  // servers tab shows a completely different panel
  if(tab === 'servers'){
    document.querySelector('.shell').style.display = 'none';
    document.getElementById('serversPanel').style.display = '';
    document.querySelectorAll('#tab-flowers,#tab-vases,#tab-servers').forEach(b=>{
      b.classList.remove('active','all');
    });
    el.classList.add('active','all');
    loadServers();
    return;
  }
  // switching back to master list tabs
  document.querySelector('.shell').style.display = '';
  document.getElementById('serversPanel').style.display = 'none';
  activeTab    = tab;
  activeFilter = 'all';
  document.querySelectorAll('#tab-flowers,#tab-vases,#tab-servers').forEach(b=>b.classList.remove('active','all'));
  el.classList.add('active','all');
  document.getElementById('bannerTitle').textContent = cfg().bannerTitle;
  document.getElementById('bannerSub').textContent   = cfg().bannerSub;
  document.getElementById('nameLbl').textContent      = cfg().label+' Name';
  document.getElementById('fName').placeholder        = cfg().namePh;
  resetForm();
  document.querySelectorAll('.rpill').forEach(p=>p.classList.remove('active'));
  document.querySelector('.rpill.all').classList.add('active');
  load();
}

// ── SERVERS ──────────────────────────────────────────────────────

async function loadServers(){
  try{
    const r = await fetch('/api/servers');
    if(!r.ok) throw new Error('Failed to load servers');
    const servers = await r.json();
    document.getElementById('sTotal2').textContent = servers.length;
    renderServerList(servers);
  }catch(e){
    document.getElementById('serversStatusBar').innerHTML =
      '<div class="toast err">'+e.message+'</div>';
  }
}

function renderServerList(servers){
  showServerList();
  const tbody = document.getElementById('serverRows');
  if(!servers.length){
    tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="icon">🌿</div><p>No servers have run /setup yet.</p></div></td></tr>';
    return;
  }
  tbody.innerHTML = servers.map(function(s){
    var name = s.guild_name || ('Server '+s.guild_id);
    var joined = s.created_at ? s.created_at.slice(0,10) : '—';
    return '<tr>'
      +'<td><strong>'+esc(name)+'</strong></td>'
      +'<td style="font-size:.78rem;color:var(--text2);font-family:monospace">'+esc(s.guild_id)+'</td>'
      +'<td><span class="pts-base">'+s.member_count+'</span></td>'
      +'<td style="font-size:.82rem;color:var(--text2)">'+joined+'</td>'
      +'<td><button class="btn btn-secondary btn-sm" onclick="loadServerDetail(\''+esc(s.guild_id)+'\',\''+esc(name)+'\')">View</button></td>'
      +'</tr>';
  }).join('');
}

// Holds the currently-viewed server's data so Reset can restore form fields
let currentServer = null;

async function loadServerDetail(guildId, guildName){
  document.getElementById('memberServerName').textContent = guildName;
  document.getElementById('memberServerSub').textContent  = 'Loading…';
  document.getElementById('serversBannerTitle').textContent = '🌿 '+guildName;
  document.getElementById('serversBannerSub').textContent   = 'Loading…';
  document.getElementById('serverListView').style.display   = 'none';
  document.getElementById('serverDetailView').style.display = '';

  // Clear stats + members while loading
  ['statMembers','statFlowers','statVases','statLeague','statContribN','statContribTotal','statSeason','statLatestReg']
    .forEach(id => { document.getElementById(id).textContent = '—'; });
  document.getElementById('statMetaRow').textContent = '';
  document.getElementById('memberRows').innerHTML =
    '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text2)">Loading…</td></tr>';

  try{
    const [dRes, mRes] = await Promise.all([
      fetch('/api/servers/'+encodeURIComponent(guildId)),
      fetch('/api/servers/'+encodeURIComponent(guildId)+'/members'),
    ]);
    if(!dRes.ok) throw new Error('Failed to load server config');
    if(!mRes.ok) throw new Error('Failed to load members');
    const detail  = await dRes.json();
    const members = await mRes.json();

    currentServer = { guild_id: guildId, name: guildName, snapshot: detail };

    // Header
    const cnt = detail.stats.member_count;
    document.getElementById('memberServerSub').textContent  = cnt+' registered member'+(cnt!==1?'s':'');
    document.getElementById('serversBannerSub').textContent = cnt+' registered member'+(cnt!==1?'s':'');

    // Config fields
    fillConfigFields(detail);

    // Stats
    document.getElementById('statMembers').textContent      = detail.stats.member_count;
    document.getElementById('statFlowers').textContent      = detail.stats.flowers_tracked;
    document.getElementById('statVases').textContent        = detail.stats.vases_tracked;
    document.getElementById('statLeague').textContent       = detail.stats.league_entries;
    document.getElementById('statContribN').textContent     = detail.stats.contributions_logged;
    document.getElementById('statContribTotal').textContent = (detail.stats.contributions_total||0).toLocaleString();
    document.getElementById('statSeason').textContent       = detail.stats.latest_season || '—';
    document.getElementById('statLatestReg').textContent    = detail.stats.latest_registration || '—';

    const meta = [];
    if(detail.created_at) meta.push('Configured: '+detail.created_at.slice(0,10));
    if(detail.updated_at) meta.push('Last update: '+detail.updated_at.slice(0,10));
    meta.push('Guild ID: '+detail.guild_id);
    document.getElementById('statMetaRow').textContent = meta.join('  ·  ');

    // Members table
    const tbody = document.getElementById('memberRows');
    if(!members.length){
      tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="icon">🌱</div><p>No members registered yet.</p></div></td></tr>';
    } else {
      tbody.innerHTML = members.map(function(m){
        return '<tr>'
          +'<td><strong>'+esc(m.ign)+'</strong></td>'
          +'<td style="color:var(--text2)">'+esc(m.discord_name||'—')+'</td>'
          +'<td style="font-size:.78rem;color:var(--text2);font-family:monospace">'+esc(m.discord_id)+'</td>'
          +'<td><span class="pts-base">'+m.flower_count+'</span></td>'
          +'<td><span class="pts-base">'+(m.vase_count||0)+'</span></td>'
          +'<td style="font-size:.82rem;color:var(--text2)">'+esc(m.registered_at)+'</td>'
          +'</tr>';
      }).join('');
    }
  }catch(e){
    document.getElementById('serversStatusBar').innerHTML =
      '<div class="toast err">'+esc(e.message)+'</div>';
  }
}

function fillConfigFields(detail){
  document.getElementById('cfgNewRole').value     = detail.new_role_id    || '';
  document.getElementById('cfgMemberRole').value  = detail.member_role_id || '';
  document.getElementById('cfgLeaderRoles').value = (detail.leader_role_ids||[]).join('\n');
}

function resetConfigEdits(){
  if(!currentServer) return;
  fillConfigFields(currentServer.snapshot);
  document.getElementById('serversStatusBar').innerHTML =
    '<div class="toast ok">Reverted to last saved values.</div>';
  setTimeout(()=>{document.getElementById('serversStatusBar').innerHTML=''}, 3000);
}

async function saveServerConfig(){
  if(!currentServer) return;
  const newRole = document.getElementById('cfgNewRole').value.trim();
  const memRole = document.getElementById('cfgMemberRole').value.trim();
  const leaderRaw = document.getElementById('cfgLeaderRoles').value;
  const leaderRoles = leaderRaw.split(/[\s,]+/).map(s=>s.trim()).filter(Boolean);

  // Client-side validation
  if(!leaderRoles.length){
    showServersToast('At least one leader role is required.','err');
    return;
  }
  const bad = [newRole, memRole, ...leaderRoles].filter(v => v && !/^\d+$/.test(v));
  if(bad.length){
    showServersToast('Invalid role ID(s): '+bad.join(', '),'err');
    return;
  }
  if(newRole && memRole && newRole === memRole){
    showServersToast("'New' role and 'Member' role must be different.",'err');
    return;
  }

  try{
    const r = await fetch('/api/servers/'+encodeURIComponent(currentServer.guild_id)+'/config', {
      method: 'PUT',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        leader_role_ids: leaderRoles,
        new_role_id:     newRole,
        member_role_id:  memRole,
      }),
    });
    const data = await r.json();
    if(!r.ok) throw new Error(data.error || 'Save failed');
    // Refresh snapshot so Reset knows the new baseline
    currentServer.snapshot.leader_role_ids = leaderRoles;
    currentServer.snapshot.new_role_id     = newRole;
    currentServer.snapshot.member_role_id  = memRole;
    showServersToast('✓ Configuration saved.','ok');
  }catch(e){
    showServersToast('Save failed: '+e.message,'err');
  }
}

function showServersToast(msg, type){
  const b = document.getElementById('serversStatusBar');
  b.innerHTML = '<div class="toast '+type+'">'+esc(msg)+'</div>';
  setTimeout(()=>{b.innerHTML=''}, 4500);
}

function showServerList(){
  document.getElementById('serverListView').style.display   = '';
  document.getElementById('serverDetailView').style.display = 'none';
  document.getElementById('serversBannerTitle').textContent = '🌿 Servers';
  document.getElementById('serversBannerSub').textContent   = 'Servers using Dreamweaving Garden Bot';
  currentServer = null;
}

function setFilter(f,el){
  activeFilter=f;
  document.querySelectorAll('.rpill').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  render();
}

async function load(){
  try{
    const r=await fetch(API(cfg().api));
    if(!r.ok) throw new Error('Session expired — please refresh.');
    items=await r.json();
    updateSidebar();
    render();
  }catch(e){toast(e.message,'err')}
}

function updateSidebar(){
  const counts={};
  items.forEach(f=>{counts[f.rarity]=(counts[f.rarity]||0)+1});
  document.getElementById('sTotal').textContent=items.length;
  document.getElementById('cnt-all').textContent=items.length;
  document.getElementById('tab-cnt-flowers').textContent='';
  document.getElementById('tab-cnt-vases').textContent='';
  document.getElementById('tab-cnt-'+activeTab).textContent=items.length;
  ['Shine','Star','Rare','Fine','Basic'].forEach(r=>{
    const el=document.getElementById('cnt-'+r);
    if(el) el.textContent=counts[r]||0;
  });
}

function render(){
  const q=document.getElementById('search').value.trim().toLowerCase();
  let rows=items.filter(f=>{
    const mf=activeFilter==='all'||f.rarity===activeFilter;
    const ms=!q||f.name.toLowerCase().includes(q)||f.source.toLowerCase().includes(q);
    return mf&&ms;
  });
  rows.sort((a,b)=>rarityOrder(a.rarity)-rarityOrder(b.rarity)||a.name.localeCompare(b.name));
  document.getElementById('countBadge').textContent=rows.length+' '+cfg().label.toLowerCase()+(rows.length!==1?'s':'');
  const tbody=document.getElementById('flowerRows');

  if(!rows.length){
    tbody.innerHTML='<tr><td colspan="7"><div class="empty-state">'
      +'<div class="icon">'+cfg().icon+'</div>'
      +'<p>'+(q||activeFilter!=='all'?'No '+cfg().label.toLowerCase()+'s match your search.':'No '+cfg().label.toLowerCase()+'s yet — add your first one above!')+'</p>'
      +'</div></td></tr>';
    return;
  }

  tbody.innerHTML=rows.map(function(f, idx){
    var i='row'+idx;
    var opts=['Shine','Star','Rare','Fine','Basic'].map(function(r){
      return '<option'+(r===f.rarity?' selected':'')+'>'+r+'</option>';
    }).join('');
    return '<tr id="main-'+i+'">'
      +'<td><span class="flower-name">'+esc(f.name)+'</span></td>'
      +'<td><span class="rarity-badge '+esc(f.rarity)+'">'+esc(f.rarity)+'</span></td>'
      +'<td><span class="pts-base">'+f.base_points+'</span></td>'
      +'<td><span class="pts-up">'+(f.base_points*2)+'</span></td>'
      +'<td><span class="diamond">💎</span> '+f.upgrade_cost.toLocaleString()+'</td>'
      +'<td><span class="source-tag">'+esc(f.source)+'</span></td>'
      +'<td><div class="actions">'
        +'<button class="btn btn-success btn-sm" onclick="startEdit(\''+i+'\')">Edit</button>'
        +'<button class="btn btn-danger btn-sm" onclick="startDelete(this)">Remove</button>'
      +'</div></td>'
    +'</tr>'
    +'<tr class="edit-row" id="edit-'+i+'" data-item-name="'+esc(f.name)+'">'
      +'<td colspan="7"><div class="edit-form">'
        +'<div class="field"><label>Name (locked)</label>'
          +'<input value="'+esc(f.name)+'" disabled style="opacity:.55"/></div>'
        +'<div class="field"><label>Rarity</label>'
          +'<select id="er-'+i+'-rarity">'+opts+'</select></div>'
        +'<div class="field"><label>Base Points</label>'
          +'<input id="er-'+i+'-pts" type="number" min="0" value="'+f.base_points+'"'
          +' oninput="updateEditCalc(\''+i+'\')"/></div>'
        +'<div class="field"><label>Upgrade Cost 💎</label>'
          +'<input id="er-'+i+'-cost" type="number" min="0" value="'+f.upgrade_cost+'"/></div>'
        +'<div class="field"><label>Source</label>'
          +'<input id="er-'+i+'-source" value="'+esc(f.source)+'" maxlength="100"/></div>'
        +'<div class="field"><label>&nbsp;</label><div class="btn-group">'
          +'<button class="btn btn-primary btn-sm" onclick="saveEdit(\''+i+'\')">Save</button>'
          +'<button class="btn btn-secondary btn-sm" onclick="closeEdit(\''+i+'\')">Cancel</button>'
        +'</div></div>'
      +'</div>'
      +'<div style="margin-top:10px;font-size:.77rem;color:var(--text2)">'
        +'Upgraded: <span id="er-'+i+'-calc" style="color:var(--wood);font-weight:600">'+(f.base_points*2)+' pts</span>'
      +'</div></td>'
    +'</tr>';
  }).join('');
}

function updateEditCalc(id){
  const pts=parseInt(document.getElementById('er-'+id+'-pts').value)||0;
  document.getElementById('er-'+id+'-calc').textContent=(pts*2)+' pts';
}

async function submitForm(){
  const name   =document.getElementById('fName').value.trim();
  const rarity =document.getElementById('fRarity').value;
  const pts    =parseInt(document.getElementById('fPoints').value)||0;
  const cost   =parseInt(document.getElementById('fCost').value)||0;
  const source =document.getElementById('fSource').value.trim()||'Unknown';
  if(!name){toast(cfg().label+' name is required.','err');return}
  const r=await fetch(API(cfg().api),{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,rarity,base_points:pts,upgrade_cost:cost,source})
  });
  const d=await r.json();
  if(!r.ok){toast(d.error||'Error adding '+cfg().label.toLowerCase()+'.','err');return}
  toast(cfg().addedMsg(name));
  resetForm();await load();
}

function resetForm(){
  ['fName','fPoints','fCost','fSource'].forEach(id=>{document.getElementById(id).value=''});
  document.getElementById('fRarity').value='Basic';
  document.getElementById('calcVal').textContent='—';
  document.getElementById('formTitle').textContent=cfg().addTitle;
  document.getElementById('btnCancel').style.display='none';
}
function cancelEdit(){resetForm()}

function startEdit(id){
  document.querySelectorAll('.edit-row.open').forEach(r=>r.classList.remove('open'));
  const row=document.getElementById('edit-'+id);
  if(row) row.classList.add('open');
}
function closeEdit(id){
  const row=document.getElementById('edit-'+id);
  if(row) row.classList.remove('open');
}
async function saveEdit(id){
  const row=document.getElementById('edit-'+id);
  const name=row ? row.getAttribute('data-item-name') : '';
  if(!name){toast('Could not find item name.','err');return;}
  const rarity=document.getElementById('er-'+id+'-rarity').value;
  const pts=parseInt(document.getElementById('er-'+id+'-pts').value)||0;
  const cost=parseInt(document.getElementById('er-'+id+'-cost').value)||0;
  const source=document.getElementById('er-'+id+'-source').value.trim()||'Unknown';
  const r=await fetch(API(cfg().api+'/'+encodeURIComponent(name)),{
    method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({rarity,base_points:pts,upgrade_cost:cost,source})
  });
  const d=await r.json();
  if(!r.ok){toast(d.error||'Error saving.','err');return}
  toast(cfg().updatedMsg(name));await load();
}

function startDelete(btn){
  const mainRow = btn.closest ? btn.closest('tr') : null;
  const editRow = mainRow ? mainRow.nextElementSibling : null;
  const name = editRow ? editRow.getAttribute('data-item-name') : null;
  if(!name){toast('Could not identify item to delete.','err');return;}
  deleteTarget=name;
  const label=cfg().label;
  const icon=activeTab==='flowers'?'🌺':'🏺';
  document.getElementById('deleteTitle').textContent=icon+' Remove '+label+'?';
  document.getElementById('deleteMsg').textContent=
    'Remove "'+name+'" from the '+label.toLowerCase()+' master list? Players who have it tracked will keep their record.';
  document.getElementById('deleteModal').classList.add('open');
}
function closeDelete(){
  deleteTarget=null;
  document.getElementById('deleteModal').classList.remove('open');
}
async function confirmDelete(){
  if(!deleteTarget) return;
  const name=deleteTarget;closeDelete();
  const r=await fetch(API(cfg().api+'/'+encodeURIComponent(name)),{method:'DELETE'});
  const d=await r.json();
  if(!r.ok){toast(d.error||'Error removing.','err');return}
  toast(cfg().removedMsg(name));await load();
}

document.getElementById('deleteModal').addEventListener('click',e=>{
  if(e.target===e.currentTarget) closeDelete();
});

// ── BULK IMPORT ──
let importVisible = false;
document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('importPanel').style.display = 'none';
});
function toggleImport(){
  const panel = document.getElementById('importPanel');
  importVisible = !importVisible;
  panel.style.display = importVisible ? '' : 'none';
  document.getElementById('importToggle').textContent = importVisible ? '🌿 Hide Import' : '📥 Bulk Import';
}

function dragOver(e){ e.preventDefault(); document.getElementById('dropZone').classList.add('drag'); }
function dragLeave(){ document.getElementById('dropZone').classList.remove('drag'); }
function dropFile(e){
  e.preventDefault(); dragLeave();
  const file = e.dataTransfer.files[0];
  if(file) processFile(file);
}
function handleFile(e){ if(e.target.files[0]) processFile(e.target.files[0]); }

function processFile(file){
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById('pasteArea').value = e.target.result;
    importFromPaste();
  };
  reader.readAsText(file);
}

function parseRows(raw){
  const lines = raw.trim().split(/\r?\n/);
  if(!lines.length) return [];
  const first = lines[0];
  const delim = first.includes('\t') ? '\t' : ',';
  const firstLower = first.toLowerCase();
  const hasHeader = firstLower.includes('flower') || firstLower.includes('name') || firstLower.includes('type');
  const dataLines = hasHeader ? lines.slice(1) : lines;

  return dataLines.map(line => {
    let cols;
    if(delim === ','){
      cols = []; let cur = '', inQ = false;
      for(let i=0;i<line.length;i++){
        const c=line[i];
        if(c==='"'){inQ=!inQ;}
        else if(c===','&&!inQ){cols.push(cur.trim());cur='';}
        else{cur+=c;}
      }
      cols.push(cur.trim());
    } else {
      cols = line.split('\t').map(c=>c.trim());
    }
    return {
      name:         cols[0]||'',
      rarity:       cols[1]||'',
      source:       cols[2]||'Unknown',
      points:       cols[3]||'0',
      upgrade_cost: cols[4]||'0',
    };
  }).filter(r=>r.name.length>0);
}

async function importFromPaste(){
  const raw = document.getElementById('pasteArea').value.trim();
  if(!raw){ toast('Nothing to import — paste some data first.','err'); return; }
  const rows = parseRows(raw);
  if(!rows.length){ toast('Could not parse any rows. Check your data format.','err'); return; }

  const wrap=document.getElementById('progressWrap');
  const fill=document.getElementById('progressFill');
  const label=document.getElementById('progressLabel');
  const res=document.getElementById('importResults');
  wrap.style.display='block'; res.style.display='none';
  fill.style.width='10%';
  label.textContent='Importing '+rows.length+' flowers...';

  const r = await fetch(API(cfg().bulkApi),{
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({rows: rows})
  });
  fill.style.width='100%';
  const d = await r.json();
  setTimeout(()=>{wrap.style.display='none';fill.style.width='0';},800);

  const hasErrors = d.errors && d.errors.length>0;
  res.className='import-results '+(hasErrors?'warn':'ok');
  res.style.display='block';

  let html=(hasErrors?'<strong>&#9888;&#65039; Import Complete</strong>':'<strong>&#127800; Import Complete</strong>')+'<br/>';
  html+='&#9989; '+d.imported+' flower'+(d.imported!==1?'s':'')+' imported';
  if(d.skipped) html+=' &nbsp;&#183;&nbsp; &#9193;&#65039; '+d.skipped+' skipped';
  if(hasErrors){
    html+='<br/><br/><strong>Issues:</strong><ul style="margin:6px 0 0 16px">';
    d.errors.slice(0,10).forEach(e=>{html+='<li>'+esc(e)+'</li>';});
    if(d.errors.length>10) html+='<li>...and '+(d.errors.length-10)+' more</li>';
    html+='</ul>';
  }
  res.innerHTML=html;
  await load();
  toast(hasErrors?'Imported '+d.imported+' with '+d.errors.length+' issue(s).':'Imported '+d.imported+' flowers successfully!');
}

load();
</script>
</body>
</html>"""


# ------------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------------

@admin_app.route("/")
@require_login
def dashboard_root():
    return DASHBOARD_HTML


@admin_app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        if hmac.compare_digest(pw, ADMIN_SECRET):
            session["logged_in"] = True
            return redirect(url_for("dashboard_root"))
        error = "Incorrect password. Please try again."
    return render_template_string(LOGIN_HTML, error=error)


@admin_app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------
# THREAD LAUNCHER
# ------------------------------------------------------------------

def start_admin_dashboard() -> None:
    port = int(os.getenv("PORT", os.getenv("ADMIN_PORT", 5000)))
    def run():
        log.info("Admin dashboard starting on port %d", port)
        admin_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    t = threading.Thread(target=run, daemon=True, name="admin-dashboard")
    t.start()
    log.info("Admin dashboard thread started.")
