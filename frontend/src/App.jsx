import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3, Brain, Inbox, Network, RefreshCw, Scale, Sparkles } from "lucide-react";
import { api, fmtDate, isRealService, pickInterval } from "./api.js";
import {
  AiPage,
  AnomaliesByService,
  DependencyGraph,
  EndpointTable,
  Explain,
  GovernancePage,
  GovernanceSummary,
  HealthDonut,
  HealthTable,
  NAV,
  Pipeline,
  Sidebar,
  StatCards,
  TopAnomalies,
  TrendCharts,
} from "./components.jsx";

const RANGES = [
  { key: "all", label: "All data" },
  { key: "24", label: "Last 24 hours", hours: 24 },
  { key: "168", label: "Last 7 days", hours: 168 },
  { key: "720", label: "Last 30 days", hours: 720 },
];

const PAGE_INFO = {
  overview: {
    title: "Overview",
    sub: "A quick summary of your whole microservice platform",
  },
  monitoring: {
    title: "Monitoring",
    sub: "Speed, errors and health of every service",
  },
  graph: {
    title: "Dependencies",
    sub: "Which service calls which, and what breaks if one fails",
  },
  governance: {
    title: "API Governance",
    sub: "Documented architecture compared with what really happens",
  },
  ai: {
    title: "Anomalies and AI",
    sub: "Unusual behaviour found by machine learning, explained by AI",
  },
};

function pageFromHash() {
  const h = window.location.hash.replace("#", "");
  return NAV.some((n) => n.key === h) ? h : "overview";
}

