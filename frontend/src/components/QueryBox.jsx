import { useState } from 'react'
import { Search, Loader2, ChevronDown, ChevronUp, Zap, AlertTriangle, Database } from 'lucide-react'

const TIER_CONFIG = {
  1: { label: 'Full RAG', color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/30', Icon: Zap },
  2: { label: 'Retrieval only', color: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/30', Icon: AlertTriangle },
  3: { label: 'Cached', color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30', Icon: Database },
}

const EXAMPLE_QUERIES = [
  'What caused the payment service errors?',
  'Which services are hitting circuit breakers?',
  'Show me all slow database query warnings',
  'What is the most frequent error pattern?',
]

export default function QueryBox({ onQuery, result, loading }) {
  const [input, setInput]           = useState('')
  const [showSources, setShowSources] = useState(false)

  function submit(q) {
    const query = (q || input).trim()
    if (!query) return
    setInput(query)
    setShowSources(false)
    onQuery(query)
  }

  const tier = result?.tier
  const TierIcon = tier ? TIER_CONFIG[tier]?.Icon : null

  return (
    <div className="card space-y-3">
      <h2 className="text-sm font-semibold text-white">Natural Language Query</h2>

      {/* Input */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            placeholder="Ask anything about your logs…"
            className="w-full bg-surface border border-border rounded-lg pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-accent transition-colors"
          />
        </div>
        <button
          onClick={() => submit()}
          disabled={loading || !input.trim()}
          className="px-4 py-2 bg-accent hover:bg-accent/80 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
          Ask
        </button>
      </div>

      {/* Example queries */}
      <div className="flex flex-wrap gap-2">
        {EXAMPLE_QUERIES.map(q => (
          <button
            key={q}
            onClick={() => submit(q)}
            className="text-xs px-2.5 py-1 rounded-full border border-border text-slate-500 hover:text-slate-300 hover:border-slate-500 transition-colors"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Result */}
      {result && (
        <div className="space-y-2">
          {/* Tier badge + latency */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            {tier && (
              <div className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${TIER_CONFIG[tier].bg}`}>
                <TierIcon size={11} className={TIER_CONFIG[tier].color} />
                <span className={TIER_CONFIG[tier].color}>{TIER_CONFIG[tier].label}</span>
              </div>
            )}
            <div className="flex items-center gap-3 text-xs text-slate-500 font-mono">
              {result.embed_ms      != null && <span>embed {result.embed_ms}ms</span>}
              {result.retrieval_ms  != null && <span>retrieval {Math.round(result.retrieval_ms - (result.embed_ms || 0))}ms</span>}
              {result.llm_ms        != null && <span>llm {result.llm_ms}ms</span>}
              {result.total_latency_ms != null && (
                <span className="text-white font-semibold">total {result.total_latency_ms}ms</span>
              )}
            </div>
          </div>

          {/* Answer */}
          <div className="bg-surface rounded-lg p-3 text-sm text-slate-200 leading-relaxed whitespace-pre-wrap border border-border">
            {result.answer}
          </div>

          {/* Sources toggle */}
          {result.sources?.length > 0 && (
            <div>
              <button
                onClick={() => setShowSources(v => !v)}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                {showSources ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                {result.sources.length} source logs
              </button>
              {showSources && (
                <div className="mt-2 space-y-1 font-mono text-xs">
                  {result.sources.map((s, i) => (
                    <div key={i} className="flex gap-2 bg-surface rounded px-2 py-1.5 border border-border">
                      <span className="text-slate-600 flex-shrink-0">#{i + 1}</span>
                      <span className="text-slate-500 flex-shrink-0">{(s.score * 100).toFixed(0)}%</span>
                      <span className={`flex-shrink-0 badge-${s.level?.toLowerCase()}`}>{s.level}</span>
                      <span className="text-indigo-400 flex-shrink-0">{s.service}</span>
                      <span className="text-slate-300 truncate">{s.message}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
