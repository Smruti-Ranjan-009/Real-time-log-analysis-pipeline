import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api'
import Header       from './components/Header'
import StatsCards   from './components/StatsCards'
import QueryBox     from './components/QueryBox'
import LogFeed      from './components/LogFeed'
import LatencyGauges from './components/LatencyGauges'
import ErrorChart   from './components/ErrorChart'

const STATS_INTERVAL = 10_000   // 10s
const LOGS_INTERVAL  = 3_000    // 3s
const MAX_HISTORY    = 20       // chart history points

export default function App() {
  const [healthy,      setHealthy]      = useState(null)
  const [stats,        setStats]        = useState(null)
  const [logs,         setLogs]         = useState([])
  const [logsLoading,  setLogsLoading]  = useState(false)
  const [levelFilter,  setLevelFilter]  = useState(null)
  const [queryResult,  setQueryResult]  = useState(null)
  const [queryLoading, setQueryLoading] = useState(false)
  const [slo,          setSlo]          = useState(null)
  const [indexStatus,  setIndexStatus]  = useState(null)
  const [chartHistory, setChartHistory] = useState([])

  const historyRef = useRef([])

  // ── Health check ──────────────────────────────────────────────────────────
  useEffect(() => {
    api.health()
      .then(() => setHealthy(true))
      .catch(() => setHealthy(false))
  }, [])

  // ── Stats polling ─────────────────────────────────────────────────────────
  const refreshStats = useCallback(async () => {
    try {
      const s = await api.stats()
      setStats(s)

      // Accumulate chart history
      const point = {
        time:  new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        ERROR: s.errors_1h   ?? 0,
        WARN:  s.warnings_1h ?? 0,
        INFO:  s.info_1h     ?? 0,
        DEBUG: s.debug_1h    ?? 0,
      }
      historyRef.current = [...historyRef.current.slice(-MAX_HISTORY + 1), point]
      setChartHistory([...historyRef.current])
    } catch (e) {
      console.warn('stats error', e)
    }
  }, [])

  useEffect(() => {
    refreshStats()
    const t = setInterval(refreshStats, STATS_INTERVAL)
    return () => clearInterval(t)
  }, [refreshStats])

  // ── Logs polling ──────────────────────────────────────────────────────────
  const refreshLogs = useCallback(async () => {
    setLogsLoading(true)
    try {
      const data = await api.logs(40, levelFilter)
      setLogs(data.logs ?? [])
    } catch (e) {
      console.warn('logs error', e)
    } finally {
      setLogsLoading(false)
    }
  }, [levelFilter])

  useEffect(() => {
    refreshLogs()
    const t = setInterval(refreshLogs, LOGS_INTERVAL)
    return () => clearInterval(t)
  }, [refreshLogs])

  // ── SLO + index status ────────────────────────────────────────────────────
  useEffect(() => {
    api.slo().then(setSlo).catch(() => {})
    api.indexStatus().then(setIndexStatus).catch(() => {})
    const t = setInterval(() => {
      api.slo().then(setSlo).catch(() => {})
      api.indexStatus().then(setIndexStatus).catch(() => {})
    }, 30_000)
    return () => clearInterval(t)
  }, [])

  // ── Query handler ─────────────────────────────────────────────────────────
  const handleQuery = useCallback(async (q) => {
    setQueryLoading(true)
    setQueryResult(null)
    try {
      const result = await api.query(q, levelFilter)
      setQueryResult(result)
      // Refresh SLO after query to get fresh latency data
      api.slo().then(setSlo).catch(() => {})
    } catch (e) {
      setQueryResult({ tier: 3, answer: `Error: ${e.message}`, sources: [] })
    } finally {
      setQueryLoading(false)
    }
  }, [levelFilter])

  return (
    <div className="min-h-screen bg-surface flex flex-col">
      <Header
        healthy={healthy}
        totalLogs={stats?.total_1h}
        indexedLogs={indexStatus?.total_indexed}
      />

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-6 space-y-4">

        {/* Row 1 — Stats */}
        <StatsCards stats={stats} />

        {/* Row 2 — Query */}
        <QueryBox
          onQuery={handleQuery}
          result={queryResult}
          loading={queryLoading}
        />

        {/* Row 3 — Log feed + Latency gauges */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" style={{ minHeight: '420px' }}>
          <div className="lg:col-span-2 flex flex-col min-h-0">
            <LogFeed
              logs={logs}
              loading={logsLoading}
              levelFilter={levelFilter}
              onLevelChange={setLevelFilter}
            />
          </div>
          <div className="flex flex-col">
            <LatencyGauges slo={slo} queryResult={queryResult} />
          </div>
        </div>

        {/* Row 4 — Chart */}
        <ErrorChart stats={stats} history={chartHistory} />

      </main>

      {/* Footer */}
      <footer className="border-t border-border py-3 px-6 text-center text-xs text-slate-700">
        RTLA · Kafka · FastAPI · Qdrant · Groq · Prometheus · React ·{' '}
        <a
          href="https://github.com/Smruti-Ranjan-009/Real-time-log-analysis-pipeline"
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent/60 hover:text-accent transition-colors"
        >
          GitHub
        </a>
      </footer>
    </div>
  )
}
