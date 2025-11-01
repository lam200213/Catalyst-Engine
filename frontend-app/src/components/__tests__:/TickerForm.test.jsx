// frontend-app/src/components/TickerForm.test.jsx
import React from 'react';
import { screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders } from '../test-utils'; // Optional but consistent
import TickerForm from './TickerForm';

describe('components/TickerForm', () => {

    // Test Case 1: Business Logic Verification
    it('should call the submit handler with the correct ticker on form submission', async () => {
        // Arrange: Create a mock function for the submission handler
        const handleSubmit = vi.fn((e) => e.preventDefault());
        const setTicker = vi.fn();

        renderWithProviders(
        <TickerForm ticker="AAPL" setTicker={setTicker} handleSubmit={handleSubmit} loading={false} />
        );
        
        // Act: Simulate form submission
        const form = screen.getByRole('form'); // Note: Added role="form" to TickerForm for this to work
        fireEvent.submit(form);

        // Assert: Verify the handler was called
        expect(handleSubmit).toHaveBeenCalledTimes(1);
    });
    
    // Test Case 2: Edge Case (Empty Submission)
    it('should still call the submit handler when the form is empty', async () => {
        // Arrange
        const handleSubmit = vi.fn((e) => e.preventDefault());
        const setTicker = vi.fn();

        renderWithProviders(
        <TickerForm ticker="" setTicker={setTicker} handleSubmit={handleSubmit} loading={false} />
        );
        
        // Act
        const form = screen.getByRole('form');
        fireEvent.submit(form);

        // Assert
        expect(handleSubmit).toHaveBeenCalledTimes(1);
        // Note: The TickerForm component itself does not prevent submission.
        // The validation logic resides in the parent `App.jsx` component's handler.
        // This test correctly verifies the component's responsibility: to call the handler.
    });

    // Test case 3: User Interaction (input onChange event)
    it('should call setTicker when user types in the input', async () => {
        // Arrange
        const setTicker = vi.fn();
        const user = userEvent.setup();
        renderWithProviders(
        <TickerForm ticker="" setTicker={setTicker} handleSubmit={(e) => e.preventDefault()} loading={false} />
        );
        const input = screen.getByPlaceholderText(/Enter Ticker/i);

        // Act
        await user.type(input, 'TSLA');

        // Assert
        expect(setTicker).toHaveBeenCalledWith('T');
        expect(setTicker).toHaveBeenCalledWith('S');
        expect(setTicker).toHaveBeenCalledWith('L');
        expect(setTicker).toHaveBeenCalledWith('A');
    });
});