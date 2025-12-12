# Frontend Architecture & Design Guidelines

This document serves as the single source of truth for the frontend architecture of the SEPA Stock Screener. It integrates standards from the UI/UX Specification, Phase 2 Technical Design, and TDD Blueprints.

## 1. Technology Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Core Framework** | React 18+ (Vite) | Component-based UI library |
| **Language** | JavaScript / TypeScript | Logic and Type definition (Mixed JS/TS codebase) |
| **UI Library** | Chakra UI | Accessible, composable component system |
| **State Management** | TanStack Query (React Query) | Server state, caching, and synchronization |
| **Routing** | React Router DOM | Client-side navigation |
| **HTTP Client** | Axios | API communication |
| **Charting** | TradingView Lightweight Charts | High-performance financial charts |
| **Testing** | Vitest, React Testing Library, @testing-library/user-event | Unit and Integration testing |
| **Build Tool** | Vite | Fast development and building |

## 2. Project Structure

The `frontend-app/src` directory follows a feature-based and functional organization pattern:

frontend-app/
├── scripts/
│ └── verify-structure.cjs # Directory structure verification
├── src/
│ ├── components/ # Reusable, "dumb" UI components 
│ │ ├── tests/ # Co-located component tests 
│ │ │ ├── fixtures/ # Test fixtures
│ │ │ │ └── watchlistFixtures.js # shared watchlist fixtures
│ │ │ ├── ArchivedWatchlistTable.test.jsx
│ │ │ ├── ChartLegend.test.jsx
│ │ │ ├── ChartPanel.test.jsx
│ │ │ ├── ScreeningPanel.test.jsx
│ │ │ ├── TickerForm.test.jsx
│ │ │ ├── AddWatchlistTickerForm.test.tsx
│ │ │ └── WatchlistTable.test.jsx
│ │ ├── ChartLegend.jsx # OHLCV + MA legend display
│ │ ├── ChartPanel.jsx # TradingView chart wrapper
│ │ ├── ErrorBoundary.jsx # React error boundary for crash protection
│ │ ├── LeadingIndustriesTable.jsx # Market leaders display
│ │ ├── MarketHealthCard.jsx # Market overview metrics
│ │ ├── ScreeningPanel.jsx # Screening results display
│ │ ├── Sidebar.jsx # Navigation sidebar
│ │ ├── WatchlistTable.tsx
│ │ ├── AddWatchlistTickerForm.tsx
│ │ └── TickerForm.jsx # Ticker input form
│ ├── hooks/ # Custom React hooks 
│ │ ├── tests/ # Co-located hook tests  
│ │ │ ├── useScreeningJobMutations.test.tsx 
│ │ │ ├── useStockData.test.js
│ │ │ ├── useWatchlistQuery.test.tsx
│ │ │ └── useWatchlistRefreshJobMutation.test.tsx.skip.tsx
│ │ ├── queryKeys.ts # Centralized React Query keys
│ │ ├── useMarketHealthQuery.js # Market health data fetching
│ │ ├── useScreeningJobMutations.ts # Watchlist CRUD mutations
│ │ ├── useStockData.js # Stock screening & analysis data
│ │ └── useWatchlistQuery.ts # Watchlist & archive queries
│ ├── pages/ # Top-level "smart" page components 
│ │ ├── tests/ 
│ │ │ ├── WatchlistPage.test.jsx
│ │ │ └── WatchlistPageRowActions.test.jsx
│ │ ├── DashboardPage.jsx # Legacy single-stock analysis page
│ │ ├── MarketPage.jsx # Market health & leaders
│ │ ├── PortfolioPage.jsx # Portfolio tracking (placeholder)
│ │ └── WatchlistPage.jsx # Watchlist management
│ ├── services/ # API communication layer 
│ │ ├── tests/ # Service unit tests 
│ │ │ ├── fixtures/ # Test fixtures
│ │ │ │ ├── httpFixtures.ts # Generic Axios response mocks
│ │ │ │ └── monitoringFixtures.ts # Monitoring API mocks
│ │ │ ├── monitoringApi.test.js
│ │ │ └── screeningApi.test.js
│ │ ├── mockData.js # Legacy mock data
│ │ ├── monitoringApi.d.ts # TypeScript declarations for monitoring API
│ │ ├── monitoringApi.js # Watchlist, archive, market health endpoints
│ │ ├── schedulerApi.js # Batch job endpoints
│ │ └── screeningApi.js # Stock screening & VCP analysis endpoints
│ ├── types/ # TypeScript definitions 
│ │ └── monitoring.ts # Mirrors backend Pydantic models
│ ├── App.jsx # Main routing logic
│ ├── App.test.jsx # App integration tests
│ ├── main.jsx # Application entry point
│ ├── sanity.test.js # Basic test harness verification
│ ├── setupTests.js # Global test configuration
│ ├── test-utils.jsx # Custom render helpers for tests
│ └── theme.js # Chakra UI theme + chart colors
├── .dockerignore
├── .eslintrc.cjs # ESLint configuration
├── docker-entrypoint.sh # Dev container entrypoint
├── Dockerfile # Production build
├── Dockerfile.dev # Development container
├── index.html # HTML entry point
├── nginx.conf # Production server config
├── package.json
├── tsconfig.json # TypeScript configuration
└── vitest.config.js # Vitest test runner config


