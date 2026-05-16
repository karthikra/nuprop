import axios from 'axios'

export const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('nuprop_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('nuprop_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

/**
 * Normalise an axios error into a user-facing message string.
 *
 * FastAPI returns `detail` as either:
 *   - a string (HTTPException with a string detail, our usual 4xx shape), or
 *   - an array of {type, loc, msg, input, ctx} objects (Pydantic 422 validation errors).
 *
 * Naively rendering `err.response.data.detail` into JSX crashes React (error #31)
 * when the array form is returned. This helper picks the string path,
 * concatenates the `msg` fields from the array path, and falls back to
 * the caller's fallback string for everything else.
 */
export function formatApiError(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
      .filter(Boolean)
    if (msgs.length) return msgs.join('; ')
  }
  return fallback
}
