import { defineConfig } from 'vite';

// Port 5173 belongs to another app: never fall back to it.
export default defineConfig({
  server: { port: 5174, strictPort: true, fs: { allow: ['..'] } },
});
