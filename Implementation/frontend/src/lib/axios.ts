import axios from 'axios'

// Base URL comes from VITE_API_URL at build time. In local dev it falls back to
// the Vite proxy (`/api` -> http://localhost:8000, see vite.config.js).
const baseURL = import.meta.env.VITE_API_URL ?? '/api'

const api = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export default api
