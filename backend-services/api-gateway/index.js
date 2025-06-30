// backend-services/api-gateway/index.js
require('dotenv').config({ path: '../../.env' });
const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();
const PORT = process.env.API_GATEWAY_PORT || 3000;

// Proxy configuration
const services = [
  {
    route: '/screen',
    target: process.env.SCREENING_SERVICE_URL || 'http://screening-service:3002',
  },
  {
    route: '/analyze',
    target: process.env.ANALYSIS_SERVICE_URL || 'http://analysis-service:3003',
  },
];

services.forEach(({ route, target }) => {
  app.use(route, createProxyMiddleware({
    target,
    changeOrigin: true,
    pathRewrite: {
      [`^${route}`]: '', // remove base path
    },
  }));
});

app.listen(PORT, () => {
  console.log(`API Gateway listening on port ${PORT}`);
});