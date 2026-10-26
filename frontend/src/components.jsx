import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity, AlertTriangle, Archive, BarChart3, Bot, Boxes, Brain, FileQuestion, FileText, Gauge, Globe,
  Inbox, LayoutDashboard, Lightbulb, ListChecks, Lock, Network, Play, ScanSearch, Scale, Search,
  Send, ServerCrash, ShieldCheck, Sparkles, Timer, Wrench,
} from "lucide-react";
import { fmtAxis, fmtDateTime, num, parseUtc, pct } from "./api.js";

// ---- Yahan apna naam aur logo badlo (sirf ye 4 lines) ----
const APP_NAME = "Governance Engine";
const APP_TAGLINE = "API and microservice monitoring";
const MADE_BY = "Python FastAPI, scikit-learn, React";
const LOGO_IMAGE = ""; // jaise "/logo.png" (file frontend/public folder mein rakho). Khali chhodo to shield icon dikhega

const STATUS_COLORS = {
  Healthy: { fill: "#dcfce7", stroke: "#10b981" },
  Warning: { fill: "#fef3c7", stroke: "#f59e0b" },
  Critical: { fill: "#ffe4e6", stroke: "#ef4444" },
  Unknown: { fill: "#e2e8f0", stroke: "#94a3b8" },
};
const PALETTE = ["#6366f1", "#06b6d4", "#f43f5e", "#f59e0b", "#8b5cf6", "#10b981", "#ec4899"];

/* ================================================================== */
/* Chhote helpers                                                      */
/* ================================================================== */
function CountUp({ value, format }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (value === null || value === undefined) return undefined;
    let raf;
    const t0 = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / 900);
      setV(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  if (value === null || value === undefined) return "-";
  return (format || ((x) => Math.round(x).toLocaleString("en-IN")))(v);
}

export function Explain({ title = "What am I looking at?", children }) {
  return (
    <details className="explain" open>
      <summary>
        <span className="bulb"><Lightbulb size={17} /></span> {title}
      </summary>
      <div className="explain-body">{children}</div>
    </details>
  );
}

