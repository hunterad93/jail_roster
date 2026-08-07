import logging
import threading
import time

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rapidfuzz import fuzz

from jail_roster.scrapers import scrape_all
from jail_roster.storage import read_inmates, read_metadata, write_inmates, write_metadata

log = logging.getLogger(__name__)

app = FastAPI()

_inmates: list[dict] = []
_sync_status: list[dict] = []
_last_updated: float = 0
_lock = threading.Lock()


def _load_data() -> tuple[list[dict], list[dict]]:
    return read_inmates(), read_metadata()


def _refresh_cache():
    global _inmates, _sync_status, _last_updated
    with _lock:
        try:
            _inmates, _sync_status = _load_data()
            _last_updated = time.time()
            log.info("Cache refreshed: %d inmates", len(_inmates))
        except Exception:
            log.exception("Failed to refresh cache from sheet")


def _get_inmates() -> list[dict]:
    if not _inmates or (time.time() - _last_updated > 300):
        _refresh_cache()
    return _inmates


@app.on_event("startup")
def startup():
    _refresh_cache()


ALLOWED_SA = "public-jail-roster-database@magnetic-mender-389117.iam.gserviceaccount.com"


def _verify_oidc(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization[7:]
    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request())
        if claims.get("email") != ALLOWED_SA:
            raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/api/scrape")
def trigger_scrape(authorization: str | None = Header(default=None)):
    _verify_oidc(authorization)

    old_inmates, _ = _load_data()

    inmates, metadata = scrape_all()

    failed_counties = {m["county"] for m in metadata if m["status"] == "error"}
    if failed_counties:
        county_to_jail = {
            "Missoula": "Missoula County", "Flathead": "Flathead County",
            "Ravalli": "Ravalli County", "Gallatin": "Gallatin County",
            "Park": "Park County", "Lake": "Lake County",
            "Lewis & Clark": "Lewis & Clark County", "Deer Lodge": "Deer Lodge County",
            "Wheatland": "Wheatland County", "Jefferson": "Jefferson County",
            "Broadwater": "Broadwater County",
            "Yellowstone": "Yellowstone County",
        }
        failed_jails = {county_to_jail[c] for c in failed_counties if c in county_to_jail}
        stale_rows = [i for i in old_inmates if i.get("jail") in failed_jails]
        inmates.extend(stale_rows)
        for m in metadata:
            if m["status"] == "error":
                m["count"] = sum(1 for i in old_inmates if i.get("jail") == county_to_jail.get(m["county"]))

    write_inmates(inmates)
    write_metadata(metadata)
    _refresh_cache()
    return {"status": "ok", "count": len(inmates)}


@app.get("/api/search")
def search(q: str = Query(default=""), jail: str = Query(default=""), limit: int = Query(default=50), offset: int = Query(default=0)):
    inmates = _get_inmates()
    if jail:
        inmates = [i for i in inmates if i.get("jail") == jail]

    if not q.strip():
        page = inmates[offset:offset + limit]
        return {"results": page, "total": len(inmates), "offset": offset, "has_more": offset + limit < len(inmates)}

    scored = []
    query = q.lower()
    for inmate in inmates:
        last = inmate.get("last_name", "")
        first = inmate.get("first_name", "")
        middle = inmate.get("middle_name", "")
        full_name = f"{last} {first} {middle}".strip()
        full_comma = f"{last}, {first} {middle}".strip()

        score = max(
            fuzz.WRatio(query, full_name.lower()),
            fuzz.WRatio(query, full_comma.lower()),
            fuzz.partial_ratio(query, full_name.lower()),
            fuzz.partial_ratio(query, f"{first} {last}".lower()),
        )
        if score > 55:
            scored.append((score, inmate, full_name))

    scored.sort(key=lambda x: x[0], reverse=True)
    page = scored[offset:offset + limit]
    results = [
        {**item, "_score": score, "_full_name": name}
        for score, item, name in page
    ]
    return {"results": results, "total": len(scored), "offset": offset, "has_more": offset + limit < len(scored)}


