import { extendTheme } from '@chakra-ui/react';

const config = {
  initialColorMode: 'dark',
  useSystemColorMode: false,
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