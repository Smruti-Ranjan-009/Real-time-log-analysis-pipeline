import { AlertTriangle, AlertCircle, Info, Clock, TrendingUp } from 'lucide-react'

function Card({ label, value, sub, icon: Icon, color }) {
  return (
    <div className="card flex items-start gap-3">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${color}`}>
        <Icon size={16} />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-slate-500 truncate">{label}</p>
        <p className="text-xl font-bold text-white mt-0.5">{value ?? '—'}</p>
        {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

export default function StatsCards({ stats }) {
  if (!stats) return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      {Array(5).fill(0).map((_, i) => (
        <div key={i} className="card h-20 animate-pulse bg-border/20" />
      ))}
    </div>
  )

  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <Card
        label="Total Logs (1h)"
        value={stats.total_1h?.toLocaleString()}
        icon={TrendingUp}
        color="bg-slate-700/50 text-slate-300"
      />
      <Card
        label="Errors"
        value={stats.errors_1h?.toLocaleString()}
        sub={`${stats.total_1h ? ((stats.errors_1h / stats.total_1h) * 100).toFixed(1) : 0}% of total`}
        icon={AlertCircle}
        color="bg-red-500/15 text-red-400"
      />
      <Card
        label="Warnings"
        value={stats.warnings_1h?.toLocaleString()}
        sub={`${stats.total_1h ? ((stats.warnings_1h / stats.total_1h) * 100).toFixed(1) : 0}% of total`}
        icon={AlertTriangle}
        color="bg-amber-500/15 text-amber-400"
      />
      <Card
        label="Info"
        value={stats.info_1h?.toLocaleString()}
        icon={Info}
        color="bg-blue-500/15 text-blue-400"
      />
      <Card
        label="Avg Parse Latency"
        value={stats.avg_parse_ms != null ? `${stats.avg_parse_ms} ms` : '—'}
        sub={`p95: ${stats.p95_parse_ms ?? '—'} ms`}
        icon={Clock}
        color="bg-emerald-500/15 text-emerald-400"
      />
    </div>
  )
}