@app.get("/api/stats")
def stats():
    inmates = _get_inmates()
    jails: dict[str, int] = {}
    for i in inmates:
        jail = i.get("jail", "Unknown")
        jails[jail] = jails.get(jail, 0) + 1
    return {
        "total": len(inmates),
        "by_jail": jails,
        "last_updated": _last_updated,
        "sync_status": _sync_status,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASHBOARD_HTML


_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jail Roster Search</title>
<style>
  :root {
    --bg: #0f172a;
    --surface: #1e293b;
    --surface-hover: #334155;
    --border: #334155;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --accent: #38bdf8;
    --accent-dim: #0c4a6e;
    --green: #4ade80;
    --amber: #fbbf24;
    --red: #f87171;
    --radius: 8px;
    --font: 'Inter', system-ui, -apple-system, sans-serif;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }

  .container {
    max-width: 1100px;
    margin: 0 auto;
    padding: 24px 16px;
  }

  header {
    text-align: center;
    padding: 32px 0 24px;
  }

  header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: -0.025em;
    margin-bottom: 4px;
  }

  header p {
    color: var(--text-muted);
    font-size: 0.875rem;
  }

  .stats-bar {
    display: flex;
    gap: 12px;
    justify-content: center;
    flex-wrap: wrap;
    margin-bottom: 24px;
  }

  .stat-chip {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 0.8rem;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .stat-chip {
    cursor: default;
  }

  .stat-chip .count {
    color: var(--accent);
    font-weight: 600;
    font-size: 0.9rem;
  }

  .search-wrap {
    position: relative;
    max-width: 600px;
    margin: 0 auto 24px;
  }

  .search-wrap svg {
    position: absolute;
    left: 16px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    pointer-events: none;
  }

  #search {
    width: 100%;
    padding: 14px 16px 14px 48px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-size: 1rem;
    font-family: var(--font);
    outline: none;
    transition: border-color 0.15s;
  }

  #search:focus {
    border-color: var(--accent);
  }

  #search::placeholder {
    color: var(--text-muted);
  }

  .results-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    font-size: 0.8rem;
    color: var(--text-muted);
    padding: 0 4px;
  }

  .results-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    background: var(--surface);
    border-radius: var(--radius);
    overflow: hidden;
    border: 1px solid var(--border);
  }

  .results-table thead th {
    text-align: left;
    padding: 10px 14px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    cursor: pointer;
    user-select: none;
  }

  .results-table thead th:hover {
    color: var(--text);
  }

  .results-table tbody tr {
    transition: background 0.1s;
  }

  .results-table tbody tr:hover {
    background: var(--surface-hover);
  }

  .results-table td {
    padding: 10px 14px;
    font-size: 0.875rem;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }

  .results-table tbody tr:last-child td {
    border-bottom: none;
  }

  .name-cell {
    font-weight: 600;
    white-space: nowrap;
  }

  .stale-row td { opacity: 0.65; }
  .stale-badge {
    display: inline-block;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.65rem;
    font-weight: 600;
    background: #422006;
    color: #fbbf24;
    margin-left: 6px;
    vertical-align: middle;
  }

  .jail-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    white-space: nowrap;
  }

  .jail-missoula { background: #164e63; color: #67e8f9; }
  .jail-flathead { background: #3b0764; color: #d8b4fe; }
  .jail-ravalli  { background: #14532d; color: #86efac; }
  .jail-default  { background: #1e293b; color: #94a3b8; }

  .charges-cell {
    max-width: 350px;
    font-size: 0.8rem;
    color: var(--text-muted);
    line-height: 1.4;
  }

  .match-score {
    display: inline-block;
    width: 36px;
    text-align: center;
    padding: 2px 0;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
  }

  .score-high   { background: #14532d; color: #4ade80; }
  .score-medium { background: #422006; color: #fbbf24; }
  .score-low    { background: #450a0a; color: #f87171; }

  .empty-state {
    text-align: center;
    padding: 48px 16px;
    color: var(--text-muted);
  }

  .empty-state p { font-size: 0.9rem; }

  @media (max-width: 700px) {
    .container { padding: 12px 8px; }

    header { padding: 16px 0 12px; }
    header h1 { font-size: 1.3rem; }
    header p { font-size: 0.8rem; }

    .stats-bar { gap: 6px; margin-bottom: 16px; }
    .stat-chip {
      padding: 8px 12px;
      font-size: 0.7rem;
      border-radius: 16px;
    }
    .stat-chip .count { font-size: 0.8rem; }

    .search-wrap { margin-bottom: 16px; }
    #search { padding: 12px 12px 12px 40px; font-size: 0.9rem; }
    .search-wrap svg { left: 12px; width: 18px; height: 18px; }

    .status-panel { margin-bottom: 16px; }

    .results-table { font-size: 0.8rem; }
    .results-table td, .results-table th { padding: 8px 10px; }
    .charges-cell, .bond-cell, .charges-head, .bond-head { display: none; }

    .name-cell { white-space: normal; word-break: break-word; }

    .results-meta { font-size: 0.75rem; }
  }

  .card-list {
    display: none;
    flex-direction: column;
    gap: 8px;
  }
  .inmate-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 10px 12px;
  }
  .inmate-card.stale-row { opacity: 0.65; }
  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 8px;
    margin-bottom: 4px;
  }
  .card-name {
    font-weight: 600;
    font-size: 0.85rem;
    line-height: 1.3;
  }
  .card-details {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 12px;
    font-size: 0.75rem;
    color: var(--text-muted);
  }
  .card-score {
    margin-right: 4px;
  }

  @media (max-width: 480px) {
    .stats-bar {
      gap: 5px;
      justify-content: flex-start;
    }
    .stat-chip {
      padding: 6px 10px;
      font-size: 0.65rem;
    }
    .stat-chip .count { font-size: 0.75rem; }

    .results-table { display: none; }
    .card-list { display: flex; }

    .status-row { padding: 6px 10px; font-size: 0.75rem; }
    .status-county { min-width: 80px; }
  }

  .loading { opacity: 0.5; pointer-events: none; }

  .load-more {
    display: block;
    width: 100%;
    max-width: 400px;
    margin: 16px auto;
    padding: 10px 24px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--accent);
    font-family: var(--font);
    font-size: 0.875rem;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
  }

  .load-more:hover {
    background: var(--surface-hover);
    border-color: var(--accent);
  }

  .status-panel {
    max-width: 600px;
    margin: 0 auto 24px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .status-toggle {
    width: 100%;
    padding: 10px 16px;
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 0.8rem;
    font-family: var(--font);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .status-toggle:hover { color: var(--text); }

  .status-toggle .arrow {
    transition: transform 0.2s;
    font-size: 0.7rem;
  }

  .status-toggle.open .arrow { transform: rotate(90deg); }

  .status-body {
    display: none;
    border-top: 1px solid var(--border);
  }

  .status-body.open { display: block; }

  .status-row {
    display: flex;
    align-items: center;
    padding: 8px 16px;
    font-size: 0.8rem;
    border-bottom: 1px solid var(--border);
    gap: 10px;
  }

  .status-row:last-child { border-bottom: none; }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .status-dot.ok { background: var(--green); }
  .status-dot.warning { background: var(--amber); }
  .status-dot.error { background: var(--red); }
  .status-dot.stale { background: var(--amber); }

  .status-county { font-weight: 500; min-width: 120px; }
  .status-county a {
    color: var(--accent);
    text-decoration: none;
  }
  .status-county a:hover { text-decoration: underline; }
  .status-count { color: var(--text-muted); min-width: 30px; text-align: right; }
  .status-time { color: var(--text-muted); flex: 1; text-align: right; font-size: 0.75rem; }
  .status-error { color: var(--red); font-size: 0.75rem; flex: 1; text-align: right; }

  .status-summary {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-summary .dot-group {
    display: flex;
    gap: 3px;
  }

  .disclaimer {
    max-width: 600px;
    margin: 0 auto 20px;
    padding: 12px 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 0.75rem;
    color: var(--text-muted);
    line-height: 1.5;
  }

  .disclaimer summary {
    cursor: pointer;
    font-weight: 600;
    font-size: 0.8rem;
    color: var(--text-muted);
  }

  .disclaimer summary:hover { color: var(--text); }

  .disclaimer p { margin-top: 8px; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Jail Roster Search</h1>
    <p>Montana Detention Facilities</p>
  </header>

  <details class="disclaimer">
    <summary>Disclaimer</summary>
    <p>This tool aggregates publicly available jail roster data from county sheriff websites across Montana. It is not an official government resource. Data may be incomplete, delayed, or inaccurate. Always verify information through official county sources before relying on it.</p>
    <p>Some counties (currently Glacier County) are excluded because their websites use bot protection (Cloudflare/SiteGround) that blocks automated access.</p>
  </details>

  <div class="stats-bar" id="stats-bar"></div>

  <div class="status-panel" id="status-panel" style="display:none">
    <button class="status-toggle" onclick="toggleStatus()">
      <span class="status-summary" id="status-summary"></span>
      <span class="arrow">&#9654;</span>
    </button>
    <div class="status-body" id="status-body"></div>
  </div>

  <div class="search-wrap">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
    </svg>
    <input type="text" id="search" placeholder="Search by name..." autocomplete="off" autofocus>
  </div>

  <div class="results-meta" id="results-meta"></div>

  <div id="results"></div>
</div>

<script>
const JAIL_CLASSES = {
  'Missoula County': 'jail-missoula',
  'Flathead County': 'jail-flathead',
  'Ravalli County': 'jail-ravalli',
};

let debounceTimer;
let currentResults = [];
let currentTotal = 0;
let currentOffset = 0;
let currentQuery = '';
let hasMore = false;
let staleJails = new Set();
const PAGE_SIZE = 100;

const searchInput = document.getElementById('search');
const resultsDiv = document.getElementById('results');
const metaDiv = document.getElementById('results-meta');

searchInput.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => doSearch(false), 200);
});

async function doSearch(append) {
  const q = searchInput.value.trim();

  if (!append || q !== currentQuery) {
    currentResults = [];
    currentOffset = 0;
    currentQuery = q;
  }

  resultsDiv.classList.add('loading');

  try {
    const resp = await fetch('/api/search?q=' + encodeURIComponent(q) + '&limit=' + PAGE_SIZE + '&offset=' + currentOffset);
    const data = await resp.json();
    currentResults = currentResults.concat(data.results);
    currentTotal = data.total;
    hasMore = data.has_more;
    currentOffset += data.results.length;
    renderResults(currentResults, currentTotal, q);
  } catch (e) {
    resultsDiv.innerHTML = '<div class="empty-state"><p>Error loading results</p></div>';
  }

  resultsDiv.classList.remove('loading');
}

function loadMore() {
  doSearch(true);
}

function renderResults(results, total, query) {
  if (!results.length) {
    metaDiv.textContent = '';
    resultsDiv.innerHTML = query
      ? '<div class="empty-state"><p>No matches found</p></div>'
      : '<div class="empty-state"><p>Loading...</p></div>';
    return;
  }

  const isSearch = query.length > 0;
  metaDiv.innerHTML = isSearch
    ? '<span>Showing ' + results.length + ' of ' + total + ' matches</span>'
    : '<span>Showing ' + results.length + ' of ' + total + ' inmates</span>';

  let html = '<table class="results-table"><thead><tr>';
  if (isSearch) html += '<th>Match</th>';
  html += '<th>Name</th><th>Jail</th><th class="booking-date-head">Booking Date</th><th class="charges-head">Charges</th><th class="bond-head">Bond</th>';
  html += '</tr></thead><tbody>';

  for (const r of results) {
    const name = [r.last_name, [r.first_name, r.middle_name].filter(Boolean).join(' ')].filter(Boolean).join(', ');
    const jailClass = JAIL_CLASSES[r.jail] || 'jail-default';
    const jailShort = (r.jail || '').replace(' County', '');
    const isStale = staleJails.has(r.jail);

    html += '<tr' + (isStale ? ' class="stale-row"' : '') + '>';
    if (isSearch) {
      const score = r._score || 0;
      const cls = score >= 80 ? 'score-high' : score >= 60 ? 'score-medium' : 'score-low';
      html += '<td><span class="match-score ' + cls + '">' + Math.round(score) + '</span></td>';
    }
    html += '<td class="name-cell">' + esc(name) + '</td>';
    html += '<td><span class="jail-badge ' + jailClass + '">' + esc(jailShort) + '</span>' + (isStale ? '<span class="stale-badge">STALE</span>' : '') + '</td>';
    html += '<td class="booking-date-cell">' + esc(r.booking_date || '') + '</td>';
    html += '<td class="charges-cell">' + esc(r.charges || '') + '</td>';
    html += '<td class="bond-cell">' + esc(r.bond || '') + '</td>';
    html += '</tr>';
  }

  html += '</tbody></table>';

  let cards = '<div class="card-list">';
  for (const r of results) {
    const name = [r.last_name, [r.first_name, r.middle_name].filter(Boolean).join(' ')].filter(Boolean).join(', ');
    const jailClass = JAIL_CLASSES[r.jail] || 'jail-default';
    const jailShort = (r.jail || '').replace(' County', '');
    const isStale = staleJails.has(r.jail);

    cards += '<div class="inmate-card' + (isStale ? ' stale-row' : '') + '">';
    cards += '<div class="card-top">';
    cards += '<span class="card-name">';
    if (isSearch && r._score) {
      const score = r._score;
      const cls = score >= 80 ? 'score-high' : score >= 60 ? 'score-medium' : 'score-low';
      cards += '<span class="match-score card-score ' + cls + '">' + Math.round(score) + '</span>';
    }
    cards += esc(name) + '</span>';
    cards += '<span class="jail-badge ' + jailClass + '">' + esc(jailShort) + '</span>';
    if (isStale) cards += '<span class="stale-badge">STALE</span>';
    cards += '</div>';
    cards += '<div class="card-details">';
    if (r.booking_date) cards += '<span>' + esc(r.booking_date) + '</span>';
    if (r.charges) cards += '<span>' + esc(r.charges) + '</span>';
    if (r.bond) cards += '<span>' + esc(r.bond) + '</span>';
    cards += '</div>';
    cards += '</div>';
  }
  cards += '</div>';

  let loadMoreBtn = '';
  if (hasMore) {
    loadMoreBtn = '<button class="load-more" onclick="loadMore()">Load more (' + (total - results.length) + ' remaining)</button>';
  }

  resultsDiv.innerHTML = html + cards + loadMoreBtn;
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function toggleStatus() {
  const btn = document.querySelector('.status-toggle');
  const body = document.getElementById('status-body');
  btn.classList.toggle('open');
  body.classList.toggle('open');
}

function timeAgo(utcStr) {
  if (!utcStr) return 'never';
  const then = new Date(utcStr.replace(' UTC', 'Z'));
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  return Math.floor(hrs / 24) + 'd ago';
}

function renderSyncStatus(syncStatus) {
  if (!syncStatus || !syncStatus.length) return;

  staleJails = new Set(
    syncStatus.filter(s => s.status === 'error').map(s => s.county + ' County')
  );

  const panel = document.getElementById('status-panel');
  panel.style.display = '';

  const okCount = syncStatus.filter(s => s.status === 'ok').length;
  const warnCount = syncStatus.filter(s => s.status === 'warning').length;
  const errCount = syncStatus.filter(s => s.status === 'error').length;
  const total = syncStatus.length;

  const summary = document.getElementById('status-summary');
  let dots = '<span class="dot-group">';
  syncStatus.forEach(s => {
    dots += '<span class="status-dot ' + s.status + '" title="' + esc(s.county) + '"></span>';
  });
  dots += '</span>';

  const issues = [];
  if (errCount > 0) issues.push(errCount + ' failed');
  if (warnCount > 0) issues.push(warnCount + ' empty');
  if (issues.length > 0) {
    summary.innerHTML = dots + ' ' + okCount + '/' + total + ' sources synced — ' + issues.join(', ');
  } else {
    summary.innerHTML = dots + ' All ' + total + ' sources synced';
  }

  const body = document.getElementById('status-body');
  let html = '';
  for (const s of syncStatus) {
    html += '<div class="status-row">';
    html += '<span class="status-dot ' + s.status + '"></span>';
    if (s.url || s.source_url) {
      html += '<span class="status-county"><a href="' + esc(s.url || s.source_url) + '" target="_blank">' + esc(s.county) + '</a></span>';
    } else {
      html += '<span class="status-county">' + esc(s.county) + '</span>';
    }
    html += '<span class="status-count">' + esc(s.count || s.inmate_count || '0') + '</span>';
    if (s.status === 'error' || s.status === 'warning') {
      html += '<span class="status-error">' + esc(s.error || 'Unknown error') + '</span>';
    } else {
      html += '<span class="status-time">' + timeAgo(s.last_success || s.last_sync) + '</span>';
    }
    html += '</div>';
  }
  body.innerHTML = html;
}

async function loadStats() {
  try {
    const resp = await fetch('/api/stats');
    const data = await resp.json();
    const bar = document.getElementById('stats-bar');
    let html = '<div class="stat-chip">Total <span class="count">' + data.total + '</span></div>';
    for (const [jail, count] of Object.entries(data.by_jail)) {
      const short = jail.replace(' County', '');
      html += '<div class="stat-chip">' + esc(short) + ' <span class="count">' + count + '</span></div>';
    }
    bar.innerHTML = html;
    renderSyncStatus(data.sync_status);
  } catch (e) {}
}

loadStats();
doSearch();
</script>
</body>
</html>
"""
