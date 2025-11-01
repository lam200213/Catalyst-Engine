// frontend-app/.eslintrc.cjs
// ESLint configuration for React + Vite

module.exports = {
  env: {
    browser: true,
    es2021: true,
  },
  overrides: [
    {
      files: ['**/*.test.js', '**/*.test.jsx', 'src/setupTests.js'],
      env: {
        node: true,
        jest: true,
      }
    },
    {
      files: ['**/*.cjs', 'scripts/**/*.js'],
      env: {
        node: true,
      }
    }
  ],
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
  ],
  parserOptions: {
    ecmaFeatures: {
      jsx: true,
    },
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  plugins: ['react', 'react-hooks'],
  rules: {
    'no-unreachable': 'error',
    'no-undef': 'error',
    'react/react-in-jsx-scope': 'off',
    'react/prop-types': 'off',  // REMOVED DUPLICATE - only this line
    'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    'no-console': ['warn', { allow: ['warn', 'error', 'log'] }],
  },
  settings: {
    react: {
      version: 'detect',
    },
  },
};
