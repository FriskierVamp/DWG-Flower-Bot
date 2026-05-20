"""
admin/dashboard.py
Dreamweaving Garden Bot — Flask admin dashboard
Flower master list management with DWG-specific fields.
Runs in a daemon thread alongside the Discord bot.
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
    get_all_flowers, upsert_flower, delete_flower,
    normalize_rarity, VALID_RARITIES, RARITY_ORDER,
)

log          = logging.getLogger("dwg.admin")
admin_app    = Flask(__name__)
admin_app.secret_key = os.getenv("FLASK_SECRET", secrets.token_hex(32))
ADMIN_SECRET = os.getenv("ADMIN_PASSWORD", "changeme")
ADMIN_PORT   = int(os.getenv("ADMIN_PORT", 5000))


# ------------------------------------------------------------------
# AUTH — session based login
# ------------------------------------------------------------------

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            # API calls return JSON 401; page calls redirect to login
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
    # Sort by rarity order then name
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
    log.info("Flower upserted: %s (%s, %d pts, %d💎)", name, rarity, base_points, upgrade_cost)
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
        return jsonify({"error": f"Invalid rarity."}), 400
    try:
        base_points  = int(base_points)
        upgrade_cost = int(upgrade_cost)
    except (TypeError, ValueError):
        return jsonify({"error": "base_points and upgrade_cost must be integers."}), 400

    upsert_flower(name, rarity, base_points, upgrade_cost, source)
    log.info("Flower updated: %s", name)
    return jsonify({"status": "ok", "name": name})


@admin_app.route("/api/flowers/<path:name>", methods=["DELETE"])
@require_login
def api_delete_flower(name: str):
    from db.queries import delete_flower as df
    deleted = df(name)
    if not deleted:
        return jsonify({"error": f'Flower "{name}" not found.'}), 404
    log.info("Flower deleted: %s", name)
    return jsonify({"status": "ok", "name": name})


@admin_app.route("/api/rarities", methods=["GET"])
@require_login
def api_rarities():
    rarities = sorted(VALID_RARITIES, key=lambda r: RARITY_ORDER.get(r, 99))
    return jsonify(rarities)


# ------------------------------------------------------------------
# DASHBOARD HTML
# ------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>DWG · Flower Manager</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0e0b14;
  --surface:#18132a;
  --surface2:#211a38;
  --border:#2e2450;
  --accent:#c9a0ff;
  --accent2:#b8f2d0;
  --accent3:#ffb3c1;
  --gold:#f4d58d;
  --text:#e8e0f5;
  --text2:#9f93c0;
  --text3:#5e5480;
  --shine:#fff8e7;
  --star:#c9a0ff;
  --rare:#7dd4fc;
  --fine:#b8f2d0;
  --basic:#9f93c0;
  --danger:#ff6b8a;
  --success:#6ee7b7;
  --font-display:'Playfair Display',Georgia,serif;
  --font-body:'DM Sans',system-ui,sans-serif;
  --radius:12px;
  --radius-sm:8px;
}
html{font-size:15px}
body{background:var(--bg);color:var(--text);font-family:var(--font-body);min-height:100vh;
  background-image:radial-gradient(ellipse at 20% 0%,rgba(100,60,180,.18) 0%,transparent 60%),
                   radial-gradient(ellipse at 80% 100%,rgba(184,242,208,.08) 0%,transparent 50%);
}

/* ── LAYOUT ── */
.shell{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
.sidebar{background:var(--surface);border-right:1px solid var(--border);
  padding:32px 24px;display:flex;flex-direction:column;gap:8px;position:sticky;top:0;height:100vh}
.main{padding:40px 48px;overflow-y:auto}

/* ── SIDEBAR ── */
.logo{font-family:var(--font-display);font-size:1.35rem;font-weight:700;
  color:var(--accent);letter-spacing:.02em;margin-bottom:8px;line-height:1.2}
.logo span{display:block;font-size:.75rem;font-weight:400;color:var(--text3);
  font-family:var(--font-body);letter-spacing:.08em;text-transform:uppercase;margin-top:4px}
.sidebar-divider{height:1px;background:var(--border);margin:16px 0}
.sidebar-label{font-size:.68rem;font-weight:500;letter-spacing:.12em;
  text-transform:uppercase;color:var(--text3);padding:0 4px;margin-bottom:4px}
.stat-card{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:12px 14px;margin-bottom:8px}
.stat-card .val{font-family:var(--font-display);font-size:1.6rem;font-weight:600;color:var(--accent)}
.stat-card .lbl{font-size:.75rem;color:var(--text2);margin-top:2px}
.rarity-pills{display:flex;flex-direction:column;gap:6px;margin-top:4px}
.rpill{display:flex;align-items:center;justify-content:space-between;padding:7px 12px;
  border-radius:6px;font-size:.8rem;font-weight:500;cursor:pointer;border:none;
  transition:opacity .15s,transform .1s;text-align:left}
.rpill:hover{opacity:.85;transform:translateX(2px)}
.rpill.all{background:var(--surface2);color:var(--text);border:1px solid var(--border)}
.rpill.shine{background:rgba(255,248,231,.12);color:var(--shine);border:1px solid rgba(255,248,231,.2)}
.rpill.star{background:rgba(201,160,255,.12);color:var(--star);border:1px solid rgba(201,160,255,.2)}
.rpill.rare{background:rgba(125,212,252,.12);color:var(--rare);border:1px solid rgba(125,212,252,.2)}
.rpill.fine{background:rgba(184,242,208,.12);color:var(--fine);border:1px solid rgba(184,242,208,.2)}
.rpill.basic{background:rgba(159,147,192,.12);color:var(--basic);border:1px solid rgba(159,147,192,.2)}
.rpill .count{font-size:.72rem;opacity:.7;margin-left:auto;padding-left:8px}
.rpill.active{outline:2px solid currentColor;outline-offset:-2px}

/* ── HEADER ── */
.page-header{display:flex;align-items:flex-start;justify-content:space-between;
  margin-bottom:36px;gap:24px;flex-wrap:wrap}
.page-title{font-family:var(--font-display);font-size:2rem;font-weight:700;
  color:var(--text);line-height:1.15}
.page-title small{display:block;font-size:.85rem;font-family:var(--font-body);
  font-weight:400;color:var(--text2);margin-top:6px;letter-spacing:.01em}

/* ── FORM PANEL ── */
.panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  padding:28px 28px 24px;margin-bottom:32px;position:relative;overflow:hidden}
.panel::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--accent),var(--accent2),var(--gold))}
.panel-title{font-family:var(--font-display);font-size:1.1rem;font-weight:600;
  margin-bottom:20px;color:var(--accent)}
.form-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1.5fr auto;
  gap:14px;align-items:end}
.field label{display:block;font-size:.72rem;font-weight:500;letter-spacing:.09em;
  text-transform:uppercase;color:var(--text2);margin-bottom:7px}
.field input,.field select{width:100%;background:var(--surface2);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:10px 13px;font-size:.9rem;color:var(--text);
  font-family:var(--font-body);transition:border-color .15s,box-shadow .15s;outline:none}
.field input:focus,.field select:focus{border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(201,160,255,.15)}
.field input::placeholder{color:var(--text3)}
.field select option{background:var(--surface2)}
.calc-display{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:10px 13px;font-size:.9rem;color:var(--text3);min-height:42px;
  display:flex;align-items:center;gap:6px}
.calc-display .val{color:var(--gold);font-weight:500}

/* ── BUTTONS ── */
.btn{padding:10px 18px;border:none;border-radius:var(--radius-sm);cursor:pointer;
  font-size:.85rem;font-weight:500;font-family:var(--font-body);
  transition:opacity .15s,transform .1s;white-space:nowrap}
.btn:hover{opacity:.88;transform:translateY(-1px)}
.btn:active{transform:translateY(0)}
.btn-primary{background:var(--accent);color:#0e0b14}
.btn-secondary{background:var(--surface2);color:var(--text);border:1px solid var(--border)}
.btn-danger{background:rgba(255,107,138,.15);color:var(--danger);border:1px solid rgba(255,107,138,.3)}
.btn-success{background:rgba(110,231,183,.15);color:var(--success);border:1px solid rgba(110,231,183,.3)}
.btn-sm{padding:6px 12px;font-size:.78rem}
.btn-group{display:flex;gap:8px;align-items:center;padding-bottom:1px}

/* ── STATUS BAR ── */
.status-bar{min-height:40px;margin-bottom:16px}
.toast{display:inline-flex;align-items:center;gap:8px;padding:10px 16px;
  border-radius:var(--radius-sm);font-size:.85rem;animation:fadeIn .2s ease}
.toast.ok{background:rgba(110,231,183,.12);color:var(--success);border:1px solid rgba(110,231,183,.25)}
.toast.err{background:rgba(255,107,138,.12);color:var(--danger);border:1px solid rgba(255,107,138,.25)}
@keyframes fadeIn{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}

/* ── TOOLBAR ── */
.toolbar{display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.search-wrap{position:relative;flex:1;min-width:200px}
.search-wrap input{width:100%;padding-left:36px}
.search-icon{position:absolute;left:12px;top:50%;transform:translateY(-50%);
  color:var(--text3);font-size:1rem;pointer-events:none}
.count-badge{font-size:.78rem;color:var(--text2);white-space:nowrap}

/* ── TABLE ── */
.table-wrap{border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
table{width:100%;border-collapse:collapse}
thead th{background:var(--surface2);padding:12px 16px;text-align:left;
  font-size:.72rem;font-weight:500;letter-spacing:.09em;text-transform:uppercase;
  color:var(--text2);border-bottom:1px solid var(--border);white-space:nowrap}
tbody tr{border-bottom:1px solid var(--border);transition:background .12s}
tbody tr:last-child{border-bottom:none}
tbody tr:hover{background:var(--surface2)}
tbody td{padding:13px 16px;font-size:.88rem;vertical-align:middle}
.flower-name{font-weight:500;color:var(--text)}
.rarity-badge{display:inline-block;padding:3px 10px;border-radius:999px;
  font-size:.72rem;font-weight:500;letter-spacing:.04em;white-space:nowrap}
.rarity-badge.Shine{background:rgba(255,248,231,.15);color:var(--shine);border:1px solid rgba(255,248,231,.3)}
.rarity-badge.Star{background:rgba(201,160,255,.15);color:var(--star);border:1px solid rgba(201,160,255,.3)}
.rarity-badge.Rare{background:rgba(125,212,252,.15);color:var(--rare);border:1px solid rgba(125,212,252,.3)}
.rarity-badge.Fine{background:rgba(184,242,208,.15);color:var(--fine);border:1px solid rgba(184,242,208,.3)}
.rarity-badge.Basic{background:rgba(159,147,192,.15);color:var(--basic);border:1px solid rgba(159,147,192,.3)}
.pts{font-weight:500}
.pts.base{color:var(--text)}
.pts.upgraded{color:var(--gold)}
.diamond{color:#7dd4fc;font-size:.85em}
.source-tag{font-size:.78rem;color:var(--text2)}
.actions{display:flex;gap:6px}
.empty-state{padding:60px 20px;text-align:center;color:var(--text3)}
.empty-state .icon{font-size:2.5rem;margin-bottom:12px;opacity:.4}
.empty-state p{font-size:.9rem}

/* ── EDIT ROW ── */
.edit-row{display:none}
.edit-row.open{display:table-row}
.edit-row td{background:var(--surface2);padding:16px;border-bottom:1px solid var(--border)}
.edit-form{display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1.5fr auto;
  gap:12px;align-items:end}

/* ── MODAL (confirm delete) ── */
.modal-overlay{position:fixed;inset:0;background:rgba(14,11,20,.8);
  display:flex;align-items:center;justify-content:center;z-index:100;
  opacity:0;pointer-events:none;transition:opacity .2s}
.modal-overlay.open{opacity:1;pointer-events:all}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  padding:32px;max-width:400px;width:90%;transform:translateY(8px);transition:transform .2s}
.modal-overlay.open .modal{transform:none}
.modal h3{font-family:var(--font-display);font-size:1.2rem;margin-bottom:12px;color:var(--accent3)}
.modal p{font-size:.9rem;color:var(--text2);margin-bottom:24px;line-height:1.6}
.modal .btn-group{justify-content:flex-end}

@media(max-width:900px){
  .shell{grid-template-columns:1fr}
  .sidebar{position:static;height:auto}
  .main{padding:24px 20px}
  .form-grid,.edit-form{grid-template-columns:1fr 1fr}
  .form-grid>:last-child,.edit-form>:last-child{grid-column:1/-1}
}
</style>
</head>
<body>

<div class="shell">
  <!-- SIDEBAR -->
  <aside class="sidebar">
    <div class="logo">Dreamweaving Garden<span>Flower Manager</span></div>
    <div class="sidebar-divider"></div>
    <div class="stat-card">
      <div class="val" id="sTotal">—</div>
      <div class="lbl">Total flowers</div>
    </div>
    <div class="sidebar-divider"></div>
    <a href="/logout" style="display:block;padding:9px 14px;border-radius:8px;
      background:rgba(255,107,138,.1);color:#ff6b8a;border:1px solid rgba(255,107,138,.25);
      font-size:.8rem;font-weight:500;text-decoration:none;text-align:center;
      transition:opacity .15s" onmouseover="this.style.opacity=.8" onmouseout="this.style.opacity=1">
      Sign Out
    </a>
    <div class="sidebar-divider"></div>
    <div class="sidebar-label">Filter by rarity</div>
    <div class="rarity-pills">
      <button class="rpill all active" onclick="setFilter('all',this)">
        All flowers <span class="count" id="cnt-all"></span>
      </button>
      <button class="rpill shine" onclick="setFilter('Shine',this)">
        ✦ Shine <span class="count" id="cnt-Shine"></span>
      </button>
      <button class="rpill star" onclick="setFilter('Star',this)">
        ★ Star <span class="count" id="cnt-Star"></span>
      </button>
      <button class="rpill rare" onclick="setFilter('Rare',this)">
        ◆ Rare <span class="count" id="cnt-Rare"></span>
      </button>
      <button class="rpill fine" onclick="setFilter('Fine',this)">
        ◇ Fine <span class="count" id="cnt-Fine"></span>
      </button>
      <button class="rpill basic" onclick="setFilter('Basic',this)">
        · Basic <span class="count" id="cnt-Basic"></span>
      </button>
    </div>
  </aside>

  <!-- MAIN -->
  <main class="main">
    <div class="page-header">
      <div class="page-title">
        Flower Master List
        <small>Add, edit, and remove flowers for Dreamweaving Garden league.</small>
      </div>
    </div>

    <!-- STATUS -->
    <div class="status-bar" id="statusBar"></div>

    <!-- ADD FORM -->
    <div class="panel">
      <div class="panel-title" id="formTitle">Add New Flower</div>
      <div class="form-grid">
        <div class="field">
          <label>Flower Name</label>
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
          <label>Upgrade Cost <span class="diamond">💎</span></label>
          <input id="fCost" type="number" min="0" placeholder="0"/>
        </div>
        <div class="field">
          <label>Source</label>
          <input id="fSource" placeholder="Garden, Shop, Event…" maxlength="100"/>
        </div>
        <div class="field">
          <label>&nbsp;</label>
          <div class="btn-group">
            <button class="btn btn-primary" onclick="submitForm()">Add</button>
            <button class="btn btn-secondary" id="btnCancel" onclick="cancelEdit()" style="display:none">Cancel</button>
          </div>
        </div>
      </div>
      <div style="margin-top:14px;display:flex;align-items:center;gap:10px">
        <span style="font-size:.78rem;color:var(--text2)">Upgraded points (×2):</span>
        <span class="calc-display"><span class="val" id="calcVal">—</span></span>
      </div>
    </div>

    <!-- TOOLBAR -->
    <div class="toolbar">
      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input class="field input" id="search" placeholder="Search flowers…" oninput="render()"/>
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

<!-- DELETE CONFIRM MODAL -->
<div class="modal-overlay" id="deleteModal">
  <div class="modal">
    <h3>Remove Flower?</h3>
    <p id="deleteMsg">This will permanently remove the flower from the master list. Players who have it tracked will keep their record, but it won't appear in lookups.</p>
    <div class="btn-group">
      <button class="btn btn-secondary" onclick="closeDelete()">Cancel</button>
      <button class="btn btn-danger" onclick="confirmDelete()">Remove</button>
    </div>
  </div>
</div>

<script>
const PW = new URLSearchParams(location.search).get('pw') || '';
const API = (path) => `${path}?pw=${encodeURIComponent(PW)}`;

let flowers = [];
let activeFilter = 'all';
let editingName  = null;
let deleteTarget = null;

// ── HELPERS ──
function esc(s){ return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])) }
function toast(msg, type='ok'){
  const bar = document.getElementById('statusBar');
  bar.innerHTML = `<div class="toast ${type}">${esc(msg)}</div>`;
  setTimeout(()=>{ bar.innerHTML=''; }, 4000);
}
function updateCalc(){
  const v = parseInt(document.getElementById('fPoints').value)||0;
  document.getElementById('calcVal').textContent = v ? (v*2)+' pts' : '—';
}
function rarityOrder(r){ return ({'Shine':0,'Star':1,'Rare':2,'Fine':3,'Basic':4}[r]??9) }

// ── FILTER ──
function setFilter(f, el){
  activeFilter = f;
  document.querySelectorAll('.rpill').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  render();
}

// ── LOAD ──
async function load(){
  try{
    const r = await fetch(API('/api/flowers'));
    if(!r.ok) throw new Error('Auth failed — check your password in the URL (?pw=…)');
    flowers = await r.json();
    updateSidebar();
    render();
  } catch(e){ toast(e.message,'err'); }
}

function updateSidebar(){
  const counts = {};
  flowers.forEach(f=>{ counts[f.rarity]=(counts[f.rarity]||0)+1; });
  document.getElementById('sTotal').textContent = flowers.length;
  document.getElementById('cnt-all').textContent = flowers.length;
  ['Shine','Star','Rare','Fine','Basic'].forEach(r=>{
    const el = document.getElementById('cnt-'+r);
    if(el) el.textContent = counts[r]||0;
  });
}

// ── RENDER ──
function render(){
  const q = document.getElementById('search').value.trim().toLowerCase();
  let rows = flowers.filter(f=>{
    const matchFilter = activeFilter==='all' || f.rarity===activeFilter;
    const matchSearch = !q || f.name.toLowerCase().includes(q) || f.source.toLowerCase().includes(q);
    return matchFilter && matchSearch;
  });
  rows.sort((a,b)=> rarityOrder(a.rarity)-rarityOrder(b.rarity) || a.name.localeCompare(b.name));

  document.getElementById('countBadge').textContent = `${rows.length} flower${rows.length!==1?'s':''}`;
  const tbody = document.getElementById('flowerRows');

  if(!rows.length){
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state">
      <div class="icon">🌸</div>
      <p>${q||activeFilter!=='all' ? 'No flowers match your search.' : 'No flowers yet. Add your first one above.'}</p>
    </div></td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(f=>`
    <tr id="row-${CSS.escape(f.name)}">
      <td><span class="flower-name">${esc(f.name)}</span></td>
      <td><span class="rarity-badge ${esc(f.rarity)}">${esc(f.rarity)}</span></td>
      <td><span class="pts base">${f.base_points}</span></td>
      <td><span class="pts upgraded">${f.base_points*2}</span></td>
      <td><span class="diamond">💎</span> ${f.upgrade_cost.toLocaleString()}</td>
      <td><span class="source-tag">${esc(f.source)}</span></td>
      <td><div class="actions">
        <button class="btn btn-success btn-sm" onclick="startEdit(${JSON.stringify(f.name)})">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="startDelete(${JSON.stringify(f.name)})">Remove</button>
      </div></td>
    </tr>
    <tr class="edit-row" id="edit-${CSS.escape(f.name)}">
      <td colspan="7">
        <div class="edit-form">
          <div class="field">
            <label>Name (locked)</label>
            <input value="${esc(f.name)}" disabled style="opacity:.5"/>
          </div>
          <div class="field">
            <label>Rarity</label>
            <select id="er-${CSS.escape(f.name)}-rarity">
              ${['Shine','Star','Rare','Fine','Basic'].map(r=>`<option${r===f.rarity?' selected':''}>${r}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label>Base Points</label>
            <input id="er-${CSS.escape(f.name)}-pts" type="number" min="0" value="${f.base_points}"
              oninput="updateEditCalc(${JSON.stringify(f.name)})"/>
          </div>
          <div class="field">
            <label>Upgrade Cost 💎</label>
            <input id="er-${CSS.escape(f.name)}-cost" type="number" min="0" value="${f.upgrade_cost}"/>
          </div>
          <div class="field">
            <label>Source</label>
            <input id="er-${CSS.escape(f.name)}-source" value="${esc(f.source)}" maxlength="100"/>
          </div>
          <div class="field">
            <label>&nbsp;</label>
            <div class="btn-group">
              <button class="btn btn-primary btn-sm" onclick="saveEdit(${JSON.stringify(f.name)})">Save</button>
              <button class="btn btn-secondary btn-sm" onclick="closeEdit(${JSON.stringify(f.name)})">Cancel</button>
            </div>
          </div>
        </div>
        <div style="margin-top:10px;font-size:.78rem;color:var(--text2)">
          Upgraded: <span id="er-${CSS.escape(f.name)}-calc" style="color:var(--gold)">${f.base_points*2} pts</span>
        </div>
      </td>
    </tr>
  `).join('');
}

function updateEditCalc(name){
  const pts = parseInt(document.getElementById(`er-${CSS.escape(name)}-pts`).value)||0;
  document.getElementById(`er-${CSS.escape(name)}-calc`).textContent = (pts*2)+' pts';
}

// ── ADD ──
async function submitForm(){
  const name   = document.getElementById('fName').value.trim();
  const rarity = document.getElementById('fRarity').value;
  const pts    = parseInt(document.getElementById('fPoints').value)||0;
  const cost   = parseInt(document.getElementById('fCost').value)||0;
  const source = document.getElementById('fSource').value.trim()||'Unknown';

  if(!name){ toast('Flower name is required.','err'); return; }

  const r = await fetch(API('/api/flowers'), {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name,rarity,base_points:pts,upgrade_cost:cost,source})
  });
  const d = await r.json();
  if(!r.ok){ toast(d.error||'Error adding flower.','err'); return; }
  toast(`✓ "${name}" added to the master list.`);
  resetForm();
  await load();
}

function resetForm(){
  ['fName','fPoints','fCost','fSource'].forEach(id=>{ document.getElementById(id).value=''; });
  document.getElementById('fRarity').value='Basic';
  document.getElementById('calcVal').textContent='—';
  document.getElementById('formTitle').textContent='Add New Flower';
  document.getElementById('btnCancel').style.display='none';
  editingName=null;
}
function cancelEdit(){ resetForm(); }

// ── EDIT ──
function startEdit(name){
  // Close any open edit rows first
  document.querySelectorAll('.edit-row.open').forEach(r=>r.classList.remove('open'));
  const row = document.getElementById('edit-'+CSS.escape(name));
  if(row) row.classList.add('open');
}
function closeEdit(name){
  const row = document.getElementById('edit-'+CSS.escape(name));
  if(row) row.classList.remove('open');
}
async function saveEdit(name){
  const rarity = document.getElementById(`er-${CSS.escape(name)}-rarity`).value;
  const pts    = parseInt(document.getElementById(`er-${CSS.escape(name)}-pts`).value)||0;
  const cost   = parseInt(document.getElementById(`er-${CSS.escape(name)}-cost`).value)||0;
  const source = document.getElementById(`er-${CSS.escape(name)}-source`).value.trim()||'Unknown';

  const r = await fetch(API(`/api/flowers/${encodeURIComponent(name)}`), {
    method:'PUT', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({rarity,base_points:pts,upgrade_cost:cost,source})
  });
  const d = await r.json();
  if(!r.ok){ toast(d.error||'Error saving.','err'); return; }
  toast(`✓ "${name}" updated.`);
  await load();
}

// ── DELETE ──
function startDelete(name){
  deleteTarget = name;
  document.getElementById('deleteMsg').textContent =
    `Remove "${name}" from the master list? Players who have it tracked will keep their record, but it won't appear in lookups.`;
  document.getElementById('deleteModal').classList.add('open');
}
function closeDelete(){
  deleteTarget=null;
  document.getElementById('deleteModal').classList.remove('open');
}
async function confirmDelete(){
  if(!deleteTarget) return;
  const name = deleteTarget;
  closeDelete();
  const r = await fetch(API(`/api/flowers/${encodeURIComponent(name)}`), {method:'DELETE'});
  const d = await r.json();
  if(!r.ok){ toast(d.error||'Error removing.','err'); return; }
  toast(`✓ "${name}" removed.`);
  await load();
}

// ── CLOSE MODAL ON BACKDROP ──
document.getElementById('deleteModal').addEventListener('click', e=>{
  if(e.target===e.currentTarget) closeDelete();
});

// ── INIT ──
load();
</script>
</body>
</html>
"""


LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>DWG · Admin Login</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0e0b14;
  --surface:#18132a;
  --border:#2e2450;
  --accent:#c9a0ff;
  --accent2:#b8f2d0;
  --text:#e8e0f5;
  --text2:#9f93c0;
  --text3:#5e5480;
  --danger:#ff6b8a;
  --font-display:\'Playfair Display\',Georgia,serif;
  --font-body:\'DM Sans\',system-ui,sans-serif;
  --radius:14px;
}
body{
  background:var(--bg);color:var(--text);font-family:var(--font-body);
  min-height:100vh;display:flex;align-items:center;justify-content:center;
  background-image:
    radial-gradient(ellipse at 20% 10%,rgba(100,60,180,.22) 0%,transparent 55%),
    radial-gradient(ellipse at 80% 90%,rgba(184,242,208,.1) 0%,transparent 50%);
}
.card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:48px 44px;width:100%;max-width:400px;
  position:relative;overflow:hidden;
}
.card::before{
  content:\'\';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--accent),var(--accent2),#f4d58d);
}
.logo{
  font-family:var(--font-display);font-size:1.6rem;font-weight:700;
  color:var(--accent);text-align:center;margin-bottom:6px;
}
.subtitle{
  text-align:center;font-size:.82rem;color:var(--text3);
  letter-spacing:.06em;text-transform:uppercase;margin-bottom:36px;
}
label{
  display:block;font-size:.72rem;font-weight:500;letter-spacing:.09em;
  text-transform:uppercase;color:var(--text2);margin-bottom:8px;
}
input[type=password]{
  width:100%;background:#0e0b14;border:1px solid var(--border);
  border-radius:9px;padding:12px 16px;font-size:.95rem;color:var(--text);
  font-family:var(--font-body);outline:none;
  transition:border-color .15s,box-shadow .15s;
}
input[type=password]:focus{
  border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(201,160,255,.15);
}
button{
  width:100%;margin-top:20px;padding:13px;border:none;
  border-radius:9px;background:var(--accent);color:#0e0b14;
  font-size:.95rem;font-weight:600;font-family:var(--font-body);
  cursor:pointer;transition:opacity .15s,transform .1s;
}
button:hover{opacity:.88;transform:translateY(-1px)}
button:active{transform:none}
.error{
  margin-top:16px;padding:11px 14px;border-radius:8px;font-size:.85rem;
  background:rgba(255,107,138,.1);color:var(--danger);
  border:1px solid rgba(255,107,138,.25);text-align:center;
}
.footer-note{
  margin-top:28px;text-align:center;font-size:.75rem;color:var(--text3);
}
</style>
</head>
<body>
<div class="card">
  <div class="logo">🌸 Dreamweaving Garden</div>
  <div class="subtitle">Flower Manager · Admin</div>
  <form method="POST" action="/login">
    <label for="password">Password</label>
    <input type="password" id="password" name="password"
           placeholder="Enter admin password" autofocus autocomplete="current-password"/>
    {% if error %}
    <div class="error">{{ error }}</div>
    {% endif %}
    <button type="submit">Sign In</button>
  </form>
  <div class="footer-note">Dreamweaving Garden • Grow together, bloom brighter</div>
</div>
</body>
</html>"""


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
    def run():
        log.info("Admin dashboard starting on port %d", ADMIN_PORT)
        admin_app.run(host="0.0.0.0", port=ADMIN_PORT, debug=False, use_reloader=False)

    t = threading.Thread(target=run, daemon=True, name="admin-dashboard")
    t.start()
    log.info("Admin dashboard thread started.")