function Panel({ title, desc, right, children, className = "" }) {
  return (
    <div className={"panel " + className}>
      {(title || right) && (
        <div className="panel-head">
          <div>
            {title && <h2>{title}</h2>}
            {desc && <p className="desc">{desc}</p>}
          </div>
          {right && <div className="controls">{right}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

/* ================================================================== */
/* Sidebar (left menu)                                                 */
/* ================================================================== */
export const NAV = [
  { key: "overview", icon: LayoutDashboard, label: "Overview" },
  { key: "monitoring", icon: Activity, label: "Monitoring" },
  { key: "graph", icon: Network, label: "Dependencies" },
  { key: "governance", icon: Scale, label: "API Governance" },
  { key: "ai", icon: Brain, label: "Anomalies and AI" },
];

export function Sidebar({ page, onNavigate, connected, dataText }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo">
          {LOGO_IMAGE ? (
            <img src={LOGO_IMAGE} alt="logo" style={{ width: "100%", height: "100%", borderRadius: 14, objectFit: "cover" }} />
          ) : (
            <ShieldCheck size={24} color="#fff" />
          )}
        </div>
        <div>
          <div className="brand-name">{APP_NAME}</div>
          <div className="brand-sub">{APP_TAGLINE}</div>
        </div>
      </div>

      <nav className="nav">
        {NAV.map((n) => (
          <button key={n.key} className={"nav-item" + (page === n.key ? " active" : "")} onClick={() => onNavigate(n.key)}>
            <span className="nav-icon"><n.icon size={19} /></span>
            <span className="nav-label">{n.label}</span>
          </button>
        ))}
      </nav>

      <div className="side-foot">
        <div className="status-line">
          <span className={"status-dot " + (connected ? "on" : "off")} />
          {connected ? "Backend connected" : "Backend offline"}
        </div>
        {dataText && <div className="side-note">{dataText}</div>}
        <div className="side-note">{MADE_BY}</div>
      </div>
    </aside>
  );
}

/* ================================================================== */
/* Overview page                                                       */
/* ================================================================== */
export function Pipeline({ steps }) {
  return (
    <div className="pipeline">
      {steps.map((s, i) => (
        <div className="pipe-step" key={s.title}>
          <div className="pipe-icon" style={{ background: s.color }}><s.icon size={22} color="#fff" /></div>
          <div>
            <div className="pipe-tag">{s.tag}</div>
            <div className="pipe-title">{s.title}</div>
            <div className="pipe-num">
              <CountUp value={s.value} /> <span>{s.unit}</span>
            </div>
          </div>
          {i < steps.length - 1 && <div className="pipe-arrow">›</div>}
        </div>
      ))}
    </div>
  );
}

export function StatCards({ summary, serviceCount, anomalyCount }) {
  return (
    <div className="cards">
      <div className="card stat">
        <div className="label">Services</div>
        <div className="value"><CountUp value={serviceCount} /></div>
        <div className="hint">monitored</div>
        <Boxes className="stat-ico" size={46} />
      </div>
      <div className="card stat">
        <div className="label">Total requests</div>
        <div className="value"><CountUp value={summary ? summary.total_requests : null} /></div>
        <div className="hint">API calls logged</div>
        <Send className="stat-ico" size={46} />
      </div>
      <div className="card stat">
        <div className="label">Error rate</div>
        <div className="value">
          <CountUp value={summary ? summary.overall_error_rate * 100 : null} format={(x) => x.toFixed(2) + "%"} />
        </div>
        <div className="hint">status 500 and above</div>
        <AlertTriangle className="stat-ico" size={46} />
      </div>
      <div className="card stat">
        <div className="label">Avg response time</div>
        <div className="value">
          <CountUp value={summary ? summary.overall_avg_response_time_ms : null} format={(x) => Math.round(x) + " ms"} />
        </div>
        <div className="hint">all services</div>
        <Timer className="stat-ico" size={46} />
      </div>
      <div className="card stat">
        <div className="label">Anomalies found</div>
        <div className="value"><CountUp value={anomalyCount} /></div>
        <div className="hint">by the ML model</div>
        <ScanSearch className="stat-ico" size={46} />
      </div>
    </div>
  );
}

export function HealthDonut({ rows }) {
  const data = useMemo(() => {
    const counts = { Healthy: 0, Warning: 0, Critical: 0 };
    rows.forEach((r) => {
      if (r.total_requests > 0 && counts[r.status] !== undefined) counts[r.status] += 1;
    });
    return Object.entries(counts).filter(([, v]) => v > 0).map(([name, value]) => ({ name, value }));
  }, [rows]);

  return (
    <Panel title="Service health" desc="How many services are healthy right now">
      {data.length === 0 ? (
        <div className="empty">No traffic in this time range.</div>
      ) : (
        <>
          <div className="donut">
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="name" innerRadius={64} outerRadius={92} paddingAngle={3} stroke="none">
                  {data.map((d) => (
                    <Cell key={d.name} fill={STATUS_COLORS[d.name].stroke} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-center">
              <div className="donut-num">{rows.length}</div>
              <div className="donut-label">services</div>
            </div>
          </div>
          <div className="legend center">
            {["Healthy", "Warning", "Critical"].map((s) => (
              <span key={s}>
                <span className="dot" style={{ background: STATUS_COLORS[s].stroke }} />
                {s}: <b>{data.find((d) => d.name === s)?.value || 0}</b>
              </span>
            ))}
          </div>
        </>
      )}
    </Panel>
  );
}

export function AnomaliesByService({ counts }) {
  return (
    <Panel title="Anomalies by service" desc="Which service the ML model flagged most often">
      {counts.length === 0 ? (
        <div className="empty">No anomalies yet. Run POST /ml/detect in the backend.</div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(160, counts.length * 44 + 20)}>
          <BarChart data={counts} layout="vertical" margin={{ top: 4, right: 36, left: 0, bottom: 0 }}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: "rgba(99,102,241,0.06)" }} />
            <Bar dataKey="count" name="Anomalies" radius={[0, 8, 8, 0]} barSize={20}>
              {counts.map((c, i) => (
                <Cell key={c.name} fill={PALETTE[i % PALETTE.length]} />
              ))}
              <LabelList dataKey="count" position="right" style={{ fontSize: 12, fontWeight: 700, fill: "#334155" }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}

export function TopAnomalies({ items, recs, onOpen }) {
  return (
    <Panel title="Top anomalies" desc="The most unusual moments found by the ML model. Click one to see the AI advice.">
      {items.length === 0 ? (
        <div className="empty">No anomalies found yet.</div>
      ) : (
        <div className="toplist">
          {items.map((a, i) => (
            <button key={a.id} className="top-row" onClick={() => onOpen(a.id)}>
              <span className="rank">{i + 1}</span>
              <span className="top-main">
                <b>{a.service_name}</b>
                <small>{fmtDateTime(a.window_start)} · {Math.round(a.avg_response_ms)} ms · {pct(a.error_rate, 0)} errors</small>
              </span>
              <span className="score-pill">{Number(a.score).toFixed(2)}</span>
              {recs[a.id] && <span className={"badge " + recs[a.id].priority}>{recs[a.id].priority}</span>}
              <span className="chev">›</span>
            </button>
          ))}
        </div>
      )}
    </Panel>
  );
}

/* ================================================================== */
/* Monitoring page                                                     */
/* ================================================================== */
export function HealthTable({ rows, selectedId, onSelect, rangeLabel }) {
  const noTraffic = rows.length > 0 && rows.every((r) => r.total_requests === 0);
  return (
    <Panel title="Service health table" desc={`Time range: ${rangeLabel}. Click a service to see its charts below.`}>
      {noTraffic && <div className="notice info">No traffic in this time range. Choose "All data" at the top.</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Service</th>
              <th>Status</th>
              <th>Requests</th>
              <th>Error rate</th>
              <th>p95 response</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.service_id}
                className={"clickable" + (r.service_id === selectedId ? " selected" : "")}
                onClick={() => onSelect(r.service_id)}
              >
                <td><b>{r.service_name}</b></td>
                <td><span className={"badge " + r.status}>{r.status}</span></td>
                <td>{num(r.total_requests)}</td>
                <td>{pct(r.error_rate, 2)}</td>
                <td>{Math.round(r.p95_response_time_ms)} ms</td>
                <td className="wrap">{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function TrendCharts({ series, anomalies, services, selectedId, onSelect, loading }) {
  const data = useMemo(() => {
    const rows = (series || []).map((b) => {
      const has = b.total_requests > 0;
      const d = parseUtc(b.bucket_start);
      return {
        ts: d ? d.getTime() : 0,
        ms: has ? b.avg_response_time_ms : null,
        err: has ? Number((b.error_rate * 100).toFixed(2)) : null,
      };
    });
    const first = rows.findIndex((r) => r.ms !== null);
    let last = -1;
    rows.forEach((r, i) => {
      if (r.ms !== null) last = i;
    });
    return first === -1 ? [] : rows.slice(first, last + 1);
  }, [series]);

  const marks = useMemo(() => {
    if (data.length === 0) return [];
    const lo = data[0].ts;
    const hi = data[data.length - 1].ts;
    return (anomalies || [])
      .map((a) => parseUtc(a.window_start)?.getTime())
      .filter((t) => t && t >= lo && t <= hi);
  }, [anomalies, data]);

  const axis = (
    <XAxis
      dataKey="ts"
      type="number"
      scale="time"
      domain={["dataMin", "dataMax"]}
      tickFormatter={fmtAxis}
      tick={{ fontSize: 11 }}
      minTickGap={60}
      axisLine={false}
      tickLine={false}
    />
  );
  const tip = <Tooltip labelFormatter={(v) => fmtAxis(v)} contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0" }} />;
  const hasData = data.length > 0;

  return (
    <Panel
      title="Response time and errors over time"
      desc="Red vertical lines show moments where the ML model detected something unusual."
      right={
        <select value={selectedId ?? ""} onChange={(e) => onSelect(Number(e.target.value))}>
          {services.map((s) => (
            <option key={s.service_id} value={s.service_id}>{s.service_name}</option>
          ))}
        </select>
      }
    >
      {loading && <div className="empty">Loading charts...</div>}
      {!loading && !hasData && <div className="empty">This service has no data in the selected time range.</div>}
      {!loading && hasData && (
        <div className="charts">
          <div className="chart-box">
            <div className="chart-title">Average response time (ms)</div>
            <ResponsiveContainer width="100%" height={270}>
              <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gMs" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                {axis}
                <YAxis tick={{ fontSize: 11 }} domain={[0, "auto"]} width={42} axisLine={false} tickLine={false} />
                {tip}
                {marks.map((t, i) => (
                  <ReferenceLine key={i} x={t} stroke="#ef4444" strokeOpacity={0.45} strokeWidth={2} />
                ))}
                <Area type="monotone" dataKey="ms" name="Avg ms" stroke="#6366f1" strokeWidth={2.5} fill="url(#gMs)" connectNulls={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-box">
            <div className="chart-title">Error rate (%)</div>
            <ResponsiveContainer width="100%" height={270}>
              <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gErr" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                {axis}
                <YAxis tick={{ fontSize: 11 }} domain={[0, "auto"]} width={42} axisLine={false} tickLine={false} />
                {tip}
                {marks.map((t, i) => (
                  <ReferenceLine key={i} x={t} stroke="#ef4444" strokeOpacity={0.45} strokeWidth={2} />
                ))}
                <Area type="monotone" dataKey="err" name="Error %" stroke="#f43f5e" strokeWidth={2.5} fill="url(#gErr)" connectNulls={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      <div className="legend">
        <span><span className="dot" style={{ background: "#6366f1" }} />Average response time</span>
        <span><span className="dot" style={{ background: "#f43f5e" }} />Error rate</span>
        <span><span className="vline" />ML anomaly ({marks.length})</span>
      </div>
    </Panel>
  );
}

export function EndpointTable({ rows, serviceName }) {
  return (
    <Panel title="Slowest endpoints" desc={`Which API endpoints of ${serviceName || "this service"} are slow or failing`}>
      {rows.length === 0 ? (
        <div className="empty">No endpoint data in this time range.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Method</th>
                <th>Requests</th>
                <th>Avg</th>
                <th>p95</th>
                <th>Error rate</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 8).map((r) => (
                <tr key={r.method + r.endpoint}>
                  <td><code>{r.endpoint}</code></td>
                  <td><span className="method">{r.method}</span></td>
                  <td>{num(r.total_requests)}</td>
                  <td>{Math.round(r.avg_response_time_ms)} ms</td>
                  <td>{Math.round(r.p95_response_time_ms)} ms</td>
                  <td>{pct(r.error_rate, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/* ================================================================== */
/* Dependency graph page                                               */
/* ================================================================== */
const NODE_W = 200;
const NODE_H = 60;
const COL_GAP = 150;
const ROW_GAP = 32;
const PAD = 28;

function computeLayout(nodes, edges) {
  const level = {};
  nodes.forEach((n) => (level[n.id] = 0));
  const cap = Math.max(nodes.length - 1, 0);
  for (let i = 0; i < nodes.length; i++) {
    let changed = false;
    for (const e of edges) {
      if (level[e.source] === undefined || level[e.target] === undefined) continue;
      if (level[e.target] < level[e.source] + 1 && level[e.source] + 1 <= cap) {
        level[e.target] = level[e.source] + 1;
        changed = true;
      }
    }
    if (!changed) break;
  }
  const columns = {};
  nodes.forEach((n) => (columns[level[n.id]] = [...(columns[level[n.id]] || []), n]));
  const colKeys = Object.keys(columns).map(Number).sort((a, b) => a - b);
  const maxRows = Math.max(1, ...colKeys.map((k) => columns[k].length));
  const pos = {};
  colKeys.forEach((k, ci) => {
    const list = columns[k];
    const offset = (maxRows - list.length) / 2;
    list.forEach((n, ri) => {
      pos[n.id] = { x: PAD + ci * (NODE_W + COL_GAP), y: PAD + (ri + offset) * (NODE_H + ROW_GAP) };
    });
  });
  return {
    pos,
    width: PAD * 2 + colKeys.length * NODE_W + Math.max(colKeys.length - 1, 0) * COL_GAP,
    height: PAD * 2 + maxRows * NODE_H + (maxRows - 1) * ROW_GAP,
  };
}

function analyze(nodes, edges) {
  const out = {};
  const inn = {};
  nodes.forEach((n) => {
    out[n.id] = [];
    inn[n.id] = [];
  });
  edges.forEach((e) => {
    if (out[e.source] && inn[e.target]) {
      out[e.source].push(e.target);
      inn[e.target].push(e.source);
    }
  });
  // Agar "id" fail ho jaye to kaun kaun (seedha ya ghuma ke) affect hoga = usko call karne wale sab
  const affected = (id) => {
    const seen = new Set();
    const stack = [...(inn[id] || [])];
    while (stack.length) {
      const x = stack.pop();
      if (seen.has(x)) continue;
      seen.add(x);
      stack.push(...(inn[x] || []));
    }
    seen.delete(id);
    return [...seen];
  };
  return { out, inn, affected };
}

export function DependencyGraph({ nodes, edges, healthById, anomalyCountById, selected, onSelect }) {
  const layout = useMemo(() => computeLayout(nodes, edges), [nodes, edges]);
  const graph = useMemo(() => analyze(nodes, edges), [nodes, edges]);
  const nameOf = (id) => nodes.find((n) => n.id === id)?.name || String(id);
  const maxCalls = Math.max(1, ...edges.map((e) => e.call_count));

  const blast = selected ? graph.affected(selected) : [];
  const related = new Set(selected ? [selected, ...graph.out[selected], ...graph.inn[selected]] : []);

  const ranking = useMemo(
    () =>
      nodes
        .map((n) => ({ id: n.id, name: n.name, count: graph.affected(n.id).length }))
        .sort((a, b) => b.count - a.count),
    [nodes, graph]
  );

  const sel = selected ? nodes.find((n) => n.id === selected) : null;
  const h = sel ? healthById[sel.id] : null;

  return (
    <div className="graph-layout">
      <Panel title="Service dependency map" desc="Click any service to see what depends on it and what breaks if it fails.">
        {nodes.length === 0 ? (
          <div className="empty">No graph data found.</div>
        ) : (
          <div className="graph-wrap">
            <svg
              width="100%"
              style={{ maxWidth: layout.width, display: "block", margin: "0 auto" }}
              viewBox={`0 0 ${layout.width} ${layout.height}`}
              onClick={() => onSelect(null)}
            >
              <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="13" markerHeight="13" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
                </marker>
              </defs>

              {edges.map((e) => {
                const a = layout.pos[e.source];
                const b = layout.pos[e.target];
                if (!a || !b) return null;
                const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2;
                const x2 = b.x, y2 = b.y + NODE_H / 2;
                const color = e.error_rate >= 0.05 ? "#ef4444" : e.error_rate >= 0.02 ? "#f59e0b" : "#94a3b8";
                const touch = !selected || e.source === selected || e.target === selected;
                return (
                  <g key={e.source + "-" + e.target} opacity={touch ? 1 : 0.18}>
                    <path
                      d={`M ${x1} ${y1} C ${x1 + 70} ${y1}, ${x2 - 70} ${y2}, ${x2} ${y2}`}
                      fill="none"
                      stroke={color}
                      strokeWidth={1.8 + 4.5 * (e.call_count / maxCalls)}
                      strokeLinecap="round"
                      markerEnd="url(#arrow)"
                    />
                    <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 8} textAnchor="middle" fontSize="12" fontWeight="600" fill="#334155">
                      {num(e.call_count)} calls
                    </text>
                  </g>
                );
              })}

              {nodes.map((n) => {
                const p = layout.pos[n.id];
                const hh = healthById[n.id];
                const status = hh && hh.total_requests > 0 ? hh.status : "Unknown";
                const col = STATUS_COLORS[status] || STATUS_COLORS.Unknown;
                const isSel = selected === n.id;
                const isBlast = blast.includes(n.id);
                const dim = selected && !related.has(n.id) && !isBlast;
                const anomalies = anomalyCountById[n.id] || 0;
                return (
                  <g
                    key={n.id}
                    opacity={dim ? 0.3 : 1}
                    style={{ cursor: "pointer" }}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      onSelect(isSel ? null : n.id);
                    }}
                  >
                    <rect
                      x={p.x}
                      y={p.y}
                      width={NODE_W}
                      height={NODE_H}
                      rx="14"
                      fill={col.fill}
                      stroke={isBlast ? "#ef4444" : col.stroke}
                      strokeWidth={isSel ? 4 : isBlast ? 3 : 2}
                      strokeDasharray={isBlast ? "6 4" : undefined}
                    />
                    <text x={p.x + NODE_W / 2} y={p.y + 25} textAnchor="middle" fontSize="14" fontWeight="700" fill="#0f172a">
                      {n.name}
                    </text>
                    <text x={p.x + NODE_W / 2} y={p.y + 44} textAnchor="middle" fontSize="11.5" fill={anomalies ? "#be123c" : "#475569"}>
                      {anomalies ? `${anomalies} anomalies` : status}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        )}
        <div className="legend">
          <span><span className="dot" style={{ background: "#10b981" }} />Healthy</span>
          <span><span className="dot" style={{ background: "#f59e0b" }} />Warning</span>
          <span><span className="dot" style={{ background: "#ef4444" }} />Critical</span>
          <span><span className="dash" />Would be affected if the selected service fails</span>
        </div>
      </Panel>

      <Panel title={sel ? sel.name : "Most critical services"} desc={sel ? "Impact analysis" : "Ranked by how many services depend on them"}>
        {!sel ? (
          <div className="rank-list">
            {ranking.map((r, i) => (
              <button key={r.id} className="rank-row" onClick={() => onSelect(r.id)}>
                <span className="rank">{i + 1}</span>
                <span className="rank-name">{r.name}</span>
                <span className="rank-count">{r.count} {r.count === 1 ? "service depends" : "services depend"} on it</span>
              </button>
            ))}
            <div className="hint-text">Tip: click a service in the map for details.</div>
          </div>
        ) : (
          <div className="impact">
            <div className="impact-top">
              <span className={"badge " + (h && h.total_requests > 0 ? h.status : "Unknown")}>{h && h.total_requests > 0 ? h.status : "No traffic"}</span>
              <span className="muted">{h ? num(h.total_requests) : 0} requests · p95 {h ? Math.round(h.p95_response_time_ms) : 0} ms · {anomalyCountById[sel.id] || 0} anomalies</span>
            </div>

            <h4>It calls (depends on)</h4>
            <div className="chips">
              {graph.out[sel.id].length === 0 ? <span className="muted">Nothing. It is independent.</span> :
                graph.out[sel.id].map((id) => <button key={id} className="chip-btn" onClick={() => onSelect(id)}>{nameOf(id)}</button>)}
            </div>

            <h4>It is called by</h4>
            <div className="chips">
              {graph.inn[sel.id].length === 0 ? <span className="muted">No other service calls it.</span> :
                graph.inn[sel.id].map((id) => <button key={id} className="chip-btn" onClick={() => onSelect(id)}>{nameOf(id)}</button>)}
            </div>

            <div className={"blast " + (blast.length ? "danger" : "safe")}>
              <b>If {sel.name} fails:</b>{" "}
              {blast.length === 0
                ? "no other service is affected."
                : `${blast.length} ${blast.length === 1 ? "service" : "services"} can be affected (${blast.map(nameOf).join(", ")}).`}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

/* ================================================================== */
/* Anomalies and AI page                                               */
/* ================================================================== */
function Recommendation({ rec }) {
  return (
    <div className="rec">
      <div className={"prio-banner " + rec.priority}>
        <span>Priority</span>
        <b>{rec.priority}</b>
      </div>
      <h4><FileText size={15} /> Summary</h4>
      <p>{rec.summary}</p>
      <h4><Search size={15} /> Probable causes</h4>
      <ul>{rec.probable_causes.map((c, i) => <li key={i}>{c}</li>)}</ul>
      <h4><Globe size={15} /> Impact</h4>
      <p>{rec.impact}</p>
      <h4><Wrench size={15} /> Suggested fixes</h4>
      <ol>{rec.suggested_fixes.map((f, i) => <li key={i}>{f}</li>)}</ol>
    </div>
  );
}

export function AiPage({ anomalies, recs, aiStatus, busyId, topBusy, aiError, onRecommend, onRecommendTop, selectedId, onSelect }) {
  const [filter, setFilter] = useState("all");
  const [visible, setVisible] = useState(14);

  const names = useMemo(() => [...new Set(anomalies.map((a) => a.service_name))].sort(), [anomalies]);
  const list = anomalies.filter((a) => filter === "all" || a.service_name === filter);
  const current = anomalies.find((a) => a.id === selectedId) || null;
  const rec = current ? recs[current.id] : null;

  return (
    <div>
      <div className="toolbar">
        {aiStatus && <span className="chip"><Bot size={14} /> AI mode: {aiStatus.mode}</span>}
        <select value={filter} onChange={(e) => { setFilter(e.target.value); setVisible(14); }}>
          <option value="all">All services</option>
          {names.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <button className="primary" disabled={topBusy || anomalies.length === 0} onClick={onRecommendTop}>
          {topBusy ? "Generating..." : <><Sparkles size={16} /> Generate advice for top 5</>}
        </button>
      </div>

      {aiError && <div className="notice error">Could not create the recommendation: {aiError}</div>}

      {anomalies.length === 0 ? (
        <Panel><div className="empty">No anomalies found. Run POST /ml/detect in the backend, then press Refresh.</div></Panel>
      ) : (
        <div className="ai-layout">
          <Panel title="Detected anomalies" desc={`${list.length} unusual time windows (5 minutes each)`}>
            <div className="alist">
              {list.slice(0, visible).map((a) => (
                <button key={a.id} className={"arow" + (a.id === selectedId ? " active" : "")} onClick={() => onSelect(a.id)}>
                  <div className="arow-top">
                    <b>{a.service_name}</b>
                    {recs[a.id] ? <span className={"badge " + recs[a.id].priority}>{recs[a.id].priority}</span> : <span className="muted small">no advice yet</span>}
                  </div>
                  <div className="arow-sub">
                    {fmtDateTime(a.window_start)} · {Math.round(a.avg_response_ms)} ms · {pct(a.error_rate, 0)} errors
                  </div>
                  <div className="meter"><span style={{ width: Math.min(100, a.score * 100) + "%" }} /></div>
                </button>
              ))}
            </div>
            {list.length > visible && (
              <div style={{ textAlign: "center", marginTop: 12 }}>
                <button onClick={() => setVisible((v) => v + 14)}>Show more ({list.length - visible} left)</button>
              </div>
            )}
          </Panel>

          <Panel className="detail" title={current ? current.service_name : "Details"} desc={current ? `Window starting ${fmtDateTime(current.window_start)}` : "Select an anomaly on the left"}>
            {!current ? (
              <div className="empty">Pick an anomaly to see the AI explanation.</div>
            ) : (
              <>
                <div className="tiles">
                  <div className="tile"><span>Avg response</span><b>{Math.round(current.avg_response_ms)} ms</b></div>
                  <div className="tile"><span>Error rate</span><b>{pct(current.error_rate, 1)}</b></div>
                  <div className="tile"><span>Anomaly score</span><b>{Number(current.score).toFixed(3)}</b></div>
                </div>
                {!rec ? (
                  <div className="gen-box">
                    <p>The ML model flagged this window. Ask the AI what may have happened and how to fix it.</p>
                    <button className="primary" disabled={busyId === current.id} onClick={() => onRecommend(current.id, false)}>
                      {busyId === current.id ? "Thinking..." : <><Sparkles size={16} /> Generate AI recommendation</>}
                    </button>
                  </div>
                ) : (
                  <>
                    <Recommendation rec={rec} />
                    <div className="rec-foot">
                      <span className="muted small">Source: {rec.source}</span>
                      <button className="small" disabled={busyId === current.id} onClick={() => onRecommend(current.id, true)}>
                        {busyId === current.id ? "Regenerating..." : "Regenerate"}
                      </button>
                    </div>
                  </>
                )}
              </>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}


/* ================================================================== */
/* API Governance                                                      */
/* ================================================================== */
const CATEGORY_INFO = {
  dependency_drift: { label: "Dependency drift", icon: Network, hint: "Calls that differ from the documented architecture" },
  unused_api: { label: "Unused APIs", icon: Archive, hint: "Documented but never called" },
  broken_api: { label: "Broken APIs", icon: ServerCrash, hint: "Many server errors or 404 responses" },
  undocumented_api: { label: "Undocumented APIs", icon: FileQuestion, hint: "Called but missing from the catalog" },
  security: { label: "Security risks", icon: Lock, hint: "Risk signals found in the traffic" },
  performance: { label: "Performance", icon: Gauge, hint: "Slow endpoints (p95)" },
};
const CATEGORY_ORDER = Object.keys(CATEGORY_INFO);

function CatIcon({ k, size = 18 }) {
  const Icon = CATEGORY_INFO[k].icon;
  return <Icon size={size} />;
}
const STATE_ORDER = { Broken: 0, Undocumented: 1, Unused: 2, Active: 3 };

export function timeAgo(iso) {
  const d = parseUtc(iso);
  if (!d || isNaN(d)) return "-";
  const sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return "just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hr = Math.round(min / 60);
  if (hr < 48) return `${hr} h ago`;
  return `${Math.round(hr / 24)} days ago`;
}

function ScoreRing({ score, grade, size = 150 }) {
  const r = 54;
  const c = 2 * Math.PI * r;
  const color = score >= 80 ? "#10b981" : score >= 60 ? "#f59e0b" : "#ef4444";
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg viewBox="0 0 140 140" width={size} height={size}>
        <circle cx="70" cy="70" r={r} fill="none" stroke="#e2e8f0" strokeWidth="12" />
        <circle
          cx="70" cy="70" r={r} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
          strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 70 70)"
        />
      </svg>
      <div className="ring-center">
        <div className="ring-score" style={{ fontSize: size * 0.27 }}><CountUp value={score} /></div>
        <div className="ring-grade">Grade {grade}</div>
      </div>
    </div>
  );
}

function SeverityChips({ counts }) {
  return (
    <div className="sev-chips">
      {["Critical", "High", "Medium", "Low"].map((k) => (
        <span key={k} className={"badge " + k}>{counts[k] || 0} {k}</span>
      ))}
    </div>
  );
}

/* Overview par chhota summary */
export function GovernanceSummary({ report, onOpen }) {
  const scan = report && report.scan;
  return (
    <Panel
      title="API governance at a glance"
      desc="Documented architecture compared with what the logs really show"
      right={<button className="small" onClick={onOpen}>Open API Governance</button>}
    >
      {!scan ? (
        <div className="empty">Governance scan is not set up yet. Open API Governance to set it up.</div>
      ) : (
        <div className="gov-glance">
          <ScoreRing score={scan.summary.score} grade={scan.summary.grade} size={120} />
          <div className="glance-body">
            <SeverityChips counts={scan.summary.by_severity} />
            <div className="glance-list">
              {scan.findings.slice(0, 3).map((f) => (
                <div key={f.id} className="glance-row">
                  <span className={"badge " + f.severity}>{f.severity}</span>
                  <span>{f.title}</span>
                </div>
              ))}
            </div>
            <div className="muted small">Last scan {timeAgo(scan.created_at)} ({scan.trigger})</div>
          </div>
        </div>
      )}
    </Panel>
  );
}

function DriftGraph({ architecture, countByService }) {
  const edges = architecture.edges;
  const used = new Set();
  edges.forEach((e) => {
    used.add(e.source);
    used.add(e.target);
  });
  const nodes = architecture.nodes.filter((n) => used.has(n.id));

  // Services ko gol ghere (ellipse) mein rakhte hain, taaki arrows aapas mein na uljhein
  const W = 940, H = 450, cx = W / 2, cy = H / 2, rx = 345, ry = 150, nw = 178, nh = 54;
  const pos = {};
  nodes.forEach((n, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(nodes.length, 1);
    pos[n.id] = { x: cx + rx * Math.cos(a), y: cy + ry * Math.sin(a) };
  });
  // Box ke kinare ka wo point jahan se arrow nikalna ya pahunchna hai
  const edgePoint = (from, to) => {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const t = Math.min(nw / 2 / Math.abs(dx || 1e-6), nh / 2 / Math.abs(dy || 1e-6));
    return { x: from.x + dx * t, y: from.y + dy * t };
  };

  const style = {
    ok: { color: "#10b981", dash: undefined, marker: "ok" },
    undocumented: { color: "#ef4444", dash: "9 6", marker: "bad" },
    stale: { color: "#94a3b8", dash: "2 7", marker: "stale" },
    observed: { color: "#94a3b8", dash: undefined, marker: "stale" },
  };
  const markers = { ok: "#10b981", bad: "#ef4444", stale: "#94a3b8" };

  return (
    <div className="graph-wrap">
      <svg width="100%" style={{ maxWidth: W, display: "block", margin: "0 auto" }} viewBox={`0 0 ${W} ${H}`}>
        <defs>
          {Object.entries(markers).map(([k, c]) => (
            <marker key={k} id={"arr-" + k} viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="14" markerHeight="14" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
            </marker>
          ))}
        </defs>

        {edges.map((e) => {
          const a = pos[e.source];
          const b = pos[e.target];
          if (!a || !b) return null;
          const st = style[e.state] || style.observed;
          const p0 = edgePoint(a, b);
          const p1 = edgePoint(b, a);
          const dx = p1.x - p0.x;
          const dy = p1.y - p0.y;
          const len = Math.hypot(dx, dy) || 1;
          const bend = 0.1 * len;
          const qx = (p0.x + p1.x) / 2 - (dy / len) * bend;
          const qy = (p0.y + p1.y) / 2 + (dx / len) * bend;
          const lx = 0.25 * p0.x + 0.5 * qx + 0.25 * p1.x;
          const ly = 0.25 * p0.y + 0.5 * qy + 0.25 * p1.y;
          const label =
            e.state === "stale" ? "documented, never called" : e.state === "undocumented" ? `${num(e.calls)} calls, not documented` : `${num(e.calls)} calls`;
          return (
            <g key={e.source + "-" + e.target}>
              <path
                d={`M ${p0.x} ${p0.y} Q ${qx} ${qy} ${p1.x} ${p1.y}`}
                fill="none" stroke={st.color} strokeWidth="3" strokeDasharray={st.dash} strokeLinecap="round"
                markerEnd={`url(#arr-${st.marker})`}
              />
              <text
                x={lx} y={ly - 5} textAnchor="middle" fontSize="12" fontWeight="700"
                fill={st.color === "#94a3b8" ? "#475569" : st.color}
                stroke="#fafbff" strokeWidth="5" strokeLinejoin="round" paintOrder="stroke"
              >
                {label}
              </text>
            </g>
          );
        })}

        {nodes.map((n) => {
          const p = pos[n.id];
          const cnt = countByService[n.name] || 0;
          return (
            <g key={n.id}>
              <rect x={p.x - nw / 2} y={p.y - nh / 2} width={nw} height={nh} rx="14" fill="#ffffff" stroke={cnt ? "#f43f5e" : "#818cf8"} strokeWidth="2.5" />
              <text x={p.x} y={p.y - 3} textAnchor="middle" fontSize="14" fontWeight="700" fill="#0f172a">{n.name}</text>
              <text x={p.x} y={p.y + 16} textAnchor="middle" fontSize="11.5" fill={cnt ? "#be123c" : "#475569"}>
                {cnt ? `${cnt} ${cnt === 1 ? "finding" : "findings"}` : "no findings"}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function GovernancePage({ status, report, scans, busy, error, onScan, onSeed, onRemoveSeed }) {
  const [cat, setCat] = useState("all");
  const [visible, setVisible] = useState(8);
  const [invVisible, setInvVisible] = useState(10);

  const scan = report && report.scan;
  const findings = scan ? scan.findings : [];
  const filtered = findings.filter((f) => cat === "all" || f.category === cat);
  const countByService = useMemo(() => {
    const m = {};
    findings.forEach((f) => {
      if (f.service) m[f.service] = (m[f.service] || 0) + 1;
    });
    return m;
  }, [findings]);
  const inventory = useMemo(
    () => (scan ? [...scan.inventory].sort((a, b) => STATE_ORDER[a.state] - STATE_ORDER[b.state]) : []),
    [scan]
  );

  if (!report || !report.setup || !scan) {
    return (
      <Panel title="Set up API governance" desc="The scan needs two documents to compare with the logs">
        <p className="lead">
          Governance means comparing <b>what should happen</b> (the documented APIs and the documented architecture) with{" "}
          <b>what really happens</b> (your logs). This simulated system has no such documents, so one click creates demo ones.
        </p>
        <ul className="plain">
          <li><b>API catalog:</b> the list of officially documented APIs of every service.</li>
          <li><b>Documented architecture:</b> which service is allowed to call which.</li>
          <li><b>A little extra simulated traffic</b> with realistic problems: a broken endpoint, a login attack pattern and an unexpected caller.</li>
        </ul>
        {error && <div className="notice error">{error}</div>}
        <button className="primary" disabled={busy} onClick={onSeed}>
          {busy ? "Setting up..." : <><Sparkles size={16} /> Set up demo data and run the first scan</>}
        </button>
      </Panel>
    );
  }

  const s = scan.summary;
  return (
    <div>
      {error && <div className="notice error">{error}</div>}

      <div className="gov-top">
        <div className="panel gov-score">
          <div className="gov-card-title">Governance score</div>
          <ScoreRing score={s.score} grade={s.grade} />
          <div className="muted small">{s.total_findings} findings in total</div>
          <SeverityChips counts={s.by_severity} />
        </div>

        <div className="panel">
          <div className="gov-card-title">Autonomous scanning</div>
          <div className="auto-line">
            <span className={"status-dot " + (status && status.auto_scan_enabled ? "on" : "off")} />
            {status && status.auto_scan_enabled ? `On: scans by itself every ${status.auto_scan_minutes} min` : "Off: only manual scans"}
          </div>
          <div className="muted small">Last scan {timeAgo(scan.created_at)} ({scan.trigger})</div>
          <div className="scan-list">
            {scans.slice(0, 5).map((x) => (
              <div key={x.id} className="scan-row">
                <span>{timeAgo(x.created_at)}</span>
                <span className="muted">{x.trigger}</span>
                <b>{x.score}</b>
              </div>
            ))}
          </div>
          <button className="primary" disabled={busy} onClick={onScan}>{busy ? "Scanning..." : <><Play size={15} /> Run scan now</>}</button>
        </div>

        <div className="panel">
          <div className="gov-card-title">Architecture drift</div>
          <div className="drift-num">{s.drift_percent === null ? "-" : s.drift_percent + "%"}</div>
          <div className="muted small">How far the real architecture is from the documented one</div>
          <div className="kv"><span>Dependencies</span><b>{s.dependencies_observed} observed / {s.dependencies_documented} documented</b></div>
          <div className="kv"><span>APIs</span><b>{s.apis_observed} observed / {s.apis_documented} documented</b></div>
        </div>
      </div>

      <div className="cat-tiles">
        <button className={"cat-tile" + (cat === "all" ? " active" : "")} onClick={() => { setCat("all"); setVisible(8); }}>
          <span className="cat-icon"><ListChecks size={20} /></span>
          <span className="cat-name">All findings</span>
          <b>{findings.length}</b>
        </button>
        {CATEGORY_ORDER.map((k) => (
          <button key={k} className={"cat-tile" + (cat === k ? " active" : "") + (s.by_category[k] ? "" : " zero")} title={CATEGORY_INFO[k].hint}
            onClick={() => { setCat(cat === k ? "all" : k); setVisible(8); }}>
            <span className="cat-icon"><CatIcon k={k} size={20} /></span>
            <span className="cat-name">{CATEGORY_INFO[k].label}</span>
            <b>{s.by_category[k] || 0}</b>
          </button>
        ))}
      </div>

      <Panel title="Findings" desc="Every problem found, with what to do about it. Click a tile above to filter.">
        {filtered.length === 0 ? (
          <div className="empty">No findings in this category.</div>
        ) : (
          <div className="findings">
            {filtered.slice(0, visible).map((f) => (
              <div key={f.id} className={"finding sev-" + f.severity}>
                <div className="finding-head">
                  <span className={"badge " + f.severity}>{f.severity}</span>
                  <span className="cat-chip"><CatIcon k={f.category} size={14} /> {CATEGORY_INFO[f.category].label}</span>
                  {f.service && <span className="muted small">{f.service}</span>}
                </div>
                <div className="finding-title">{f.title}</div>
                <div className="finding-detail">{f.detail}</div>
                <div className="finding-fix"><b>How to fix:</b> {f.recommendation}</div>
              </div>
            ))}
          </div>
        )}
        {filtered.length > visible && (
          <div style={{ textAlign: "center", marginTop: 12 }}>
            <button onClick={() => setVisible((v) => v + 8)}>Show more ({filtered.length - visible} left)</button>
          </div>
        )}
      </Panel>

      <Panel title="Documented vs real architecture" desc="Green: documented and used. Red dashed: used but not documented. Grey dotted: documented but never used.">
        <DriftGraph architecture={scan.architecture} countByService={countByService} />
        <div className="legend">
          <span><span className="line ok" />Documented and used</span>
          <span><span className="line bad" />Used but not documented</span>
          <span><span className="line stale" />Documented but never used</span>
        </div>
      </Panel>

      <Panel title="API inventory" desc="Every API found in the catalog or in the logs, and what state it is in">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Service</th><th>API</th><th>Calls</th><th>Error rate</th><th>p95</th><th>Documented</th><th>State</th>
              </tr>
            </thead>
            <tbody>
              {inventory.slice(0, invVisible).map((i) => (
                <tr key={i.service + i.method + i.endpoint}>
                  <td><b>{i.service}</b></td>
                  <td><span className="method">{i.method}</span> <code>{i.endpoint}</code></td>
                  <td>{num(i.calls)}</td>
                  <td>{pct(i.error_rate, 1)}</td>
                  <td>{Math.round(i.p95_ms)} ms</td>
                  <td>{i.documented === null ? "-" : i.documented ? "Yes" : "No"}</td>
                  <td><span className={"badge " + i.state}>{i.state}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {inventory.length > invVisible && (
          <div style={{ textAlign: "center", marginTop: 12 }}>
            <button onClick={() => setInvVisible((v) => v + 10)}>Show more ({inventory.length - invVisible} left)</button>
          </div>
        )}
      </Panel>

      <div className="gov-foot">
        <span className="muted small">
          Security findings are risk signals found in the traffic logs. This is not a vulnerability scanner.
        </span>
        <button className="small" disabled={busy} onClick={onRemoveSeed}>Remove demo data</button>
      </div>
    </div>
  );
}