## 3. Architectural Patterns

### 3.1. Smart vs. Dumb Components
*   **Smart Components (Pages/Containers):**
    *   Located in `src/pages/`.
    *   Responsible for **fetching data** (via Custom Hooks) and **managing page-level state**.
    *   Pass data down to dumb components via props.
    *   *Example:* `WatchlistPage.jsx` calls `useWatchlistQuery` and passes `items` to `WatchlistTable`.
*   **Dumb Components (UI):**
    *   Located in `src/components/`.
    *   Purely presentational. Receive data and callbacks via props.
    *   Do not make API calls directly.
    *   *Example:* `WatchlistTable.jsx` renders a table and triggers `onDelete(ticker)` when a button is clicked.

### 3.2. Data Layer & State Management
*   **Server State:** Handled exclusively by **TanStack Query v5**.
    *   **Queries:** Encapsulated in custom hooks (e.g., `useWatchlistQuery`). Keys must be strictly managed (e.g., `['monitoring', 'watchlist']`).
    *   **Query Keys:** Centralized in `src/hooks/queryKeys.ts` for consistency.
    *   **Mutations:** Encapsulated in hooks (e.g., `useScreeningJobMutations`). Responsible for invalidating query keys to trigger automatic UI refreshes.
*   **Local State:** Managed via `useState` or `useReducer` for ephemeral UI state (e.g., form inputs, modal visibility, selected table rows).

### 3.3. Service Layer
*   All HTTP requests are isolated in `src/services/`.
*   Functions return Axios response objects (unwrapped by hooks).
*   **Strict Contract Adherence:** The frontend must expect data shapes matching `shared/contracts.py`.
*   **Test Fixtures:** Centralized in `src/services/__tests__/fixtures/` for consistent mocking.

## 4. Actual Implementation Status

### 4.1. Implemented Components
| Component | Purpose | Test Coverage |
|:---|:---|:---:|
| `ChartLegend.jsx` | OHLCV + MA legend overlay | ✅ |
| `ChartPanel.jsx` | TradingView chart with VCP lines | ✅ |
| `ErrorBoundary.jsx` | React error boundary | ❌ |
| `LeadingIndustriesTable.jsx` | Market leaders display | ❌ |
| `MarketHealthCard.jsx` | Market metrics dashboard | ❌ |
| `ScreeningPanel.jsx` | Screening result display | ✅ |
| `Sidebar.jsx` | Navigation sidebar | ❌ |
| `TickerForm.jsx` | Ticker input form | ✅ |

### 4.2. Missing Implementations
**Note:** Tests exist for the following components, but implementations are missing:
- `WatchlistTable.jsx` - Watchlist items table
- `ArchivedWatchlistTable.jsx` - Archived items table

## 5. UI/UX Design System

