// frontend-app/src/components/__tests__/WatchlistTable.test.jsx
// Tests for WatchlistTable component.

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { render } from '../../test-utils';
import { WatchlistTable } from '../WatchlistTable';
import {
  baseWatchlistItem,
  makeWatchlistItem,
} from '../../testing/fixtures/watchlistFixtures';

// Shared sample items matching frontend WatchlistItem interface shape.
const baseItems = [
  baseWatchlistItem,
  makeWatchlistItem({
    ticker: 'CELH',
    status: 'Buy Alert',
    date_added: '2025-10-05',
    is_favourite: false,
    is_leader: false,
    is_at_pivot: false,
    has_pullback_setup: true,
    last_refresh_status: 'FAIL',
    last_refresh_at: '2025-10-10T10:00:00Z',
    failed_stage: 'vcp',
    current_price: 60.25,
    pivot_price: null,
    pivot_proximity_percent: null,
    vol_last: 8_000_000,
    vol_50d_avg: 10_000_000,
    vol_vs_50d_ratio: 0.8,
    day_change_pct: -1.2,
  }),
];

const defaultProps = (overrides = {}) => ({
  items: baseItems,
  selectedTickers: [],
  onToggleSelect: vi.fn(),
  onRemoveSelected: vi.fn(),
  // Row actions (Task C.2)
  onToggleFavourite: undefined,
  onRemoveItem: undefined,
  rowActionsDisabled: false,
  ...overrides,
});

