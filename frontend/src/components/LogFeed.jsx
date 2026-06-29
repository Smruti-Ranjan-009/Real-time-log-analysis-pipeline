import { useEffect, useRef } from 'react'
import { RefreshCw } from 'lucide-react'

const LEVEL_STYLE = {
  ERROR:   'badge-error',
  WARN:    'badge-warn',
  INFO:    'badge-info',
  DEBUG:   'badge-debug',
  UNKNOWN: 'badge-unknown',
}

const ROW_BG = {
  ERROR: 'border-l-2 border-red-500/40 bg-red-500/5',
  WARN:  'border-l-2 border-amber-500/40 bg-amber-500/5',
  INFO:  'border-l-2 border-transparent',
  DEBUG: 'border-l-2 border-transparent',
}

function fmt(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('en-GB', { hour12: false })
  } catch {
    return ts.slice(11, 19)
  }
}

export default function LogFeed({ logs, loading, levelFilter, onLevelChange }) {
  const bottomRef = useRef(null)
  const containerRef = useRef(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
    if (isAtBottom) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs])

  const levels = ['ALL', 'ERROR', 'WARN', 'INFO', 'DEBUG']

  return (
    <div className="card flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <h2 className="text-sm font-semibold text-white">Live Log Feed</h2>
          {loading && <RefreshCw size={11} className="text-slate-500 animate-spin" />}
        </div>
        {/* Level filter pills */}
        <div className="flex gap-1">
          {levels.map(l => (
            <button
              key={l}
              onClick={() => onLevelChange(l === 'ALL' ? null : l)}
              className={`text-xs px-2 py-0.5 rounded transition-all ${
                (l === 'ALL' && !levelFilter) || l === levelFilter
                  ? 'bg-accent text-white'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {/* Log rows */}
      <div className="flex-1 overflow-y-auto space-y-0.5 font-mono text-xs min-h-0">
        {!logs?.length && (
          <div className="text-slate-600 text-center py-8">
            No logs yet — start the generator
          </div>
        )}
        {logs?.map((log, i) => (
          <div
            key={log.id ?? i}
            className={`flex gap-2 items-start px-2 py-1.5 rounded ${ROW_BG[log.level] || 'border-l-2 border-transparent'} hover:bg-white/5 transition-colors`}
          >
            <span className="text-slate-600 flex-shrink-0 w-16">{fmt(log.timestamp)}</span>
            <span className={`flex-shrink-0 ${LEVEL_STYLE[log.level] || 'badge-unknown'}`}>
              {log.level}
            </span>
            <span className="text-indigo-400 flex-shrink-0 truncate max-w-[90px]">{log.service}</span>
            <span className="text-slate-300 truncate flex-1">{log.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