### 5.1. Style Guide (Chakra UI)
*   **Color Palette:**
    *   **Primary Action:** `green.500` (Add, Buy, Positive P/L)
    *   **Destructive:** `red.500` (Delete, Sell, Negative P/L)
    *   **Neutral:** `blue.400` (Info, Loading)
    *   **Highlight:** `yellow.400` (Leadership stars, warnings)
    *   **Backgrounds:** `gray.800` (Page), `gray.700` (Cards/Tables)
*   **Typography:**
    *   Headings: `fontFamily="heading"`, `fontWeight="bold"`
    *   Tables: Headers `uppercase`, `semibold`; Cells `fontSize="sm"`

### 5.2. Chart Color Configuration
Centralized in `src/theme.js` under `chartColors`:
- Candlestick: Green (up) / Red (down)
- Volume: Green/Red with 0.5 opacity
- Moving Averages: Pink (MA20), Red (MA50), Orange (MA150), Green (MA200)
- VCP Lines: Light Blue
- Pivots: Green (buy), Red (stop loss), Yellow (low volume pivot)

## 6. Testing Strategy

Adheres to `FRONTEND_TESTING_STANDARD.md` and the TDD Blueprint.

### 6.1. Test Categories
1.  **Unit Tests:**
    *   Target: `src/services/`, `src/hooks/`, utility functions.
    *   Goal: Verify logic, API endpoint mapping, and state updates.
    *   Total: 6 test files (2 service, 4 hook tests)
2.  **Component Tests:**
    *   Target: `src/components/`.
    *   Goal: Verify rendering, conditional formatting (colors/badges), and user interaction (clicks).
    *   Total: 7 test files
    *   *Mocking:* Mock all child components and hooks if necessary.
3.  **Integration Tests:**
    *   Target: `src/pages/`, `App.jsx`.
    *   Goal: Verify full flows (Load Page -> API Mock -> Render -> User Action -> Mutation -> Re-render).
    *   Total: 2 test files

### 6.2. Workflow
*   **TDD:** Write tests *before* implementation for critical logic (hooks/services).
*   **Run Tests:** `npm test` (Watch mode).
*   **CI/CD:** All tests must pass before merge.
*   **Timeout:** 10 seconds per test (increased for heavy setup).

### 6.3. Test Utilities
- `src/test-utils.jsx` - Custom render helpers with all providers
- `src/setupTests.js` - Global mocks (IntersectionObserver, ResizeObserver)
- `src/services/__tests__/fixtures/` - Reusable test fixtures

## 7. Integration with Microservices

The frontend interacts with the backend services via the **API Gateway**.

| Frontend Page | Primary Backend Service | Key API Endpoints |
| :--- | :--- | :--- |
| **/market** | `monitoring-service` | `GET /monitor/market-health` |
| **/watchlist** | `monitoring-service` | `GET /monitor/watchlist`, `POST /jobs/watchlist/refresh` |
| **/portfolio** | `monitoring-service` | `GET /monitor/portfolio`, `POST /monitor/portfolio` |
| **/ (Dashboard)** | `screening-service`, `analysis-service` | `GET /screen/{ticker}`, `GET /analyze/{ticker}` |

## 8. Configuration Files

| File | Purpose |
|:---|:---|
| `vitest.config.js` | Test runner configuration (jsdom, globals, coverage) |
| `tsconfig.json` | TypeScript compiler options (ESNext, React JSX) |
| `.eslintrc.cjs` | ESLint rules for React + Vite |
| `package.json` | Dependencies, scripts, dev tooling |
| `Dockerfile` | Production build (multi-stage with Nginx) |
| `Dockerfile.dev` | Development container with hot reload |
| `nginx.conf` | Production server config with SPA routing |

## 9. Documentation Sources
*   *Architecture & Design:* `ARCHITECTURE.md` (Master), `Phase 2_ Technical Design_ Monitor Service & Frontend Enhancements.txt`
*   *UI Specs:* `Frontend UI_UX Specification.txt`
*   *Testing:* `FRONTEND_TESTING_STANDARD.md`
*   *Data Contracts:* `DATA_CONTRACTS.md`, `shared/contracts.py`
