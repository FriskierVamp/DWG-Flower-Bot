"""
DWG Flower Bot – Admin Dashboard
Flask application served in a background thread.
All HTML/JS uses NO backticks so the Python triple-quoted string stays intact.
"""

import hmac
import json
import logging
import os
import threading

from flask import Flask, redirect, render_template_string, request, session, url_for

log = logging.getLogger(__name__)

admin_app = Flask(__name__)
admin_app.secret_key = os.getenv("FLASK_SECRET", "dwg-changeme-secret")

ADMIN_SECRET = os.getenv("ADMIN_PASSWORD", "changeme")


# ── require login decorator ──────────────────────────────────────────────────

def require_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── DB helpers (lazy import to avoid circular) ───────────────────────────────

def _db():
    from db.schema import get_db
    return get_db()


# ── API routes ───────────────────────────────────────────────────────────────

@admin_app.route("/api/flowers", methods=["GET"])
@require_login
def api_flowers_list():
    cur = _db().execute(
        "SELECT name, rarity, base_points, upgrade_cost, source "
        "FROM flowers ORDER BY rarity, name"
    )
    rows = [dict(r) for r in cur.fetchall()]
    return json.dumps(rows), 200, {"Content-Type": "application/json"}


@admin_app.route("/api/flowers", methods=["POST"])
@require_login
def api_flowers_add():
    data = request.get_json(force=True)
    name   = (data.get("name") or "").strip()
    rarity = (data.get("rarity") or "Basic").strip()
    pts    = int(data.get("base_points") or 0)
    cost   = int(data.get("upgrade_cost") or 0)
    source = (data.get("source") or "Unknown").strip()
    if not name:
        return json.dumps({"error": "Name required"}), 400, {"Content-Type": "application/json"}
    db = _db()
    try:
        db.execute(
            "INSERT INTO flowers(name,rarity,base_points,upgrade_cost,source) VALUES(?,?,?,?,?)",
            (name, rarity, pts, cost, source)
        )
        db.commit()
    except Exception as e:
        return json.dumps({"error": str(e)}), 409, {"Content-Type": "application/json"}
    return json.dumps({"ok": True}), 201, {"Content-Type": "application/json"}


@admin_app.route("/api/flowers/<path:name>", methods=["PUT"])
@require_login
def api_flowers_update(name):
    data   = request.get_json(force=True)
    rarity = (data.get("rarity") or "Basic").strip()
    pts    = int(data.get("base_points") or 0)
    cost   = int(data.get("upgrade_cost") or 0)
    source = (data.get("source") or "Unknown").strip()
    db = _db()
    db.execute(
        "UPDATE flowers SET rarity=?,base_points=?,upgrade_cost=?,source=? WHERE name=?",
        (rarity, pts, cost, source, name)
    )
    db.commit()
    return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}


@admin_app.route("/api/flowers/<path:name>", methods=["DELETE"])
@require_login
def api_flowers_delete(name):
    db = _db()
    db.execute("DELETE FROM flowers WHERE name=?", (name,))
    db.commit()
    return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}


@admin_app.route("/api/flowers/bulk", methods=["POST"])
@require_login
def api_flowers_bulk():
    data   = request.get_json(force=True)
    rows   = data.get("rows", [])
    db     = _db()
    imported = 0
    skipped  = 0
    errors   = []
    VALID_RARITIES = {"Basic", "Fine", "Rare", "Star", "Shine"}
    for row in rows:
        name   = (row.get("name") or "").strip()
        rarity = (row.get("rarity") or "Basic").strip().capitalize()
        source = (row.get("source") or "Unknown").strip()
        try:
            pts  = int(float(row.get("points") or 0))
            cost = int(float(row.get("upgrade_cost") or 0))
        except (ValueError, TypeError):
            pts, cost = 0, 0
        if not name:
            skipped += 1
            continue
        if rarity not in VALID_RARITIES:
            errors.append(f"{name}: invalid rarity '{rarity}'")
            skipped += 1
            continue
        try:
            db.execute(
                "INSERT INTO flowers(name,rarity,base_points,upgrade_cost,source) VALUES(?,?,?,?,?)",
                (name, rarity, pts, cost, source)
            )
            imported += 1
        except Exception as e:
            errors.append(f"{name}: {e}")
            skipped += 1
    db.commit()
    return json.dumps({"imported": imported, "skipped": skipped, "errors": errors}), 200, {
        "Content-Type": "application/json"
    }


