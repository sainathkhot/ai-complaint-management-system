/**
 * Thin fetch wrapper around the complaint API.
 *
 * Every mutating call returns the complete complaint state, which Redux then
 * swaps in wholesale. There is no client-side merging of AI output — the
 * backend graph owns that logic, and the UI is a pure render of what it sends.
 */

const BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  createComplaint: () => request('/api/complaints', { method: 'POST' }),

  getComplaint: (id) => request(`/api/complaints/${id}`),

  /**
   * The single endpoint that drives the app. Text and file travel together as
   * multipart because from the graph's perspective they are the same event.
   */
  sendMessage: (id, { message = '', file = null } = {}) => {
    const body = new FormData()
    body.append('message', message)
    if (file) body.append('file', file)
    return request(`/api/complaints/${id}/message`, { method: 'POST', body })
  },

  resetComplaint: (id) => request(`/api/complaints/${id}/reset`, { method: 'POST' }),

  saveComplaint: (id) => request(`/api/complaints/${id}/save`, { method: 'POST' }),

  getAuditTrail: (id) => request(`/api/complaints/${id}/audit`),

  health: () => request('/api/health'),
}
