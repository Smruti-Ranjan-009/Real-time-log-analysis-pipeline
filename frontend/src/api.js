// All backend calls go through this module.
// VITE_API_URL is set to the HuggingFace Spaces URL in production.
// In local dev, Vite proxies /api → http://localhost:8001

const BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
  : '/api'

async function get(path) {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`)
  return r.json()
}

async function post(path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`POST ${path} → ${r.status}`)
  return r.json()
}

export const api = {
  health:      ()               => get('/health'),
  stats:       ()               => get('/stats'),
  slo:         ()               => get('/slo').catch(() => null),
  logs:        (limit = 30, level = null) =>
    get(level ? `/logs?limit=${limit}&level=${level}` : `/logs?limit=${limit}`),
  errors:      (limit = 10)    => get(`/logs/errors?limit=${limit}`),
  indexStatus: ()               => get('/index/status'),
  index:       (maxLogs = 500) => post(`/index?max_logs=${maxLogs}`, {}),
  query: (query, level) => post('/query', level ? { query, level_filter: level } : { query }),
}