# ── CSS ─────────────────────────────────────────────────────────────────────

CSS = """
:root{
  --cream:#fdf8f2;--pink:#f9c6d0;--lavender:#d8c6f0;--mint:#b8e8d0;
  --sage:#8fbc8f;--wood:#8b5e3c;--text1:#3d2b1f;--text2:#7a5c4a;
  --border:#e8d5c4;--white:#fff;--shadow:rgba(61,43,31,.08);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--cream);color:var(--text1);min-height:100vh}
a{color:var(--wood);text-decoration:none}

/* NAV */
.nav{background:linear-gradient(135deg,var(--lavender),var(--pink));
  padding:0 24px;display:flex;align-items:center;gap:16px;
  box-shadow:0 2px 8px var(--shadow);height:56px}
.nav-brand{font-weight:700;font-size:1.15rem;color:var(--text1);margin-right:auto}
.nav a{color:var(--text1);font-size:.9rem;padding:6px 12px;border-radius:6px;transition:.2s}
.nav a:hover{background:rgba(255,255,255,.35)}

/* BANNER */
.banner{width:100%;max-height:180px;object-fit:cover;display:block}

/* LAYOUT */
.container{max-width:1100px;margin:0 auto;padding:24px 16px}
.section{background:var(--white);border-radius:14px;box-shadow:0 2px 12px var(--shadow);
  padding:24px;margin-bottom:24px}
h2{font-size:1.2rem;color:var(--wood);margin-bottom:16px;
  padding-bottom:8px;border-bottom:2px solid var(--pink)}

/* BUTTONS */
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;
  border:none;border-radius:8px;cursor:pointer;font-size:.88rem;font-weight:600;transition:.2s}
.btn-primary{background:var(--lavender);color:var(--text1)}
.btn-primary:hover{background:#c8b0e8}
.btn-secondary{background:var(--border);color:var(--text1)}
.btn-secondary:hover{background:#d8c0ac}
.btn-success{background:var(--mint);color:var(--text1)}
.btn-success:hover{background:#90d4b0}
.btn-danger{background:#f8c8c8;color:#8b2020}
.btn-danger:hover{background:#f0a0a0}
.btn-sm{padding:5px 11px;font-size:.8rem}
.btn-group{display:flex;gap:8px;flex-wrap:wrap}

/* FORM */
.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;align-items:end}
.field{display:flex;flex-direction:column;gap:4px}
.field label{font-size:.82rem;font-weight:600;color:var(--text2)}
.field input,.field select{padding:8px 10px;border:1px solid var(--border);
  border-radius:8px;background:var(--cream);font-size:.88rem;color:var(--text1);width:100%}
.field input:focus,.field select:focus{outline:2px solid var(--lavender);border-color:transparent}
.calc-hint{font-size:.78rem;color:var(--text2);margin-top:8px}

/* TABLE */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.87rem}
th{background:linear-gradient(135deg,var(--lavender),var(--pink));
  color:var(--text1);font-weight:600;padding:10px 12px;text-align:left;white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:hover td{background:rgba(248,235,235,.4)}

/* BADGES */
.flower-name{font-weight:600}
.rarity-badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:.78rem;font-weight:700}
.rarity-badge.Shine{background:#fff3b0;color:#7a6200}
.rarity-badge.Star{background:#ffe0f0;color:#8b004a}
.rarity-badge.Rare{background:var(--lavender);color:#4a1880}
.rarity-badge.Fine{background:var(--mint);color:#1a5c38}
.rarity-badge.Basic{background:var(--border);color:var(--text2)}
.pts-base{color:var(--wood);font-weight:600}
.pts-up{color:#6a4c93;font-weight:600}
.source-tag{background:var(--cream);border:1px solid var(--border);border-radius:5px;
  padding:2px 7px;font-size:.78rem;color:var(--text2)}
.diamond{font-size:.95rem}

/* EDIT ROW */
.edit-row{display:none}
.edit-row.open{display:table-row}
.edit-row td{background:linear-gradient(135deg,#f9f2ff,#fff2f5);padding:16px}
.edit-form{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.edit-form .field{min-width:130px}
.edit-form input,.edit-form select{padding:6px 8px;font-size:.83rem}

/* FILTERS */
.filters{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;align-items:center}
.filters input{flex:1;min-width:180px;padding:8px 12px;border:1px solid var(--border);
  border-radius:8px;background:var(--cream);font-size:.88rem}
.filter-btn{padding:6px 14px;border:1px solid var(--border);border-radius:20px;
  background:var(--white);cursor:pointer;font-size:.82rem;transition:.2s}
.filter-btn.active,.filter-btn:hover{background:var(--lavender);border-color:var(--lavender)}
#countBadge{font-size:.82rem;color:var(--text2);margin-left:4px}

/* TOAST */
#toast{position:fixed;bottom:24px;right:24px;background:var(--wood);color:#fff;
  padding:12px 20px;border-radius:10px;font-size:.88rem;box-shadow:0 4px 16px rgba(0,0,0,.2);
  opacity:0;transform:translateY(10px);transition:.3s;pointer-events:none;z-index:9999}
#toast.show{opacity:1;transform:translateY(0)}
#toast.err{background:#c0392b}

/* DELETE MODAL */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.35);
  display:none;align-items:center;justify-content:center;z-index:999}
.modal-overlay.open{display:flex}
.modal{background:var(--white);border-radius:14px;padding:28px;max-width:420px;width:90%;
  box-shadow:0 8px 32px rgba(0,0,0,.18)}
.modal h3{margin-bottom:12px;color:var(--wood)}
.modal p{font-size:.9rem;color:var(--text2);margin-bottom:20px}
.modal .btn-group{justify-content:flex-end}

/* BULK IMPORT */
#importPanel{margin-top:16px;border:1px dashed var(--border);border-radius:10px;padding:16px}
.drop-zone{border:2px dashed var(--lavender);border-radius:10px;padding:24px;text-align:center;
  color:var(--text2);cursor:pointer;transition:.2s}
.drop-zone.drag{background:rgba(216,198,240,.2)}
.progress-wrap{margin:12px 0;display:none}
.progress-bar{height:8px;background:var(--border);border-radius:4px;overflow:hidden}
.progress-fill{height:100%;background:var(--lavender);width:0;transition:.4s}
.import-results{padding:12px;border-radius:8px;font-size:.88rem;display:none}
.import-results.ok{background:#e8f8ee;border:1px solid var(--mint)}
.import-results.warn{background:#fff8e8;border:1px solid #f0d060}

/* LOGIN */
.login-page{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
  background:linear-gradient(135deg,var(--lavender),var(--pink),var(--mint))}
.login-card{background:var(--white);border-radius:18px;padding:36px 40px;
  box-shadow:0 8px 40px rgba(0,0,0,.15);width:90%;max-width:380px;text-align:center}
.login-card img{width:80px;height:80px;border-radius:50%;margin-bottom:16px}
.login-card h1{font-size:1.4rem;color:var(--wood);margin-bottom:4px}
.login-card p{font-size:.9rem;color:var(--text2);margin-bottom:24px}
.login-card input[type=password]{width:100%;padding:10px 14px;border:1px solid var(--border);
  border-radius:8px;font-size:1rem;background:var(--cream);margin-bottom:14px}
.login-card button{width:100%;padding:11px;background:var(--lavender);border:none;
  border-radius:8px;font-size:1rem;font-weight:700;color:var(--text1);cursor:pointer;transition:.2s}
.login-card button:hover{background:#c8b0e8}
.login-err{color:#c0392b;font-size:.87rem;margin-bottom:10px}
"""