describe('WatchlistTable', () => {
  it('renders rows with ticker and status for each item', () => {
    // Arrange
    const props = defaultProps();

    // Act
    render(<WatchlistTable {...props} />);

    // Assert
    expect(screen.getByText('NET')).toBeInTheDocument();
    expect(screen.getByText('CELH')).toBeInTheDocument();
    expect(screen.getByText('Buy Ready')).toBeInTheDocument();
    expect(screen.getByText('Buy Alert')).toBeInTheDocument();
  });

  it('renders health and status badges for each row', () => {
    // Arrange
    const props = defaultProps();

    // Act
    render(<WatchlistTable {...props} />);

    // Assert
    const netStatusBadge = screen.getByTestId('status-badge-NET');
    const celhStatusBadge = screen.getByTestId('status-badge-CELH');
    const netHealthBadge = screen.getByTestId('health-badge-NET');
    const celhHealthBadge = screen.getByTestId('health-badge-CELH');

    expect(netStatusBadge).toBeInTheDocument();
    expect(celhStatusBadge).toBeInTheDocument();
    expect(netHealthBadge).toBeInTheDocument();
    expect(celhHealthBadge).toBeInTheDocument();
  });

  it('shows empty watchlist message when items array is empty', () => {
    // Arrange
    const props = defaultProps({ items: [] });

    // Act
    render(<WatchlistTable {...props} />);

    // Assert
    expect(
      screen.getByText(/your watchlist is empty/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/add a ticker to start tracking/i),
    ).toBeInTheDocument();
  });

  it('handles undefined or non-array items by rendering empty state safely', () => {
    // Arrange
    const props = defaultProps({ items: undefined });

    // Act
    render(<WatchlistTable {...props} />);

    // Assert
    expect(
      screen.getByText(/your watchlist is empty/i),
    ).toBeInTheDocument();
  });

  it('calls onToggleSelect with ticker when row checkbox is clicked', () => {
    // Arrange
    const onToggleSelect = vi.fn();
    const props = defaultProps({ onToggleSelect });

    render(<WatchlistTable {...props} />);

    const checkbox = screen.getByRole('checkbox', { name: /select NET/i });

    // Act
    fireEvent.click(checkbox);

    // Assert
    expect(onToggleSelect).toHaveBeenCalledTimes(1);
    expect(onToggleSelect).toHaveBeenCalledWith('NET');
  });

  it('disables selection checkbox when no onToggleSelect callback is provided', () => {
    // Arrange
    const props = defaultProps({ onToggleSelect: undefined });

    // Act
    render(<WatchlistTable {...props} />);

    const checkbox = screen.getByRole('checkbox', { name: /select NET/i });

    // Assert
    expect(checkbox).toBeDisabled();
  });

  it('marks checkboxes as selected only for tickers present in items', () => {
    // Arrange
    const props = defaultProps({
      selectedTickers: ['NET', 'MISSING'],
    });

    // Act
    render(<WatchlistTable {...props} />);

    const netCheckbox = screen.getByRole('checkbox', { name: /select NET/i });
    const celhCheckbox = screen.getByRole('checkbox', {
      name: /select CELH/i,
    });

    // Assert
    expect(netCheckbox).toBeChecked();
    expect(celhCheckbox).not.toBeChecked();
  });

  it('applies correct status badge color for Buy Ready, Buy Alert, and Watch', () => {
    // Arrange
    const items = [
      makeWatchlistItem({ ticker: 'READY', status: 'Buy Ready' }),
      makeWatchlistItem({ ticker: 'ALERT', status: 'Buy Alert' }),
      makeWatchlistItem({ ticker: 'WATCH', status: 'Watch' }),
    ];

    const props = defaultProps({ items });

    // Act
    render(<WatchlistTable {...props} />);

    const readyBadge = screen.getByTestId('status-badge-READY');
    const alertBadge = screen.getByTestId('status-badge-ALERT');
    const watchBadge = screen.getByTestId('status-badge-WATCH');

    // Assert
    expect(readyBadge).toHaveAttribute('data-color', 'green');
    expect(alertBadge).toHaveAttribute('data-color', 'yellow');
    expect(watchBadge).toHaveAttribute('data-color', 'blue');
  });

  it('applies correct health badge color for PASS, FAIL, PENDING, UNKNOWN', () => {
    // Arrange
    const items = [
      makeWatchlistItem({ ticker: 'PASS', last_refresh_status: 'PASS' }),
      makeWatchlistItem({ ticker: 'FAIL', last_refresh_status: 'FAIL' }),
      makeWatchlistItem({ ticker: 'PEND', last_refresh_status: 'PENDING' }),
      makeWatchlistItem({ ticker: 'UNK', last_refresh_status: 'UNKNOWN' }),
    ];

    const props = defaultProps({ items });

    // Act
    render(<WatchlistTable {...props} />);

    const passBadge = screen.getByTestId('health-badge-PASS');
    const failBadge = screen.getByTestId('health-badge-FAIL');
    const pendingBadge = screen.getByTestId('health-badge-PEND');
    const unknownBadge = screen.getByTestId('health-badge-UNK');

    // Assert
    expect(passBadge).toHaveAttribute('data-color', 'green');
    expect(failBadge).toHaveAttribute('data-color', 'red');
    expect(pendingBadge).toHaveAttribute('data-color', 'yellow');
    expect(unknownBadge).toHaveAttribute('data-color', 'gray');
  });

  it('shows favourite star icon when is_favourite is true', () => {
    // Arrange
    const props = defaultProps();

    // Act
    render(<WatchlistTable {...props} />);

    // Assert
    const favIcon = screen.getByLabelText(/favourite stock NET/i);
    expect(favIcon).toBeInTheDocument();
  });

  it('shows leadership asterisk when is_leader is true', () => {
    // Arrange
    const props = defaultProps();

    // Act
    render(<WatchlistTable {...props} />);

    // Assert
    const leaderIcon = screen.getByLabelText(/leadership stock NET/i);
    expect(leaderIcon).toBeInTheDocument();
  });

  // shows pivot and PB badges when is_at_pivot or has_pullback_setup are true
  it('shows pivot and PB badges when is_at_pivot or has_pullback_setup are true', () => {
    // Arrange
    const props = defaultProps();

    // Act
    render(<WatchlistTable {...props} />);

    // Assert
    const pivotMatches = screen.getAllByText(/pivot/i);
    expect(pivotMatches.length).toBeGreaterThanOrEqual(1);

    const pbBadges = screen.getAllByText(/\bPB\b/);
    expect(pbBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('renders pivot proximity cell with price and percentage', () => {
    // Arrange
    const props = defaultProps();

    // Act
    render(<WatchlistTable {...props} />);

    // Assert
    const cell = screen.getByTestId('pivot-cell-NET');
    expect(cell).toHaveTextContent('86.00');
    expect(cell).toHaveTextContent('-1.05');
  });

  it('renders Vol vs 50D with ratio, color-coded by day_change_pct and highlighted for spikes', () => {
    // Arrange
    const items = [
      makeWatchlistItem({
        ticker: 'POS',
        vol_vs_50d_ratio: 2.1,
        day_change_pct: 1.5,
      }),
      makeWatchlistItem({
        ticker: 'NEG',
        vol_vs_50d_ratio: 0.8,
        day_change_pct: -0.5,
      }),
      makeWatchlistItem({
        ticker: 'SPIKE',
        vol_vs_50d_ratio: 3.2,
        day_change_pct: 0.1,
      }),
    ];

    const props = defaultProps({ items });

    // Act
    render(<WatchlistTable {...props} />);

    const posCell = screen.getByTestId('vol-cell-POS');
    const negCell = screen.getByTestId('vol-cell-NEG');
    const spikeCell = screen.getByTestId('vol-cell-SPIKE');

    // Assert
    expect(posCell).toHaveTextContent('2.1x');
    expect(posCell).toHaveAttribute('data-color', 'green');

    expect(negCell).toHaveTextContent('0.8x');
    expect(negCell).toHaveAttribute('data-color', 'red');

    expect(spikeCell).toHaveTextContent('3.2x');
    expect(spikeCell).toHaveAttribute('data-highlight', 'true');
  });

  //
  // Task C.2 – Row action behaviour at component level
  //

  it('calls onToggleFavourite with ticker and toggled is_favourite when favourite star is clicked', () => {
    // Arrange
    const onToggleFavourite = vi.fn();
    const props = defaultProps({ onToggleFavourite });

    render(<WatchlistTable {...props} />);

    const favButton = screen.getByRole('button', {
      name: /favourite stock net/i,
    });

    // Act
    fireEvent.click(favButton);

    // Assert: base item has is_favourite: true, so toggled value is false
    expect(onToggleFavourite).toHaveBeenCalledTimes(1);
    expect(onToggleFavourite).toHaveBeenCalledWith('NET', false);
  });

  it('does not call onToggleFavourite when rowActionsDisabled is true', () => {
    // Arrange
    const onToggleFavourite = vi.fn();
    const props = defaultProps({
      onToggleFavourite,
      rowActionsDisabled: true,
    });

    render(<WatchlistTable {...props} />);

    const favButton = screen.getByRole('button', {
      name: /favourite stock net/i,
    });

    // Act
    fireEvent.click(favButton);

    // Assert
    expect(favButton).toBeDisabled();
    expect(onToggleFavourite).not.toHaveBeenCalled();
  });

  it('renders row-level Delete button and calls onRemoveItem with ticker when clicked', () => {
    // Arrange
    const onRemoveItem = vi.fn();
    const props = defaultProps({ onRemoveItem });

    render(<WatchlistTable {...props} />);

    const deleteButton = screen.getByRole('button', {
      name: /delete net/i,
    });

    // Act
    fireEvent.click(deleteButton);

    // Assert
    expect(onRemoveItem).toHaveBeenCalledTimes(1);
    expect(onRemoveItem).toHaveBeenCalledWith('NET');
  });

  it('disables row-level Delete button when onRemoveItem is not provided', () => {
    // Arrange
    const props = defaultProps({ onRemoveItem: undefined });

    render(<WatchlistTable {...props} />);

    const deleteButton = screen.getByRole('button', {
      name: /delete net/i,
    });

    // Assert
    expect(deleteButton).toBeDisabled();
  });

  it('disables row-level Delete button when rowActionsDisabled is true', () => {
    // Arrange
    const onRemoveItem = vi.fn();
    const props = defaultProps({
      onRemoveItem,
      rowActionsDisabled: true,
    });

    render(<WatchlistTable {...props} />);

    const deleteButton = screen.getByRole('button', {
      name: /delete net/i,
    });

    // Act
    fireEvent.click(deleteButton);

    // Assert
    expect(deleteButton).toBeDisabled();
    expect(onRemoveItem).not.toHaveBeenCalled();
  });
});
