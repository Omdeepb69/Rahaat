/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

function checkApiBase(mode: string, command: string): void {
  if (command !== 'build' || mode === 'test') return;
  const value = loadEnv(mode, process.cwd(), 'VITE_').VITE_API_BASE_URL ?? process.env.VITE_API_BASE_URL;
  if (!value) {
    throw new Error('VITE_API_BASE_URL must be set for a production build (the HTTPS address of the RAAHAT API).');
  }
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`VITE_API_BASE_URL is not a valid URL: ${value}`);
  }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.protocol !== 'https:' && !local) {
    throw new Error(`VITE_API_BASE_URL must use https outside local testing (got ${url.origin}).`);
  }
}

export default defineConfig(({ mode, command }) => {
  checkApiBase(mode, command);
  return {
    plugins: [react()],
    server: { port: 5173, strictPort: true },
    preview: { port: 4173, strictPort: true },
    build: {
      target: 'es2022',
      sourcemap: true,
      chunkSizeWarningLimit: 400,
      assetsInlineLimit: (file: string) => (/\.(woff2?|ttf|otf)$/.test(file) ? false : undefined),
    },
    test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], css: false },
  };
});
