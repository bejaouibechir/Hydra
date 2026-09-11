import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

export default defineConfig({
  integrations: [react()],

  site: 'https://hydraetl.com',
  output: 'static',
  outDir: './dist',
  publicDir: './public',
  base: '/',

  vite: {
    build: {
      rollupOptions: {
        output: {
          manualChunks: (id) => {
            if (id.includes('node_modules')) return 'vendor';
            if (id.includes('HydraCore')) return 'hydra-core';
          }
        }
      }
    }
  }
});
