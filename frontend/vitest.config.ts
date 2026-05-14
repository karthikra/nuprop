import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// A dedicated Vitest config (Vitest prefers this over vite.config.ts) so the
// Tailwind plugin and dev-server proxy don't run during tests.
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: [
        'node_modules/',
        'dist/',
        'src/test/',
        'src/main.tsx',
        'src/App.tsx',
        '**/*.config.*',
        '**/*.d.ts',
        'src/types/**',
      ],
    },
  },
})
