// frontend-app/vitest.config.js

import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import eslint from 'vite-plugin-eslint';

export default defineConfig(({ mode, command }) => ({
  root: __dirname,

  // Vite plugins (for dev server and build)
  plugins: [
    react(),
    ...(command === 'serve'
      ? [
          eslint({
            cache: false,
            include: ['src/**/*.js', 'src/**/*.jsx'],
            exclude: ['node_modules', 'dist', '**/*.config.js'],
            // Only fail on errors in CI, not during dev
            failOnError: mode === 'production',
            failOnWarning: false,
          }),
        ]
      : []),
  ],

  // Vite dev server configuration
  server: {
    port: 5173,
    open: false,
  },

  // Build configuration
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        strict: true,
      },
    },
    sourcemap: mode === 'development',
  },

  // ESBuild configuration (for faster builds)
  esbuild: {
    jsxInject: `import React from 'react'`,
  },

  // Vitest configuration
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.js',
    css: true,
    
    // use threads pool with higher timeout for heavy setup
    pool: 'threads',
    poolOptions: {
      threads: {
        singleThread: false,
      },
    },
    testTimeout: 10000, // 10s per test instead of default 5s
    
    include: ['src/**/*.test.{js,jsx,ts,tsx}'],
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
