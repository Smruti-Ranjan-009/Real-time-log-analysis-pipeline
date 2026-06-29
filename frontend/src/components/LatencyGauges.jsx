import { Clock } from 'lucide-react'

const STAGES = [
  { key: 'ingest',   label: 'Ingest',    budget: 50,  color: 'bg-violet-500' },
  { key: 'kafka',    label: 'Kafka',     budget: 30,  color: 'bg-blue-500' },
  { key: 'parse',    label: 'Parse',     budget: 80,  color: 'bg-cyan-500' },
  { key: 'embed',    label: 'Embed',     budget: 60,  color: 'bg-indigo-500' },
  { key: 'llm',      label: 'LLM',       budget: 250, color: 'bg-amber-500' },
  { key: 'delivery', label: 'Delivery',  budget: 20,  color: 'bg-emerald-500' },
]

function Gauge({ stage, actual }) {
  const pct = actual != null ? Math.min((actual / stage.budget) * 100, 100) : null
  const over = actual != null && actual > stage.budget

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">{stage.label}</span>
        <div className="flex items-center gap-2 font-mono">
          <span className="text-slate-600">/{stage.budget}ms</span>
          <span className={actual != null ? (over ? 'text-red-400' : 'text-emerald-400') : 'text-slate-600'}>
            {actual != null ? `${actual.toFixed(1)}ms` : '—'}
          </span>
        </div>
      </div>
      <div className="h-1.5 bg-border rounded-full overflow-hidden">
        {pct != null && (
          <div
            className={`h-full rounded-full transition-all duration-500 ${over ? 'bg-red-500' : stage.color}`}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
    </div>
  )
}

export default function LatencyGauges({ slo, queryResult }) {
  // Merge SLO endpoint data with latest query result
  const actuals = {}
  if (slo?.stages) {
    Object.entries(slo.stages).forEach(([k, v]) => {
      actuals[k] = v?.p95_ms
    })
  }
  // Override with fresh query result if available
  if (queryResult) {
    if (queryResult.embed_ms)      actuals.embed    = queryResult.embed_ms
    if (queryResult.llm_ms)        actuals.llm      = queryResult.llm_ms
  }

  const totalBudget = STAGES.reduce((s, st) => s + st.budget, 0)
  const totalActual = queryResult?.total_latency_ms

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock size={14} className="text-accent" />
          <h2 className="text-sm font-semibold text-white">Latency Budget</h2>
        </div>
        <div className="text-xs font-mono">
          <span className={totalActual != null ? (totalActual > totalBudget ? 'text-red-400' : 'text-emerald-400') : 'text-slate-600'}>
            {totalActual != null ? `${totalActual.toFixed(0)}ms` : '—'}
          </span>
          <span className="text-slate-600"> / {totalBudget}ms</span>
        </div>
      </div>

      <div className="space-y-3">
        {STAGES.map(stage => (
          <Gauge key={stage.key} stage={stage} actual={actuals[stage.key]} />
        ))}
      </div>

      <p className="text-xs text-slate-600">
        Run a query to see live latency breakdown per stage.
        Red bar = SLO breach.
      </p>
    </div>
  )
}
