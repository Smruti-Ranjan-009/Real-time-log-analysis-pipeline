import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { BarChart2 } from 'lucide-react'

const COLORS = {
  ERROR: '#ef4444',
  WARN:  '#f59e0b',
  INFO:  '#3b82f6',
  DEBUG: '#6b7280',
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-card border border-border rounded-lg px-3 py-2 text-xs">
      <p className="font-semibold text-white mb-1">{label}</p>
      {payload.map(p => (
        <p key={p.name} style={{ color: p.fill }}>{p.value.toLocaleString()} logs</p>
      ))}
    </div>
  )
}

export default function ErrorChart({ stats, history }) {
  // Build chart data from stats + accumulated history
  const data = history?.length > 0
    ? history
    : stats
      ? [
          { time: 'now', ERROR: stats.errors_1h, WARN: stats.warnings_1h, INFO: stats.info_1h, DEBUG: stats.debug_1h },
        ]
      : []

  if (!data.length) {
    return (
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <BarChart2 size={14} className="text-accent" />
          <h2 className="text-sm font-semibold text-white">Log Distribution</h2>
        </div>
        <div className="h-32 flex items-center justify-center text-slate-600 text-sm">
          Waiting for data…
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart2 size={14} className="text-accent" />
          <h2 className="text-sm font-semibold text-white">Log Distribution (last hour)</h2>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {Object.entries(COLORS).map(([level, color]) => (
            <div key={level} className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-sm" style={{ background: color }} />
              <span className="text-slate-500">{level}</span>
            </div>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
          <XAxis
            dataKey="time"
            tick={{ fill: '#64748b', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#64748b', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
          {Object.entries(COLORS).map(([level, color]) => (
            <Bar key={level} dataKey={level} stackId="a" fill={color} radius={level === 'DEBUG' ? [3, 3, 0, 0] : [0, 0, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