# ── Login page HTML ─────────────────────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DWG Admin – Login</title>
<style>""" + CSS + """</style>
</head>
<body class="login-page">
<div class="login-card">
  <img src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/icon.png"
       alt="DWG icon" onerror="this.style.display='none'">
  <h1>&#127808; DWG Admin</h1>
  <p>Dreamweaving Garden flower manager</p>
  {% if error %}<div class="login-err">{{ error }}</div>{% endif %}
  <form method="POST">
    <input type="password" name="password" placeholder="Admin password" autofocus>
    <button type="submit">Sign In</button>
  </form>
</div>
</body>
</html>"""


# ── Dashboard JS (no backticks — pure string concatenation) ─────────────────
# Written as a plain Python string so the surrounding triple-quote is never broken.

DASHBOARD_JS = r"""
var allFlowers = [];
var activeFilter = 'all';
var deleteTarget = null;

function API(path){
  var base = window.location.origin;
  return base + path;
}

function esc(s){
  if(s == null) return '';
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toast(msg, type){
  var el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show' + (type === 'err' ? ' err' : '');
  clearTimeout(el._t);
  el._t = setTimeout(function(){ el.className = ''; }, 3200);
}

async function load(){
  var r = await fetch(API('/api/flowers'));
  allFlowers = await r.json();
  render();
}

function render(){
  var q = (document.getElementById('searchBox').value || '').toLowerCase();
  var filtered = allFlowers.filter(function(f){
    if(activeFilter !== 'all' && f.rarity !== activeFilter) return false;
    if(q && f.name.toLowerCase().indexOf(q) === -1 &&
       (f.source || '').toLowerCase().indexOf(q) === -1) return false;
    return true;
  });

  var countEl = document.getElementById('countBadge');
  countEl.textContent = filtered.length + ' flower' + (filtered.length !== 1 ? 's' : '');

  var tbody = document.getElementById('flowerTbody');
  if(!filtered.length){
    var msg = (q || activeFilter !== 'all') ? 'No flowers match your search.' : 'No flowers yet. Add one above!';
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text2);padding:32px">' + esc(msg) + '</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(function(f){
    var n = JSON.stringify(f.name);
    var e = CSS.escape(f.name);
    var opts = ['Shine','Star','Rare','Fine','Basic'].map(function(r){
      return '<option' + (r === f.rarity ? ' selected' : '') + '>' + r + '</option>';
    }).join('');
    return '<tr id="row-' + e + '">'
      + '<td><span class="flower-name">' + esc(f.name) + '</span></td>'
      + '<td><span class="rarity-badge ' + esc(f.rarity) + '">' + esc(f.rarity) + '</span></td>'
      + '<td><span class="pts-base">' + f.base_points + '</span></td>'
      + '<td><span class="pts-up">' + (f.base_points * 2) + '</span></td>'
      + '<td>&#128142; ' + f.upgrade_cost.toLocaleString() + '</td>'
      + '<td><span class="source-tag">' + esc(f.source) + '</span></td>'
      + '<td><div class="actions btn-group">'
        + '<button class="btn btn-success btn-sm" onclick="startEdit(' + n + ')">Edit</button>'
        + '<button class="btn btn-danger btn-sm" onclick="startDelete(' + n + ')">Remove</button>'
      + '</div></td></tr>'
      + '<tr class="edit-row" id="edit-' + e + '">'
      + '<td colspan="7"><div class="edit-form">'
        + '<div class="field"><label>Name (locked)</label>'
          + '<input value="' + esc(f.name) + '" disabled style="opacity:.55"/></div>'
        + '<div class="field"><label>Rarity</label>'
          + '<select id="er-' + e + '-rarity">' + opts + '</select></div>'
        + '<div class="field"><label>Base Points</label>'
          + '<input id="er-' + e + '-pts" type="number" min="0" value="' + f.base_points + '" oninput="updateEditCalc(' + n + ')"/></div>'
        + '<div class="field"><label>Upgrade Cost &#128142;</label>'
          + '<input id="er-' + e + '-cost" type="number" min="0" value="' + f.upgrade_cost + '"/></div>'
        + '<div class="field"><label>Source</label>'
          + '<input id="er-' + e + '-source" value="' + esc(f.source) + '" maxlength="100"/></div>'
        + '<div class="field"><label>&nbsp;</label><div class="btn-group">'
          + '<button class="btn btn-primary btn-sm" onclick="saveEdit(' + n + ')">Save</button>'
          + '<button class="btn btn-secondary btn-sm" onclick="closeEdit(' + n + ')">Cancel</button>'
        + '</div></div>'
      + '</div>'
      + '<div style="margin-top:10px;font-size:.77rem;color:var(--text2)">'
        + 'Upgraded: <span id="er-' + e + '-calc" style="color:var(--wood);font-weight:600">' + (f.base_points * 2) + ' pts</span>'
      + '</div></td></tr>';
  }).join('');
}

