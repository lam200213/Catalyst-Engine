// frontend-app/src/components/__tests__/AddWatchlistTickerForm.test.tsx
// Tests for AddWatchlistTickerForm.

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { AddWatchlistTickerForm } from '../AddWatchlistTickerForm';

// Helper to get common elements
const getFormElements = () => {
  const input = screen.getByRole('textbox', { name: /ticker/i });
  const button = screen.getByRole('button', { name: /add/i });
  return { input, button };
};

describe('AddWatchlistTickerForm', () => {
  it('renders input and submit button for ticker entry', () => {
    // Arrange
    const handleSubmit = vi.fn();

    // Act
    render(<AddWatchlistTickerForm onSubmit={handleSubmit} />);

    const { input, button } = getFormElements();

    // Assert
    expect(input).toBeInTheDocument();
    expect(button).toBeInTheDocument();
    expect(button).toBeEnabled();
  });

  it('submits uppercase ticker when input is valid', () => {
    // Arrange
    const handleSubmit = vi.fn();
    render(<AddWatchlistTickerForm onSubmit={handleSubmit} />);

    const { input, button } = getFormElements();

    // Act
    fireEvent.change(input, { target: { value: 'NET' } });
    fireEvent.click(button);

    // Assert
    expect(handleSubmit).toHaveBeenCalledTimes(1);
    expect(handleSubmit).toHaveBeenCalledWith('NET');
    expect((input as HTMLInputElement).value).toBe('');
  });

  it('trims whitespace around ticker before validating and submitting', () => {
    // Arrange
    const handleSubmit = vi.fn();
    render(<AddWatchlistTickerForm onSubmit={handleSubmit} />);

    const { input, button } = getFormElements();

    // Act
    fireEvent.change(input, { target: { value: '  NET  ' } });
    fireEvent.click(button);

    // Assert
    expect(handleSubmit).toHaveBeenCalledTimes(1);
    expect(handleSubmit).toHaveBeenCalledWith('NET');
  });

  it('disables input and button while submitting', () => {
    // Arrange
    const handleSubmit = vi.fn();

    // Act
    render(
      <AddWatchlistTickerForm onSubmit={handleSubmit} isSubmitting={true} />,
    );

    const { input, button } = getFormElements();

    // Assert
    expect(input).toBeDisabled();
    expect(button).toBeDisabled();
  });

  it('shows validation error and does not submit on empty input', () => {
    // Arrange
    const handleSubmit = vi.fn();
    render(<AddWatchlistTickerForm onSubmit={handleSubmit} />);

    const { button } = getFormElements();

    // Act
    fireEvent.click(button);

    // Assert
    expect(handleSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText(/ticker is required/i),
    ).toBeInTheDocument();
  });

  it('auto-normalizes lowercase ticker to uppercase and submits', () => {
    // Arrange
    const handleSubmit = vi.fn();
    render(<AddWatchlistTickerForm onSubmit={handleSubmit} />);
    const { input, button } = getFormElements();
    // Act
    fireEvent.change(input, { target: { value: 'net' } });
    expect((input as HTMLInputElement).value).toBe('NET');
    fireEvent.click(button);
    // Assert
    expect(handleSubmit).toHaveBeenCalledTimes(1);
    expect(handleSubmit).toHaveBeenCalledWith('NET');
    expect(screen.queryByText(/ticker must be uppercase/i)).not.toBeInTheDocument();
  });

  it('shows validation error and does not submit on invalid characters', () => {
    // Arrange
    const handleSubmit = vi.fn();
    render(<AddWatchlistTickerForm onSubmit={handleSubmit} />);

    const { input, button } = getFormElements();

    // Act
    fireEvent.change(input, { target: { value: 'AAPL/US' } });
    fireEvent.click(button);

    // Assert
    expect(handleSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText(/invalid ticker format/i),
    ).toBeInTheDocument();
  });

  it('clears validation error once user fixes the input', () => {
    // Arrange
    const handleSubmit = vi.fn();
    render(<AddWatchlistTickerForm onSubmit={handleSubmit} />);

    const { input, button } = getFormElements();

    // Trigger an initial validation error
    fireEvent.click(button);
    const requiredError = screen.getByText(/ticker is required/i);
    expect(requiredError).toBeInTheDocument();

    // Act: fix the input and resubmit
    fireEvent.change(input, { target: { value: 'NET' } });
    fireEvent.click(button);

    // Assert
    expect(handleSubmit).toHaveBeenCalledTimes(1);
    expect(handleSubmit).toHaveBeenCalledWith('NET');
    expect(
      screen.queryByText(/ticker is required/i),
    ).not.toBeInTheDocument();
  });
});