export default function App() {
  const [page, setPage] = useState(pageFromHash());
  const [range, setRange] = useState("all");
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  const [summary, setSummary] = useState(null);
  const [dataRange, setDataRange] = useState(null);
  const [health, setHealth] = useState([]);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [anomalies, setAnomalies] = useState([]);
  const [recs, setRecs] = useState({});
  const [aiStatus, setAiStatus] = useState(null);

  const [selectedId, setSelectedId] = useState(null);
  const [series, setSeries] = useState([]);
  const [endpoints, setEndpoints] = useState([]);
  const [seriesLoading, setSeriesLoading] = useState(false);

  const [govStatus, setGovStatus] = useState(null);
  const [govReport, setGovReport] = useState(null);
  const [govScans, setGovScans] = useState([]);
  const [govBusy, setGovBusy] = useState(false);
  const [govError, setGovError] = useState("");

  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedAnomaly, setSelectedAnomaly] = useState(null);

  const [backendError, setBackendError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [topBusy, setTopBusy] = useState(false);
  const [aiError, setAiError] = useState("");

  const hours = range === "all" ? dataRange?.hours_span || 720 : Number(range);
  const rangeLabel = RANGES.find((r) => r.key === range).label;

  function navigate(key) {
    setPage(key);
    window.location.hash = key;
    window.scrollTo({ top: 0 });
  }

  // 1) Ek baar (ya Refresh dabane par) load hone wala data
  useEffect(() => {
    setBackendError("");
    const jobs = [
      api("/analytics/summary").then(setSummary).catch((e) => setBackendError(e.message)),
      api("/analytics/data-range").then(setDataRange).catch(() => setDataRange(null)),
      api("/graph").then(setGraph).catch(() => {}),
      api("/ml/anomalies?limit=500").then(setAnomalies).catch(() => {}),
      api("/ai/status").then(setAiStatus).catch(() => {}),
      api("/ai/recommendations?limit=200")
        .then((list) => setRecs(Object.fromEntries(list.map((r) => [r.anomaly_id, r]))))
        .catch(() => {}),
    ];
    // Sab data aa jaye tab "Updated" ka time dikhao aur button wapas normal karo
    Promise.allSettled(jobs).then(() => {
      setLastUpdated(new Date());
      setRefreshing(false);
    });
  }, [refreshKey]);

  // Governance: report, status aur scan history (har 60 second mein khud refresh, taaki autonomous scans dikhein)
  const loadGovernance = useCallback(() => {
    api("/governance/status").then(setGovStatus).catch(() => setGovStatus(null));
    api("/governance/report").then(setGovReport).catch(() => setGovReport(null));
    api("/governance/scans?limit=8").then(setGovScans).catch(() => setGovScans([]));
  }, []);

  useEffect(() => {
    loadGovernance();
    const timer = setInterval(loadGovernance, 60000);
    return () => clearInterval(timer);
  }, [loadGovernance, refreshKey]);

  async function govAction(request) {
    setGovBusy(true);
    setGovError("");
    try {
      await request();
      loadGovernance();
      setRefreshKey((k) => k + 1); // logs badle ho sakte hain, isliye baaki data bhi dobara
    } catch (e) {
      setGovError(e.message);
    } finally {
      setGovBusy(false);
    }
  }
  const runScan = () => govAction(() => api("/governance/scan", { method: "POST" }));
  const seedDemo = () => govAction(() => api("/governance/seed-demo", { method: "POST" }));
  const removeDemo = () => govAction(() => api("/governance/seed-demo", { method: "DELETE" }));

  // 2) Health: time range badalne par dobara
  useEffect(() => {
    api("/analytics/health?hours=" + hours).then(setHealth).catch(() => {});
  }, [hours, refreshKey]);

  const realHealth = useMemo(() => health.filter((h) => isRealService(h.service_name)), [health]);
  const realAnomalies = useMemo(() => anomalies.filter((a) => isRealService(a.service_name)), [anomalies]);

  useEffect(() => {
    if (selectedId === null && realHealth.length > 0) {
      const withData = realHealth.find((h) => h.total_requests > 0) || realHealth[0];
      setSelectedId(withData.service_id);
    }
  }, [realHealth, selectedId]);

  useEffect(() => {
    if (selectedAnomaly === null && realAnomalies.length > 0) setSelectedAnomaly(realAnomalies[0].id);
  }, [realAnomalies, selectedAnomaly]);

  // 3) Charts aur endpoints ka data
  useEffect(() => {
    if (selectedId === null) return;
    setSeriesLoading(true);
    api(`/analytics/services/${selectedId}/timeseries?hours=${hours}&interval_minutes=${pickInterval(hours)}`)
      .then(setSeries)
      .catch(() => setSeries([]))
      .finally(() => setSeriesLoading(false));
    api(`/analytics/services/${selectedId}/endpoints?hours=${hours}`)
      .then(setEndpoints)
      .catch(() => setEndpoints([]));
  }, [selectedId, hours, refreshKey]);

  const graphData = useMemo(() => {
    const nodes = graph.nodes.filter((n) => isRealService(n.name));
    const ids = new Set(nodes.map((n) => n.id));
    const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return { nodes, edges };
  }, [graph]);

  const healthById = useMemo(() => Object.fromEntries(realHealth.map((h) => [h.service_id, h])), [realHealth]);

  const anomalyCountById = useMemo(() => {
    const m = {};
    realAnomalies.forEach((a) => (m[a.service_id] = (m[a.service_id] || 0) + 1));
    return m;
  }, [realAnomalies]);

  const anomalyCounts = useMemo(() => {
    const m = {};
    realAnomalies.forEach((a) => (m[a.service_name] = (m[a.service_name] || 0) + 1));
    return Object.entries(m)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, [realAnomalies]);

  const selectedService = realHealth.find((h) => h.service_id === selectedId);
  const serviceAnomalies = realAnomalies.filter((a) => a.service_id === selectedId);
  const recCount = realAnomalies.filter((a) => recs[a.id]).length;

  function openAnomaly(id) {
    setSelectedAnomaly(id);
    navigate("ai");
  }

  async function recommend(id, force) {
    setBusyId(id);
    setAiError("");
    try {
      const rec = await api(`/ai/recommend/${id}?force=${force}`, { method: "POST" });
      setRecs((r) => ({ ...r, [id]: rec }));
    } catch (e) {
      setAiError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function recommendTop() {
    setTopBusy(true);
    setAiError("");
    try {
      const list = await api("/ai/recommend-top?limit=5", { method: "POST" });
      setRecs((r) => ({ ...r, ...Object.fromEntries(list.map((x) => [x.anomaly_id, x])) }));
    } catch (e) {
      setAiError(e.message);
    } finally {
      setTopBusy(false);
    }
  }

  const info = PAGE_INFO[page];
  const dataText = dataRange?.first_log ? `Data: ${fmtDate(dataRange.first_log)} to ${fmtDate(dataRange.last_log)}` : "";

  return (
    <div className="app">
      <Sidebar page={page} onNavigate={navigate} connected={!backendError && summary !== null} dataText={dataText} />

      <main className="main">
        <header className="page-head">
          <div>
            <h1>{info.title}</h1>
            <p>{info.sub}</p>
          </div>
          <div className="controls">
            {(page === "overview" || page === "monitoring") && (
              <select value={range} onChange={(e) => setRange(e.target.value)}>
                {RANGES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
              </select>
            )}
            {lastUpdated && (
              <span className="muted small">Updated {lastUpdated.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
            )}
            <button
              className="primary"
              disabled={refreshing}
              title="Fetch the latest data from the backend"
              onClick={() => {
                setRefreshing(true);
                setRefreshKey((k) => k + 1);
              }}
            >
              <RefreshCw size={16} className={refreshing ? "spin" : ""} /> {refreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </header>

        {backendError && (
          <div className="notice error">
            Cannot reach the backend ({backendError}). Is the server running? Open http://127.0.0.1:8000/docs to check.
          </div>
        )}

        {page === "overview" && (
          <div className="page">
            <Explain>
              This dashboard watches {realHealth.length || "your"} microservices. It collects their API logs, measures how healthy each
              one is, maps who calls whom, finds unusual behaviour with machine learning, suggests fixes with AI, and checks the whole system against its documented
              design. The strip below shows that whole journey from raw data to advice.
            </Explain>

            <Pipeline
              steps={[
                { icon: Inbox, tag: "Collect", title: "Logs collected", value: summary ? summary.total_requests : null, unit: "calls", color: "linear-gradient(135deg,#6366f1,#8b5cf6)" },
                { icon: BarChart3, tag: "Monitor", title: "Services monitored", value: realHealth.length, unit: "services", color: "linear-gradient(135deg,#06b6d4,#3b82f6)" },
                { icon: Network, tag: "Map", title: "Links mapped", value: graphData.edges.length, unit: "links", color: "linear-gradient(135deg,#10b981,#06b6d4)" },
                { icon: Brain, tag: "Detect", title: "Anomalies detected", value: realAnomalies.length, unit: "by ML", color: "linear-gradient(135deg,#f59e0b,#f97316)" },
                { icon: Sparkles, tag: "Advise", title: "AI advice", value: recCount, unit: "generated", color: "linear-gradient(135deg,#ec4899,#8b5cf6)" },
                { icon: Scale, tag: "Govern", title: "Governance issues", value: govReport && govReport.scan ? govReport.scan.summary.total_findings : null, unit: "found", color: "linear-gradient(135deg,#0ea5e9,#6366f1)" },
              ]}
            />

            <StatCards summary={summary} serviceCount={realHealth.length} anomalyCount={realAnomalies.length} />

            <GovernanceSummary report={govReport} onOpen={() => navigate("governance")} />

            <div className="grid-2">
              <HealthDonut rows={realHealth} />
              <AnomaliesByService counts={anomalyCounts} />
            </div>

            <TopAnomalies items={realAnomalies.slice(0, 5)} recs={recs} onOpen={openAnomaly} />
          </div>
        )}

        {page === "monitoring" && (
          <div className="page">
            <Explain>
              Every service writes a log line for each API call. From those logs we calculate the average and p95 response time
              (p95 means 95% of requests were faster than this) and the error rate. A service turns Warning or Critical when these
              numbers cross a limit.
            </Explain>
            <HealthTable rows={realHealth} selectedId={selectedId} onSelect={setSelectedId} rangeLabel={rangeLabel} />
            <TrendCharts
              series={series}
              anomalies={serviceAnomalies}
              services={realHealth}
              selectedId={selectedId}
              onSelect={setSelectedId}
              loading={seriesLoading}
            />
            <EndpointTable rows={endpoints} serviceName={selectedService?.service_name} />
          </div>
        )}

        {page === "graph" && (
          <div className="page">
            <Explain>
              Microservices call each other. If one service goes down, every service that depends on it can fail too. The arrows
              show who calls whom, and a thicker arrow means more calls. Click a service to see its impact.
            </Explain>
            <DependencyGraph
              nodes={graphData.nodes}
              edges={graphData.edges}
              healthById={healthById}
              anomalyCountById={anomalyCountById}
              selected={selectedNode}
              onSelect={setSelectedNode}
            />
          </div>
        )}

        {page === "governance" && (
          <div className="page">
            <Explain>
              Over time microservice systems drift away from their design: APIs that nobody uses any more, calls between services
              that were never documented, broken or slow endpoints, and risky access patterns. This page scans the logs, compares
              what really happens with what is documented, and lists every problem with a fix. The scan also runs by itself on a
              timer, so new problems show up without anyone pressing a button.
            </Explain>
            <GovernancePage
              status={govStatus}
              report={govReport}
              scans={govScans}
              busy={govBusy}
              error={govError}
              onScan={runScan}
              onSeed={seedDemo}
              onRemoveSeed={removeDemo}
            />
          </div>
        )}

        {page === "ai" && (
          <div className="page">
            <Explain>
              A machine learning model (Isolation Forest) learned what normal traffic looks like and flagged 5-minute windows that look
              very different. Select one, then ask the AI to explain the likely cause, the impact on other services, and how to fix it.
            </Explain>
            <AiPage
              anomalies={realAnomalies}
              recs={recs}
              aiStatus={aiStatus}
              busyId={busyId}
              topBusy={topBusy}
              aiError={aiError}
              onRecommend={recommend}
              onRecommendTop={recommendTop}
              selectedId={selectedAnomaly}
              onSelect={setSelectedAnomaly}
            />
          </div>
        )}

        <footer className="footer">AI-Powered API and Microservice Governance Engine</footer>
      </main>
    </div>
  );
}