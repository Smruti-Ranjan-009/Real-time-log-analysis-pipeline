import { Activity, Zap } from 'lucide-react'

export default function Header({ healthy, totalLogs, indexedLogs }) {
  return (
    <header className="border-b border-border bg-card/50 backdrop-blur sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent/20 border border-accent/40 flex items-center justify-center">
            <Zap size={16} className="text-accent" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-wide text-white">RTLA</h1>
            <p className="text-xs text-slate-500 leading-none">Real-Time Log Intelligence</p>
          </div>
        </div>

        {/* Phase badges */}
        <div className="hidden sm:flex items-center gap-2">
          {['Kafka + FastAPI', 'Qdrant + Groq', 'Prometheus SLOs', 'React UI'].map((p, i) => (
            <span
              key={i}
              className="text-xs px-2 py-1 rounded border border-accent/30 bg-accent/10 text-accent/80"
            >
              P{i + 1} {p}
            </span>
          ))}
        </div>

        {/* Status */}
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${healthy ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
            {healthy ? 'Live' : 'Offline'}
          </div>
          <div className="hidden sm:flex items-center gap-1">
            <Activity size={12} />
            <span>{totalLogs?.toLocaleString() ?? '—'} logs</span>
          </div>
          <div className="hidden sm:flex items-center gap-1 text-indigo-400">
            <Zap size={12} />
            <span>{indexedLogs?.toLocaleString() ?? '—'} indexed</span>
          </div>
        </div>
      </div>
    </header>
  )
}
