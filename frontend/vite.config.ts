import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // React core libraries
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          // Data fetching and virtualization
          'vendor-query': ['@tanstack/react-query', '@tanstack/react-virtual'],
          // UI icons library
          'vendor-ui': ['lucide-react'],
          // Utility libraries
          'vendor-utils': ['axios', 'date-fns'],
        },
      },
    },
    // Warn if chunk exceeds 500kb
    chunkSizeWarningLimit: 500,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
