// frontend-app/src/components/__tests__/ArchivedWatchlistTable.test.jsx
// Tests for ArchivedWatchlistTable component.

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ArchivedWatchlistTable } from '../ArchivedWatchlistTable';
import {
  baseArchivedWatchlistItem,
  makeArchivedWatchlistItem,
} from '../../testing/fixtures/watchlistFixtures';

describe('ArchivedWatchlistTable', () => {
  it('renders columns for ticker, archived at, reason, failed stage', () => {
    // Arrange
    const items = [baseArchivedWatchlistItem];

    // Act
    render(
      <ArchivedWatchlistTable
        items={items}
        onDelete={vi.fn()}
      />,
    );

    // Assert
    expect(
      screen.getByRole('columnheader', { name: /ticker/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', { name: /archived at/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', { name: /reason/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', { name: /failed stage/i }),
    ).toBeInTheDocument();
  });

  it('renders a row for each archived item', () => {
    // Arrange
    const items = [
      baseArchivedWatchlistItem,
      makeArchivedWatchlistItem({ ticker: 'NET' }),
    ];

    // Act
    render(
      <ArchivedWatchlistTable
        items={items}
        onDelete={vi.fn()}
      />,
    );

    // Assert
    expect(screen.getByText('CRM')).toBeInTheDocument();
    expect(screen.getByText('NET')).toBeInTheDocument();
  });

  it('maps reason enum to human-readable text', () => {
    // Arrange
    const items = [
      makeArchivedWatchlistItem({
        ticker: 'CRM',
        reason: 'MANUAL_DELETE',
        failed_stage: null,
      }),
      makeArchivedWatchlistItem({
        ticker: 'NET',
        reason: 'FAILED_HEALTH_CHECK',
        failed_stage: 'vcp',
      }),
    ];

    // Act
    render(
      <ArchivedWatchlistTable
        items={items}
        onDelete={vi.fn()}
      />,
    );

    // Assert
    expect(
      screen.getByText(/manual delete/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/failed health check/i),
    ).toBeInTheDocument();
  });

  it('renders failed_stage as hyphen when null', () => {
    // Arrange
    const items = [
      makeArchivedWatchlistItem({
        ticker: 'CRM',
        reason: 'MANUAL_DELETE',
        failed_stage: null,
      }),
    ];

    // Act
    render(
      <ArchivedWatchlistTable
        items={items}
        onDelete={vi.fn()}
      />,
    );

    // Assert
    const failedStageCell = screen.getByTestId('failed-stage-CRM');
    expect(failedStageCell).toHaveTextContent('-');
  });

  it('calls onDelete when delete button is clicked', async () => {
    // Arrange
    const user = userEvent.setup();
    const onDelete = vi.fn();
    const items = [
      makeArchivedWatchlistItem({
        ticker: 'CRM',
        reason: 'MANUAL_DELETE',
        failed_stage: null,
      }),
    ];

    // Act
    render(
      <ArchivedWatchlistTable
        items={items}
        onDelete={onDelete}
      />,
    );

    const button = screen.getByRole('button', { name: /delete crm/i });
    await user.click(button);

    // Assert
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledWith('CRM');
  });

  it('disables delete button when onDelete is not provided', () => {
    // Arrange
    const items = [baseArchivedWatchlistItem];

    // Act
    render(
      <ArchivedWatchlistTable
        items={items}
        onDelete={undefined}
      />,
    );

    const button = screen.getByRole('button', { name: /delete crm/i });

    // Assert
    expect(button).toBeDisabled();
  });

  it('renders empty state when no archived items exist', () => {
    // Arrange + Act
    render(
      <ArchivedWatchlistTable
        items={[]}
        onDelete={vi.fn()}
      />,
    );

    // Assert
    expect(
      screen.getByText(/no archived items/i),
    ).toBeInTheDocument();
  });

  it('handles undefined items safely by rendering empty state', () => {
    // Arrange + Act
    render(
      <ArchivedWatchlistTable
        items={undefined}
        onDelete={vi.fn()}
      />,
    );

    // Assert
    expect(
      screen.getByText(/no archived items/i),
    ).toBeInTheDocument();
  });
});
