import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', // ⬅️ required for Docker to expose to your host browser
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://backend:8000', // ⬅️ Docker service name, not localhost
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: '/frontend/dist',
  },
});
