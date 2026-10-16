const BASE = import.meta.env.VITE_API_BASE_URL || '/api'
const TOKEN_KEY = 'northline_token'
const OPS_KEY = 'northline_ops_token'

export function money(cents) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format((cents || 0) / 100)
}

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) sessionStorage.setItem(TOKEN_KEY, token)
  else sessionStorage.removeItem(TOKEN_KEY)
}

export function getOpsToken() {
  return sessionStorage.getItem(OPS_KEY) || ''
}

export function setOpsToken(token) {
  if (token) sessionStorage.setItem(OPS_KEY, token)
  else sessionStorage.removeItem(OPS_KEY)
}

export function productImage(file) {
  return `/products/${file}`
}

function errorMessage(data, status) {
  if (!data) return `Request failed (${status})`
  if (typeof data.detail === 'string') return data.detail
  if (data.detail && typeof data.detail.message === 'string') return data.detail.message
  if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg).join(' ')
  return `Request failed (${status})`
}

export async function api(path, { method = 'GET', body, headers = {}, token = getToken() } = {}) {
  const requestHeaders = { ...headers }
  if (body !== undefined) requestHeaders['Content-Type'] = 'application/json'
  if (token) requestHeaders.Authorization = `Bearer ${token}`
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: requestHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) {
    const error = new Error(errorMessage(data, response.status))
    error.status = response.status
    error.data = data
    throw error
  }
  return data
}