function updateEditCalc(name){
  var e = CSS.escape(name);
  var pts = parseInt(document.getElementById('er-' + e + '-pts').value) || 0;
  document.getElementById('er-' + e + '-calc').textContent = (pts * 2) + ' pts';
}

function startEdit(name){
  document.querySelectorAll('.edit-row.open').forEach(function(r){ r.classList.remove('open'); });
  var row = document.getElementById('edit-' + CSS.escape(name));
  if(row) row.classList.add('open');
}
function closeEdit(name){
  var row = document.getElementById('edit-' + CSS.escape(name));
  if(row) row.classList.remove('open');
}

async function saveEdit(name){
  var e = CSS.escape(name);
  var rarity = document.getElementById('er-' + e + '-rarity').value;
  var pts    = parseInt(document.getElementById('er-' + e + '-pts').value) || 0;
  var cost   = parseInt(document.getElementById('er-' + e + '-cost').value) || 0;
  var source = document.getElementById('er-' + e + '-source').value.trim() || 'Unknown';
  var r = await fetch(API('/api/flowers/' + encodeURIComponent(name)), {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({rarity: rarity, base_points: pts, upgrade_cost: cost, source: source})
  });
  var d = await r.json();
  if(!r.ok){ toast(d.error || 'Error saving.', 'err'); return; }
  toast('Updated "' + name + '".');
  await load();
}

