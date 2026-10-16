import axios from 'axios';

// 1. Read backend base URL from environment variable or fallback to backend Docker port 8010
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8010';

// 2. Create reusable Axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for logging & auth headers
api.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => {
    console.error('[Axios Request Error]', error);
    return Promise.reject(error);
  }
);

// Response interceptor for standardized error handling & logging
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Log API failures to console without swallowing error silently
    console.error(
      `[Axios Response Error] Endpoint: ${error.config?.method?.toUpperCase()} ${error.config?.url} | Error:`,
      error.response ? `${error.response.status} - ${error.response.statusText}` : error.message
    );
    return Promise.reject(error);
  }
);

export default api;
