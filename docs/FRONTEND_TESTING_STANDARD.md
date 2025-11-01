# Frontend Testing Standard

## Test Organization
- Co-locate tests with source files in `__tests__/` folders
- Test file naming: `ComponentName.test.jsx` or `utilName.test.js`

## Test Categories
1. **Unit Tests**: Individual functions, hooks, utilities
2. **Component Tests**: React components with mocked dependencies  
3. **Integration Tests**: Multi-component flows with real data flow

## Workflow

### Development Phase
1. Write tests **before** or **alongside** feature code (TDD optional but encouraged)
2. Run tests in watch mode: `npm test`
3. Fix failing tests immediately—don't commit broken tests

### Pre-Commit
1. Run full test suite: `npm test -- --run`
2. Ensure coverage meets threshold (future: add coverage requirements)
3. Lint tests: `npm run lint`

### CI/CD
- All tests must pass before merge
- Failed tests block deployment

## Test Structure (AAA Pattern)
it('should do something when condition', () => {
// Arrange: Set up test data and mocks
const mockData = { ... };

// Act: Execute the code under test
render(<Component data={mockData} />);

// Assert: Verify expected behavior
expect(screen.getByText('...')).toBeInTheDocument();
});


## Mocking Guidelines
- Mock external APIs (axios, fetch)
- Mock heavy dependencies (charting libraries)
- Do NOT mock business logic or utility functions

## Coverage Goals
- Components: 80%+ coverage
- Services/Utils: 90%+ coverage
- Critical paths: 100% coverage