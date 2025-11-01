import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import eslint from 'vite-plugin-eslint';

export default defineConfig(({ mode }) => ({
  // Vite plugins (for dev server and build)
  plugins: [
    react(),
    eslint({
      cache: false,
      include: ['src/**/*.js', 'src/**/*.jsx'],
      exclude: ['node_modules', 'dist', '**/*.config.js'],
      // Only fail on errors in CI, not during dev
      failOnError: mode === 'production',
      failOnWarning: false,
    }),
  ],

  // Vite dev server configuration
  server: {
    port: 5173,
    open: false, // Set to true to auto-open browser
  },

  // Build configuration
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        strict: true, // Enable JavaScript strict mode in production
      },
    },
    sourcemap: mode === 'development', // Source maps only in dev
  },

  // ESBuild configuration (for faster builds)
  esbuild: {
    jsxInject: `import React from 'react'`, // Auto-import React
  },

  // Vitest configuration
  test: {
    globals: true, // Use Vitest global APIs (describe, it, expect)
    environment: 'jsdom', // Simulate browser DOM for React components
    setupFiles: './src/setupTests.js', // Run setup before each test file
    css: true, // Process CSS imports in tests
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/setupTests.js',
        '**/*.config.js',
        'dist/',
      ],
    },
  },
}));