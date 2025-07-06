import { extendTheme } from '@chakra-ui/react';

const config = {
  initialColorMode: 'dark',
  useSystemColorMode: false,
};

// Centralized color configuration for the charting components.
export const chartColors = {
  background: '#1A202C',
  textColor: '#E2E8F0',
  grid: '#2D3748',
  crosshair: {
    price: '#C53030',
    time: '#A0AEC0'
  },
  candlestick: {
    up: '#26a69a',
    down: '#ef5350'
  },
  volume: {
    base: '#4A5568',
    up: 'rgba(38, 166, 154, 0.5)',
    down: 'rgba(239, 83, 80, 0.5)',
    trendLine: '#e53e3e'
  },
  ma: {
    ma20: 'pink',
    ma50: 'red',
    ma150: 'orange',
    ma200: 'green'
  },
  vcp: {
    line: '#ef5350'
  },
  pivots: {
    buy: '#4caf50',
    stopLoss: '#f44336',
    lowVolume: '#FFD700'
  }
};

const styles = {
  global: {
    'html, body': {
      fontFamily: `'Inter', sans-serif`,
      lineHeight: '1.5',
      color: 'rgba(255, 255, 255, 0.87)',
      backgroundColor: '#1A202C',
    },
    body: {
      margin: 0,
      backgroundColor: '#1A202C',
      color: '#E2E8F0',
    },
    ':root': {
      fontSynthesis: 'none',
      textRendering: 'optimizeLegibility',
      WebkitFontSmoothing: 'antialiased',
      MozOsxFontSmoothing: 'grayscale',
    },
  },
};

const theme = extendTheme({ config, styles });

export default theme;