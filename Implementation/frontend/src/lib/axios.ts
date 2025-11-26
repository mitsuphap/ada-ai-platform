import axios from 'axios'

const api = axios.create({
  baseURL: '/api',  // Uses Vite proxy to forward to http://localhost:8000
  headers: {
    'Content-Type': 'application/json',
  },
})

// Optional: Add request interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default api