function startDelete(name){
  deleteTarget = name;
  document.getElementById('deleteMsg').textContent =
    'Remove "' + name + '" from the master list? Players who tracked it will keep their record.';
  document.getElementById('deleteModal').classList.add('open');
}
function closeDelete(){
  deleteTarget = null;
  document.getElementById('deleteModal').classList.remove('open');
}
async function confirmDelete(){
  if(!deleteTarget) return;
  var name = deleteTarget;
  closeDelete();
  var r = await fetch(API('/api/flowers/' + encodeURIComponent(name)), {method: 'DELETE'});
  var d = await r.json();
  if(!r.ok){ toast(d.error || 'Error removing.', 'err'); return; }
  toast('Removed "' + name + '".');
  await load();
}

document.addEventListener('DOMContentLoaded', function(){
  var dm = document.getElementById('deleteModal');
  if(dm) dm.addEventListener('click', function(ev){ if(ev.target === ev.currentTarget) closeDelete(); });
  var ip = document.getElementById('importPanel');
  if(ip) ip.style.display = 'none';
});

function setFilter(rarity){
  activeFilter = rarity;
  document.querySelectorAll('.filter-btn').forEach(function(b){
    b.classList.toggle('active', b.dataset.rarity === rarity);
  });
  render();
}

async function submitForm(){
  var name   = document.getElementById('fName').value.trim();
  var rarity = document.getElementById('fRarity').value;
  var pts    = parseInt(document.getElementById('fPoints').value) || 0;
  var cost   = parseInt(document.getElementById('fCost').value) || 0;
  var source = document.getElementById('fSource').value.trim() || 'Unknown';
  if(!name){ toast('Flower name is required.', 'err'); return; }
  var r = await fetch(API('/api/flowers'), {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: name, rarity: rarity, base_points: pts, upgrade_cost: cost, source: source})
  });
  var d = await r.json();
  if(!r.ok){ toast(d.error || 'Error adding flower.', 'err'); return; }
  toast('Added "' + name + '" to the master list!');
  resetForm();
  await load();
}

function resetForm(){
  ['fName','fPoints','fCost','fSource'].forEach(function(id){ document.getElementById(id).value = ''; });
  document.getElementById('fRarity').value = 'Basic';
  document.getElementById('calcVal').textContent = '--';
}

function updateCalc(){
  var pts = parseInt(document.getElementById('fPoints').value) || 0;
  document.getElementById('calcVal').textContent = pts ? (pts * 2) + ' pts' : '--';
}

