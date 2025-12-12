// frontend-app/src/setupTests.js

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
});

// ---- Browser API Polyfills (for Chakra UI & charts) ----

// matchMedia (required by Chakra UI for color mode / responsive styles)
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

// IntersectionObserver (not available in jsdom)
if (!global.IntersectionObserver) {
  global.IntersectionObserver = class IntersectionObserver {
    constructor() {}
    disconnect() {}
    observe() {}
    unobserve() {}
    takeRecords() {
      return [];
    }
  };
}

// ResizeObserver (for charting & Chakra layout)
if (!global.ResizeObserver) {
  global.ResizeObserver = class ResizeObserver {
    constructor() {}
    disconnect() {}
    observe() {}
    unobserve() {}
  };
}

// ---- Focus polyfill to avoid jsdom focus getter/setter errors ----
if (typeof window !== 'undefined' && window.HTMLElement) {
  const desc = Object.getOwnPropertyDescriptor(
    window.HTMLElement.prototype,
    'focus',
  );

  // If jsdom provides focus as a problematic getter-only property, override it
  if (!desc || typeof desc.get === 'function') {
    Object.defineProperty(window.HTMLElement.prototype, 'focus', {
      configurable: true,
      writable: true,
      value: function focus() {
        // no-op in tests; jsdom doesn't manage real focus anyway
      },
    });
  }
}
