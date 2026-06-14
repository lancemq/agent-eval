"""TraceViewer Web UI - interactive dashboard for trace exploration.

Provides a self-contained web server with a modern SPA frontend
for browsing, analyzing, and managing trace records and datasets.

Usage:
    from agent_eval.trace.viewer import TraceViewer

    viewer = TraceViewer(store=TraceStore(path="./traces"))
    viewer.run(host="0.0.0.0", port=8765)
    # Open http://localhost:8765 in browser

CLI:
    agent-eval trace viewer --port 8765
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from agent_eval.trace.store import TraceStore
from agent_eval.trace.analyzer import TraceAnalyzer
from agent_eval.trace.task_generator import TaskGenerator


class TraceViewer:
    """Web-based trace exploration dashboard.

    Features:
    - Overview dashboard with stats and charts
    - Trace list with filtering by type, agent, success, quality
    - Trace detail view with trajectory timeline
    - Dataset builder with golden set selection
    - Analysis report with intent clusters and error patterns
    """

    def __init__(self, store: Optional[TraceStore] = None, port: int = 8765):
        self.store = store or TraceStore()
        self.port = port
        self._server: Optional[ThreadingHTTPServer] = None

    def run(self, host: str = "localhost", port: int = 0, open_browser: bool = True) -> None:
        """Start the web server."""
        actual_port = port or self.port

        viewer_self = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def _json(self, data: Any, status: int = 200) -> None:
                body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _html(self, content: str) -> None:
                body = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                qs = parse_qs(parsed.query)

                if path == "/" or path == "/index.html":
                    self._html(viewer_self._render_app())
                elif path == "/api/stats":
                    self._json(viewer_self.store.stats())
                elif path == "/api/traces":
                    filters: Dict[str, Any] = {}
                    for key in ("trace_type", "agent_name", "source", "success"):
                        if key in qs:
                            val = qs[key][0]
                            if key == "success":
                                val = val.lower() == "true"
                            filters[key] = val
                    if "min_quality" in qs:
                        filters["min_quality"] = float(qs["min_quality"][0])
                    if "limit" in qs:
                        filters["limit"] = int(qs["limit"][0])
                    traces = viewer_self.store.query(filters)
                    self._json([
                        {
                            "trace_id": t.trace_id,
                            "timestamp": t.timestamp,
                            "trace_type": t.trace_type,
                            "agent_name": t.agent_name,
                            "input": t.input[:200],
                            "output": t.output[:200],
                            "success": t.success,
                            "quality_score": round(t.quality_score, 3),
                            "duration_ms": t.duration_ms,
                            "num_tool_calls": t.num_tool_calls,
                            "num_turns": t.num_turns,
                            "tags": t.tags,
                        }
                        for t in traces
                    ])
                elif path.startswith("/api/trace/"):
                    trace_id = path.split("/")[-1]
                    record = viewer_self.store.load(trace_id)
                    if record:
                        self._json(record.to_dict())
                    else:
                        self._json({"error": "not found"}, 404)
                elif path == "/api/analysis":
                    traces = viewer_self.store.query({})
                    analyzer = TraceAnalyzer()
                    report = analyzer.analyze(traces)
                    self._json(report.to_dict())
                elif path == "/api/build-dataset":
                    self._json({"error": "Use POST"}, 405)
                else:
                    self._json({"error": "not found"}, 404)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    data = {}

                if path == "/api/build-dataset":
                    traces = viewer_self.store.query({})
                    if data.get("min_quality"):
                        traces = [t for t in traces if t.quality_score >= data["min_quality"]]
                    if data.get("strategy"):
                        analyzer = TraceAnalyzer()
                        n = data.get("max_tasks", 50)
                        traces = analyzer.select_golden_set(traces, n=n, strategy=data["strategy"])
                    generator = TaskGenerator()
                    tasks = generator.generate_batch(traces)
                    self._json({
                        "total_tasks": len(tasks),
                        "tasks": [t.to_dict() for t in tasks[:20]],
                        "stats": {
                            "by_type": dict(
                                sorted(
                                    {t.task_type for t in tasks}
                                    , key=lambda x: -sum(1 for tt in tasks if tt.task_type == x)
                                )
                            ),
                        },
                    })
                elif path == "/api/delete-trace":
                    trace_id = data.get("trace_id", "")
                    ok = viewer_self.store.delete(trace_id)
                    self._json({"deleted": ok})
                else:
                    self._json({"error": "not found"}, 404)

        self._server = ThreadingHTTPServer((host, actual_port), Handler)
        url = f"http://{host}:{actual_port}"
        print(f"TraceViewer running at {url}")
        if open_browser:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            self._server.shutdown()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()

    def _render_app(self) -> str:
        """Render the full SPA frontend."""
        return _HTML_TEMPLATE


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentEval TraceViewer</title>
<style>
:root {
  --bg: #0f1117; --card: #1a1d27; --border: #2a2d3a;
  --text: #e4e6eb; --text-dim: #8b8fa3; --accent: #7c5cfc;
  --accent2: #00d4aa; --warn: #ffa116; --danger: #ff5757;
  --radius: 12px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); }
.app { display: flex; height: 100vh; }
.sidebar { width: 240px; background: var(--card); border-right: 1px solid var(--border); padding: 20px 0; flex-shrink: 0; }
.sidebar h1 { font-size: 18px; padding: 0 20px 20px; border-bottom: 1px solid var(--border); color: var(--accent); }
.nav-item { padding: 12px 20px; cursor: pointer; transition: all .15s; display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--text-dim); }
.nav-item:hover { background: rgba(124,92,252,.1); color: var(--text); }
.nav-item.active { background: rgba(124,92,252,.15); color: var(--accent); border-right: 3px solid var(--accent); }
.nav-icon { width: 20px; text-align: center; }
.main { flex: 1; overflow-y: auto; padding: 24px 32px; }
.page { display: none; } .page.active { display: block; }
.page-title { font-size: 24px; margin-bottom: 20px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
.stat-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.stat-card .label { color: var(--text-dim); font-size: 13px; margin-bottom: 8px; }
.stat-card .value { font-size: 28px; font-weight: 700; }
.stat-card .sub { color: var(--text-dim); font-size: 12px; margin-top: 4px; }
.chart-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
.chart-title { font-size: 16px; margin-bottom: 16px; }
.bar-chart { display: flex; flex-direction: column; gap: 8px; }
.bar-row { display: flex; align-items: center; gap: 12px; }
.bar-label { width: 140px; font-size: 13px; color: var(--text-dim); text-align: right; }
.bar-track { flex: 1; height: 24px; background: rgba(255,255,255,.05); border-radius: 6px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 6px; transition: width .3s; display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; font-size: 12px; color: white; min-width: 2px; }
.bar-fill.purple { background: linear-gradient(90deg, #7c5cfc, #9d7fff); }
.bar-fill.teal { background: linear-gradient(90deg, #00d4aa, #00e8bb); }
.bar-fill.orange { background: linear-gradient(90deg, #ffa116, #ffbc42); }
.bar-fill.red { background: linear-gradient(90deg, #ff5757, #ff7878); }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; border-bottom: 2px solid var(--border); font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .5px; }
.table td { padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
.table tr:hover { background: rgba(255,255,255,.02); cursor: pointer; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
.badge.success { background: rgba(0,212,170,.15); color: var(--accent2); }
.badge.fail { background: rgba(255,87,87,.15); color: var(--danger); }
.badge.type { background: rgba(124,92,252,.15); color: var(--accent); }
.filters { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-select, .filter-input { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; color: var(--text); font-size: 13px; }
.btn { background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600; transition: opacity .15s; }
.btn:hover { opacity: .85; }
.btn.secondary { background: var(--card); border: 1px solid var(--border); }
.detail-panel { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px; margin-bottom: 16px; }
.detail-section { margin-bottom: 20px; }
.detail-section h3 { font-size: 14px; color: var(--text-dim); margin-bottom: 8px; text-transform: uppercase; letter-spacing: .5px; }
.msg-bubble { padding: 10px 14px; border-radius: 10px; margin-bottom: 6px; max-width: 80%; font-size: 14px; }
.msg-bubble.user { background: rgba(124,92,252,.1); border-left: 3px solid var(--accent); }
.msg-bubble.assistant { background: rgba(0,212,170,.08); border-left: 3px solid var(--accent2); }
.msg-bubble .role { font-size: 11px; color: var(--text-dim); margin-bottom: 4px; }
.timeline-step { display: flex; gap: 12px; padding: 12px; border-radius: 8px; background: rgba(255,255,255,.02); margin-bottom: 8px; }
.step-num { width: 28px; height: 28px; border-radius: 50%; background: var(--accent); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0; }
.step-content { flex: 1; }
.step-action { font-size: 13px; color: var(--accent2); margin-bottom: 4px; }
.step-result { font-size: 12px; color: var(--text-dim); }
.q-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.q-badge.excellent { background: rgba(0,212,170,.2); color: var(--accent2); }
.q-badge.good { background: rgba(124,92,252,.15); color: var(--accent); }
.q-badge.fair { background: rgba(255,161,22,.15); color: var(--warn); }
.q-badge.poor { background: rgba(255,87,87,.15); color: var(--danger); }
.toast { position: fixed; bottom: 24px; right: 24px; background: var(--accent); color: white; padding: 12px 20px; border-radius: 8px; z-index: 1000; opacity: 0; transition: opacity .3s; }
.toast.show { opacity: 1; }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="app">
  <div class="sidebar">
    <h1>TraceViewer</h1>
    <div class="nav-item active" onclick="showPage('overview')"><span class="nav-icon">📊</span> Overview</div>
    <div class="nav-item" onclick="showPage('traces')"><span class="nav-icon">📋</span> Traces</div>
    <div class="nav-item" onclick="showPage('analysis')"><span class="nav-icon">🔍</span> Analysis</div>
    <div class="nav-item" onclick="showPage('dataset')"><span class="nav-icon">📦</span> Dataset Builder</div>
  </div>
  <div class="main">

    <!-- Overview Page -->
    <div class="page active" id="page-overview">
      <div class="page-title">Overview</div>
      <div class="stat-grid" id="stat-grid"><div class="stat-card"><div class="value"><span class="spinner"></span></div></div></div>
      <div class="chart-card">
        <div class="chart-title">Quality Distribution</div>
        <div class="bar-chart" id="quality-chart"></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
        <div class="chart-card">
          <div class="chart-title">Trace Types</div>
          <div class="bar-chart" id="type-chart"></div>
        </div>
        <div class="chart-card">
          <div class="chart-title">Top Tools</div>
          <div class="bar-chart" id="tool-chart"></div>
        </div>
      </div>
    </div>

    <!-- Traces Page -->
    <div class="page" id="page-traces">
      <div class="page-title">Traces</div>
      <div class="filters">
        <select class="filter-select" id="f-type" onchange="loadTraces()">
          <option value="">All Types</option>
          <option value="single_turn">Single Turn</option>
          <option value="multi_turn">Multi Turn</option>
          <option value="tool_use">Tool Use</option>
          <option value="agentic">Agentic</option>
        </select>
        <select class="filter-select" id="f-success" onchange="loadTraces()">
          <option value="">All Status</option>
          <option value="true">Success Only</option>
          <option value="false">Failed Only</option>
        </select>
        <input class="filter-input" id="f-minq" type="number" placeholder="Min Quality" min="0" max="1" step="0.1" oninput="loadTraces()" style="width:130px;">
        <button class="btn" onclick="loadTraces()">Refresh</button>
      </div>
      <div class="chart-card" style="padding:0;overflow:hidden;">
        <table class="table">
          <thead><tr>
            <th>Trace ID</th><th>Type</th><th>Agent</th><th>Input</th>
            <th>Quality</th><th>Status</th><th>Tools</th><th>Duration</th>
          </tr></thead>
          <tbody id="trace-tbody"></tbody>
        </table>
      </div>
    </div>

    <!-- Trace Detail -->
    <div class="page" id="page-detail">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
        <button class="btn secondary" onclick="showPage('traces')">← Back</button>
        <div class="page-title" id="detail-title">Trace Detail</div>
      </div>
      <div id="detail-content"></div>
    </div>

    <!-- Analysis Page -->
    <div class="page" id="page-analysis">
      <div class="page-title">Analysis Report</div>
      <div class="stat-grid" id="analysis-stats"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
        <div class="chart-card"><div class="chart-title">Intent Clusters</div><div class="bar-chart" id="intent-chart"></div></div>
        <div class="chart-card"><div class="chart-title">Error Patterns</div><div id="error-patterns"></div></div>
      </div>
    </div>

    <!-- Dataset Builder -->
    <div class="page" id="page-dataset">
      <div class="page-title">Dataset Builder</div>
      <div class="chart-card">
        <div class="chart-title">Build Configuration</div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
          <div><label style="font-size:12px;color:var(--text-dim);display:block;margin-bottom:4px;">Strategy</label>
            <select class="filter-select" id="d-strategy">
              <option value="diverse">Diverse (max coverage)</option>
              <option value="hard">Hard (complex cases)</option>
              <option value="failure">Failure (regression)</option>
              <option value="balanced">Balanced (by type)</option>
            </select></div>
          <div><label style="font-size:12px;color:var(--text-dim);display:block;margin-bottom:4px;">Min Quality</label>
            <input class="filter-input" id="d-minq" type="number" value="0.3" min="0" max="1" step="0.1" style="width:100px;"></div>
          <div><label style="font-size:12px;color:var(--text-dim);display:block;margin-bottom:4px;">Max Tasks</label>
            <input class="filter-input" id="d-max" type="number" value="50" min="1" style="width:100px;"></div>
          <button class="btn" onclick="buildDataset()">Build Dataset</button>
        </div>
      </div>
      <div id="dataset-result"></div>
    </div>

  </div>
</div>
<div class="toast" id="toast"></div>

<script>
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const colors = ['purple','teal','orange','red'];

function showPage(name) {
  $$('.page').forEach(p => p.classList.remove('active'));
  $$('.nav-item').forEach(n => n.classList.remove('active'));
  $('#page-' + name).classList.add('active');
  if (name === 'overview') loadOverview();
  if (name === 'traces') loadTraces();
  if (name === 'analysis') loadAnalysis();
  // Mark nav active
  $$('.nav-item').forEach(n => {
    if (n.textContent.trim().toLowerCase().includes(name.toLowerCase()) || 
        (name === 'overview' && n.textContent.includes('Overview')) ||
        (name === 'traces' && n.textContent.includes('Traces')) ||
        (name === 'analysis' && n.textContent.includes('Analysis')) ||
        (name === 'dataset' && n.textContent.includes('Dataset')))
      n.classList.add('active');
  });
}

function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}

async function loadOverview() {
  const stats = await api('/api/stats');
  if (stats.total === undefined || stats.total === 0) {
    $('#stat-grid').innerHTML = '<div class="stat-card" style="text-align:center;color:var(--text-dim);grid-column:1/-1;">No traces found. Import traces first: <code>agent-eval trace import --dir ./logs</code></div>';
    return;
  }
  $('#stat-grid').innerHTML = [
    {label:'Total Traces', value:stats.total, sub:''},
    {label:'Success Rate', value:(stats.success_rate*100).toFixed(1)+'%', sub:''},
    {label:'Avg Quality', value:stats.avg_quality.toFixed(3), sub:''},
    {label:'Avg Duration', value:stats.avg_duration_ms.toFixed(0)+'ms', sub:''},
    {label:'Avg Tool Calls', value:stats.avg_tool_calls.toFixed(1), sub:'per trace'},
    {label:'Avg Turns', value:stats.avg_turns.toFixed(1), sub:'per trace'},
  ].map(s => `<div class="stat-card"><div class="label">${s.label}</div><div class="value">${s.value}</div><div class="sub">${s.sub}</div></div>`).join('');

  // Type chart
  const types = stats.by_type || {};
  const maxT = Math.max(...Object.values(types), 1);
  $('#type-chart').innerHTML = Object.entries(types).map(([k,v]) =>
    `<div class="bar-row"><div class="bar-label">${k}</div><div class="bar-track"><div class="bar-fill purple" style="width:${v/maxT*100}%;">${v}</div></div></div>`).join('');

  // Tool usage (from analysis)
  const analysis = await api('/api/analysis');
  const tools = analysis.tool_usage || {};
  const maxTool = Math.max(...Object.values(tools), 1);
  $('#tool-chart').innerHTML = Object.entries(tools).slice(0,8).map(([k,v]) =>
    `<div class="bar-row"><div class="bar-label">${k}</div><div class="bar-track"><div class="bar-fill teal" style="width:${v/maxTool*100}%;">${v}</div></div></div>`).join('') || '<div style="color:var(--text-dim);text-align:center;padding:20px;">No tool calls recorded</div>';

  // Quality distribution
  const qd = analysis.quality_distribution || {};
  const maxQ = Math.max(...Object.values(qd), 1);
  const qColors = {excellent:'teal', good:'purple', fair:'orange', poor:'red'};
  $('#quality-chart').innerHTML = Object.entries(qd).map(([k,v]) =>
    `<div class="bar-row"><div class="bar-label" style="text-transform:capitalize;">${k}</div><div class="bar-track"><div class="bar-fill ${qColors[k]||'purple'}" style="width:${v/maxQ*100}%;">${v}</div></div></div>`).join('');
}

async function loadTraces() {
  const params = new URLSearchParams();
  const t = $('#f-type').value; if (t) params.set('trace_type', t);
  const s = $('#f-success').value; if (s) params.set('success', s);
  const q = $('#f-minq').value; if (q) params.set('min_quality', q);
  params.set('limit', '200');
  const traces = await api('/api/traces?' + params);
  if (!traces.length) {
    $('#trace-tbody').innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-dim);padding:40px;">No traces match filters</td></tr>';
    return;
  }
  $('#trace-tbody').innerHTML = traces.map(t => {
    const qcls = t.quality_score>=0.8?'excellent':t.quality_score>=0.6?'good':t.quality_score>=0.4?'fair':'poor';
    return `<tr onclick="showDetail('${t.trace_id}')">
      <td style="font-family:monospace;font-size:12px;">${t.trace_id.slice(0,12)}</td>
      <td><span class="badge type">${t.trace_type}</span></td>
      <td>${t.agent_name}</td>
      <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(t.input)}</td>
      <td><span class="q-badge ${qcls}">${t.quality_score.toFixed(2)}</span></td>
      <td><span class="badge ${t.success?'success':'fail'}">${t.success?'PASS':'FAIL'}</span></td>
      <td>${t.num_tool_calls}</td>
      <td>${t.duration_ms}ms</td>
    </tr>`;
  }).join('');
}

async function showDetail(traceId) {
  showPage('detail');
  const t = await api('/api/trace/' + traceId);
  if (t.error) { $('#detail-content').innerHTML = '<p>Trace not found</p>'; return; }
  $('#detail-title').textContent = 'Trace ' + t.trace_id.slice(0,12);

  let html = '<div class="detail-panel">';
  // Metadata
  html += '<div class="detail-section"><h3>Metadata</h3><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;">';
  html += `<span>Agent: <b>${t.agent_name}</b></span>`;
  html += `<span>Type: <b>${t.trace_type}</b></span>`;
  html += `<span>Success: <b>${t.success}</b></span>`;
  html += `<span>Quality: <b>${t.quality_score.toFixed(3)}</b></span>`;
  html += `<span>Duration: <b>${t.duration_ms}ms</b></span>`;
  html += `<span>Source: <b>${t.source}</b></span>`;
  html += `<span>Tool Calls: <b>${(t.tool_calls||[]).length}</b></span>`;
  html += `<span>Steps: <b>${(t.trajectory||[]).length}</b></span>`;
  html += '</div></div>';

  // Conversation
  if (t.messages && t.messages.length) {
    html += '<div class="detail-section"><h3>Conversation</h3>';
    t.messages.forEach(m => {
      html += `<div class="msg-bubble ${m.role}"><div class="role">${m.role}</div>${esc(m.content)}</div>`;
    });
    html += '</div>';
  }

  // Input/Output
  if (t.input) {
    html += `<div class="detail-section"><h3>Input</h3><div style="background:rgba(255,255,255,.03);padding:12px;border-radius:8px;font-size:13px;">${esc(t.input)}</div></div>`;
  }
  if (t.output) {
    html += `<div class="detail-section"><h3>Output</h3><div style="background:rgba(0,212,170,.05);padding:12px;border-radius:8px;font-size:13px;">${esc(t.output)}</div></div>`;
  }

  // Trajectory
  if (t.trajectory && t.trajectory.length) {
    html += '<div class="detail-section"><h3>Trajectory</h3>';
    t.trajectory.forEach((s, i) => {
      const actionStr = s.action_type || s.action?.type || 'step';
      const detail = s.action?.tool ? `Tool: ${s.action.tool}` : JSON.stringify(s.action || {}).slice(0,100);
      const resultStr = s.result ? (typeof s.result === 'string' ? s.result.slice(0,200) : JSON.stringify(s.result).slice(0,200)) : '';
      html += `<div class="timeline-step"><div class="step-num">${i+1}</div><div class="step-content"><div class="step-action">${actionStr} — ${detail}</div><div class="step-result">${esc(resultStr)}</div>${s.error?'<div style="color:var(--danger);font-size:12px;">Error: '+esc(s.error)+'</div>':''}</div></div>`;
    });
    html += '</div>';
  }

  // Tool calls
  if (t.tool_calls && t.tool_calls.length) {
    html += '<div class="detail-section"><h3>Tool Calls</h3><table class="table"><thead><tr><th>Tool</th><th>Arguments</th><th>Success</th><th>Duration</th></tr></thead><tbody>';
    t.tool_calls.forEach(tc => {
      html += `<tr><td><b>${tc.name}</b></td><td style="font-family:monospace;font-size:11px;">${esc(JSON.stringify(tc.arguments).slice(0,100))}</td><td><span class="badge ${tc.success?'success':'fail'}">${tc.success?'OK':'ERR'}</span></td><td>${tc.duration_ms}ms</td></tr>`;
    });
    html += '</tbody></table></div>';
  }

  // Error
  if (t.error) {
    html += `<div class="detail-section"><h3>Error</h3><div style="background:rgba(255,87,87,.1);padding:12px;border-radius:8px;color:var(--danger);font-size:13px;">${esc(t.error)}</div></div>`;
  }

  html += '</div>';
  $('#detail-content').innerHTML = html;
}

async function loadAnalysis() {
  const a = await api('/api/analysis');
  if (a.total === 0) {
    $('#analysis-stats').innerHTML = '<div class="stat-card" style="text-align:center;color:var(--text-dim);grid-column:1/-1;">No data to analyze</div>';
    return;
  }
  $('#analysis-stats').innerHTML = [
    {l:'Total',v:a.total}, {l:'Success Rate',v:(a.success_rate*100).toFixed(1)+'%'},
    {l:'Avg Quality',v:a.avg_quality.toFixed(3)}, {l:'Avg Duration',v:a.avg_duration_ms.toFixed(0)+'ms'},
  ].map(s=>`<div class="stat-card"><div class="label">${s.l}</div><div class="value">${s.v}</div></div>`).join('');

  // Intent clusters
  const intents = a.intent_clusters || {};
  const maxI = Math.max(...Object.values(intents), 1);
  $('#intent-chart').innerHTML = Object.entries(intents).map(([k,v])=>
    `<div class="bar-row"><div class="bar-label">${k.replace(/_/g,' ')}</div><div class="bar-track"><div class="bar-fill teal" style="width:${v/maxI*100}%;">${v}</div></div></div>`).join('');

  // Error patterns
  const ep = a.error_patterns || [];
  $('#error-patterns').innerHTML = ep.length ? ep.map(e=>
    `<div style="padding:8px;border-bottom:1px solid var(--border);"><b style="color:var(--danger);">${e.keyword}</b> <span style="color:var(--text-dim);">(${e.count}x)</span></div>`).join('')
    : '<div style="color:var(--text-dim);text-align:center;padding:20px;">No error patterns detected</div>';
}

async function buildDataset() {
  const strategy = $('#d-strategy').value;
  const minQ = parseFloat($('#d-minq').value) || 0;
  const maxTasks = parseInt($('#d-max').value) || 50;
  const r = await api('/api/build-dataset', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({strategy, min_quality:minQ, max_tasks:maxTasks}),
  });
  const types = {};
  (r.tasks||[]).forEach(t => types[t.task_type] = (types[t.task_type]||0)+1);
  $('#dataset-result').innerHTML = `
    <div class="chart-card"><div class="chart-title">Dataset Result</div>
    <div class="stat-grid">
      <div class="stat-card"><div class="label">Total Tasks</div><div class="value">${r.total_tasks}</div></div>
      ${Object.entries(types).map(([k,v])=>`<div class="stat-card"><div class="label">${k}</div><div class="value">${v}</div></div>`).join('')}
    </div>
    <table class="table" style="margin-top:16px;">
      <thead><tr><th>Task ID</th><th>Type</th><th>Input</th><th>Scorers</th></tr></thead>
      <tbody>
        ${(r.tasks||[]).map(t=>`<tr><td style="font-family:monospace;font-size:12px;">${t.task_id.slice(0,12)}</td><td><span class="badge type">${t.task_type}</span></td><td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(t.input||'')}</td><td style="font-size:12px;">${(t.scorers||[]).join(', ')}</td></tr>`).join('')}
      </tbody>
    </table>
    <div style="margin-top:16px;display:flex;gap:12px;">
      <button class="btn" onclick="exportDataset()">Export YAML</button>
      <button class="btn secondary" onclick="exportJSON()">Export JSON</button>
    </div></div>`;
  toast(`Dataset built: ${r.total_tasks} tasks`);
}

function exportDataset() {
  toast('YAML export — use CLI: agent-eval trace build --output dataset.yaml');
}
function exportJSON() {
  toast('Use CLI: agent-eval trace build --output dataset.json');
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Init
loadOverview();
</script>
</body>
</html>"""
