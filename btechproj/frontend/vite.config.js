import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Helper function for proxying API endpoints while serving index.html for browser navigation and refreshes
const createApiProxyRule = (target = 'http://localhost:8010') => ({
  target,
  changeOrigin: true,
  bypass(req) {
    const accept = req.headers.accept || ''
    const isDoc = req.headers['sec-fetch-dest'] === 'document' || req.headers['sec-fetch-mode'] === 'navigate'
    const isHtml = accept.includes('text/html') || accept.includes('application/xhtml+xml')

    // Bypass proxying for browser page navigations and refreshes so Vite serves index.html for React Router
    if (isDoc || isHtml) {
      return '/index.html'
    }
  },
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/incidents': createApiProxyRule(),
      '/services': createApiProxyRule(),
      '/dashboard': createApiProxyRule(),
      '/investigations': createApiProxyRule(),
      '/health': createApiProxyRule(),
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    port: 5173,
    host: true,
    proxy: {
      '/incidents': createApiProxyRule(),
      '/services': createApiProxyRule(),
      '/dashboard': createApiProxyRule(),
      '/investigations': createApiProxyRule(),
      '/health': createApiProxyRule(),
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})