/* ── BULK IMPORT ── */
var importVisible = false;
function toggleImport(){
  var panel = document.getElementById('importPanel');
  importVisible = !importVisible;
  panel.style.display = importVisible ? '' : 'none';
  document.getElementById('importToggle').textContent = importVisible ? 'Hide Import' : 'Bulk Import';
}
function dragOver(ev){ ev.preventDefault(); document.getElementById('dropZone').classList.add('drag'); }
function dragLeave(){ document.getElementById('dropZone').classList.remove('drag'); }
function dropFile(ev){
  ev.preventDefault(); dragLeave();
  var file = ev.dataTransfer.files[0];
  if(file) processFile(file);
}
function handleFile(ev){ if(ev.target.files[0]) processFile(ev.target.files[0]); }
function processFile(file){
  var reader = new FileReader();
  reader.onload = function(ev){
    document.getElementById('pasteArea').value = ev.target.result;
    importFromPaste();
  };
  reader.readAsText(file);
}
function parseRows(raw){
  var lines = raw.trim().split(/\r?\n/);
  if(!lines.length) return [];
  var first = lines[0];
  var delim = first.indexOf('\t') !== -1 ? '\t' : ',';
  var firstLower = first.toLowerCase();
  var hasHeader = firstLower.indexOf('flower') !== -1 || firstLower.indexOf('name') !== -1 || firstLower.indexOf('type') !== -1;
  var dataLines = hasHeader ? lines.slice(1) : lines;
  return dataLines.map(function(line){
    var cols;
    if(delim === ','){
      cols = []; var cur = '', inQ = false;
      for(var i = 0; i < line.length; i++){
        var c = line[i];
        if(c === '"'){ inQ = !inQ; }
        else if(c === ',' && !inQ){ cols.push(cur.trim()); cur = ''; }
        else { cur += c; }
      }
      cols.push(cur.trim());
    } else {
      cols = line.split('\t').map(function(c){ return c.trim(); });
    }
    return {name: cols[0]||'', rarity: cols[1]||'', source: cols[2]||'Unknown', points: cols[3]||'0', upgrade_cost: cols[4]||'0'};
  }).filter(function(r){ return r.name.length > 0; });
}
async function importFromPaste(){
  var raw = document.getElementById('pasteArea').value.trim();
  if(!raw){ toast('Nothing to import.', 'err'); return; }
  var rows = parseRows(raw);
  if(!rows.length){ toast('Could not parse any rows.', 'err'); return; }
  var wrap = document.getElementById('progressWrap');
  var fill = document.getElementById('progressFill');
  var label = document.getElementById('progressLabel');
  var res = document.getElementById('importResults');
  wrap.style.display = 'block'; res.style.display = 'none';
  fill.style.width = '10%';
  label.textContent = 'Importing ' + rows.length + ' flowers...';
  var r = await fetch(API('/api/flowers/bulk'), {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({rows: rows})
  });
  fill.style.width = '100%';
  var d = await r.json();
  setTimeout(function(){ wrap.style.display = 'none'; fill.style.width = '0'; }, 800);
  var hasErrors = d.errors && d.errors.length > 0;
  res.className = 'import-results ' + (hasErrors ? 'warn' : 'ok');
  res.style.display = 'block';
  var html = (hasErrors ? '<strong>&#9888; Import Complete</strong>' : '<strong>&#127800; Import Complete</strong>') + '<br/>';
  html += '&#9989; ' + d.imported + ' flower' + (d.imported !== 1 ? 's' : '') + ' imported';
  if(d.skipped) html += ' &nbsp;&#183;&nbsp; &#9193; ' + d.skipped + ' skipped';
  if(hasErrors){
    html += '<br/><br/><strong>Issues:</strong><ul style="margin:6px 0 0 16px">';
    d.errors.slice(0, 10).forEach(function(e){ html += '<li>' + esc(e) + '</li>'; });
    if(d.errors.length > 10) html += '<li>...and ' + (d.errors.length - 10) + ' more</li>';
    html += '</ul>';
  }
  res.innerHTML = html;
  await load();
  toast(hasErrors ? 'Imported ' + d.imported + ' with ' + d.errors.length + ' issue(s).' : 'Imported ' + d.imported + ' flowers successfully!');
}

