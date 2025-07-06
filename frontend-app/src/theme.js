import { extendTheme } from '@chakra-ui/react';

const config = {
  initialColorMode: 'dark',
  useSystemColorMode: false,
};

// Centralized color configuration for the charting components.
export const chartColors = {
  background: 'rgb(26, 32, 44)',
  textColor: 'rgb(226, 232, 240)',
  grid: 'rgb(45, 55, 72)',
  crosshair: {
    price: 'rgb(160, 174, 192)',
    time: 'rgb(160, 174, 192)'
  },
  candlestick: {
    up: 'rgb(38, 166, 154)',
    down: 'rgb(239, 83, 80)'
  },
  volume: {
    base: 'rgb(74, 85, 104)',
    up: 'rgba(38, 166, 154, 0.5)',
    down: 'rgba(239, 83, 80, 0.5)',
    trendLine: 'rgb(229, 62, 62)'
  },
  ma: {
    // Named colors converted to RGB for consistency
    ma20: 'rgb(255, 192, 203)', // pink
    ma50: 'rgb(255, 0, 0)',      // red
    ma150: 'rgb(255, 165, 0)',   // orange
    ma200: 'rgb(0, 128, 0)',     // green
  },
  vcp: {
    line: 'rgb(80, 194, 239)',
    endPoint: 'rgb(80, 194, 239)'
  },
  pivots: {
    buy: 'rgb(76, 175, 80)',
    stopLoss: 'rgb(244, 67, 54)',
    lowVolume: 'rgb(255, 234, 0)'
  }
};

const styles = {
  global: {
    'html, body': {
      fontFamily: `'Inter', sans-serif`,
      lineHeight: '1.5',
      color: 'rgba(255, 255, 255, 0.87)',
      backgroundColor: 'rgb(26, 32, 44)',
    },
    body: {
      margin: 0,
      backgroundColor: 'rgb(26, 32, 44)',
      color: 'rgb(226, 232, 240)',
    },
    ':root': {
      fontSynthesis: 'none',
      textRendering: 'optimizeLegibility',
      WebkitFontSmoothing: 'antialiased',
      MozOsxFontSmoothing: 'grayscale',
    },
  },
};

const theme = extendTheme({ config, styles, colors: { ...chartColors } });

export default theme;