load();
"""


# ── Dashboard HTML ───────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DWG Flower Admin</title>
<style>""" + CSS + """</style>
</head>
<body>

<nav class="nav">
  <span class="nav-brand">&#127808; DWG Flower Admin</span>
  <a href="/logout">Logout</a>
</nav>

<img class="banner"
  src="https://raw.githubusercontent.com/FriskierVamp/DWG-Flower-Bot/main/assets/banner.png"
  alt="DWG banner" onerror="this.style.display='none'">

<div class="container">

  <!-- Add flower -->
  <div class="section">
    <h2>&#127799; Add New Flower</h2>
    <div class="form-grid">
      <div class="field">
        <label>Flower Name</label>
        <input id="fName" type="text" placeholder="Sunbloom Lily" maxlength="100">
      </div>
      <div class="field">
        <label>Rarity</label>
        <select id="fRarity">
          <option>Basic</option><option>Fine</option><option>Rare</option>
          <option>Star</option><option>Shine</option>
        </select>
      </div>
      <div class="field">
        <label>Base Points</label>
        <input id="fPoints" type="number" min="0" placeholder="0" oninput="updateCalc()">
      </div>
      <div class="field">
        <label>Upgrade Cost &#128142;</label>
        <input id="fCost" type="number" min="0" placeholder="0">
      </div>
      <div class="field">
        <label>How to Obtain</label>
        <input id="fSource" type="text" placeholder="Event / Shop / Drop" maxlength="100">
      </div>
      <div class="field">
        <label>&nbsp;</label>
        <div class="btn-group">
          <button class="btn btn-primary" onclick="submitForm()">&#10010; Add Flower</button>
        </div>
      </div>
    </div>
    <p class="calc-hint">Upgraded pts: <strong id="calcVal">--</strong></p>
  </div>

  <!-- Bulk import -->
  <div class="section">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <h2 style="margin-bottom:0;border:none;padding:0">&#128229; Bulk Import</h2>
      <button id="importToggle" class="btn btn-secondary btn-sm" onclick="toggleImport()">Bulk Import</button>
    </div>
    <div id="importPanel">
      <div id="dropZone" class="drop-zone" style="margin-top:12px"
           ondragover="dragOver(event)" ondragleave="dragLeave()" ondrop="dropFile(event)"
           onclick="document.getElementById('fileInput').click()">
        &#128229; Drop a CSV / TSV here or click to browse
        <input id="fileInput" type="file" accept=".csv,.tsv,.txt" style="display:none" onchange="handleFile(event)">
      </div>
      <div style="text-align:center;margin:8px 0;color:var(--text2);font-size:.85rem">or paste below</div>
      <textarea id="pasteArea" rows="4" style="width:100%;padding:8px;border:1px solid var(--border);
        border-radius:8px;font-size:.83rem;background:var(--cream)" placeholder="Name&#9;Rarity&#9;Source&#9;Points&#9;UpgradeCost"></textarea>
      <div style="margin-top:8px">
        <button class="btn btn-primary" onclick="importFromPaste()">Import</button>
      </div>
      <div id="progressWrap" class="progress-wrap">
        <div id="progressLabel" style="font-size:.82rem;color:var(--text2);margin-bottom:4px"></div>
        <div class="progress-bar"><div id="progressFill" class="progress-fill"></div></div>
      </div>
      <div id="importResults" class="import-results"></div>
    </div>
  </div>

  <!-- Flower list -->
  <div class="section">
    <h2>&#127807; Flower Master List <span id="countBadge"></span></h2>
    <div class="filters">
      <input id="searchBox" type="text" placeholder="Search flowers..." oninput="render()">
      <button class="filter-btn active" data-rarity="all" onclick="setFilter('all')">All</button>
      <button class="filter-btn" data-rarity="Basic" onclick="setFilter('Basic')">Basic</button>
      <button class="filter-btn" data-rarity="Fine" onclick="setFilter('Fine')">Fine</button>
      <button class="filter-btn" data-rarity="Rare" onclick="setFilter('Rare')">Rare</button>
      <button class="filter-btn" data-rarity="Star" onclick="setFilter('Star')">&#11088; Star</button>
      <button class="filter-btn" data-rarity="Shine" onclick="setFilter('Shine')">&#10024; Shine</button>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>Name</th><th>Rarity</th><th>Base pts</th><th>Upgraded</th>
          <th>Cost &#128142;</th><th>Source</th><th>Actions</th>
        </tr></thead>
        <tbody id="flowerTbody"><tr><td colspan="7" style="text-align:center;padding:32px;color:var(--text2)">Loading...</td></tr></tbody>
      </table>
    </div>
  </div>

</div><!-- /container -->

<!-- Delete modal -->
<div class="modal-overlay" id="deleteModal">
  <div class="modal">
    <h3>&#128465; Remove Flower</h3>
    <p id="deleteMsg"></p>
    <div class="btn-group">
      <button class="btn btn-secondary" onclick="closeDelete()">Cancel</button>
      <button class="btn btn-danger" onclick="confirmDelete()">Remove</button>
    </div>
  </div>
</div>

<!-- Toast -->
<div id="toast"></div>

<script>
""" + DASHBOARD_JS + """
</script>
</body>
</html>"""


# ── Routes ───────────────────────────────────────────────────────────────────

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


# ── Thread launcher ──────────────────────────────────────────────────────────

def start_admin_dashboard() -> None:
    port = int(os.getenv("PORT", os.getenv("ADMIN_PORT", 5000)))
    def run():
        log.info("Admin dashboard starting on port %d", port)
        admin_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    t = threading.Thread(target=run, daemon=True, name="admin-dashboard")
    t.start()
    log.info("Admin dashboard thread started.")
