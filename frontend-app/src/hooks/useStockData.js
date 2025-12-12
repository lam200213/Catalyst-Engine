// frontend-app/src/hooks/useStockData.js
import { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchStockData } from '../services/screeningApi';

// Unique key for caching this specific data type
export const STOCK_DATA_QUERY_KEY = 'stockData';

export const useStockData = (initialTicker = 'AAPL') => {
    // 1. Initialize state from localStorage if available to restore user's last view.
    //    If nothing in storage, fall back to initialTicker.
    const [searchTerm, setSearchTerm] = useState(() => {
        return localStorage.getItem('last_active_ticker') || initialTicker;
    });

    // 2. Separate "input" state (what user types) from "search" state (what triggers fetch).
    //    We initialize input with the searchTerm so the input box isn't empty on reload.
    const [tickerInput, setTickerInput] = useState(searchTerm);

    const queryClient = useQueryClient();

    // 3. Use TanStack Query for data fetching and caching.
    //    This replaces the manual useEffect/fetch logic.
    const { 
        data, 
        isLoading, 
        isError, 
        error, 
        isFetching 
    } = useQuery({
        // The query key includes the searchTerm. Changing searchTerm automatically triggers a fetch (or cache hit).
        queryKey: [STOCK_DATA_QUERY_KEY, searchTerm],
        queryFn: () => fetchStockData(searchTerm),
        // Only run the query if we have a valid ticker
        enabled: !!searchTerm,
        // Keep data fresh for 5 minutes (prevents immediate refetching on nav back)
        staleTime: 1000 * 60 * 5, 
        // Keep data in cache (garbage collection time) for 30 minutes
        gcTime: 1000 * 60 * 30,
        // Disable automatic refetch on window focus to prevent UI jumping while reading charts
        refetchOnWindowFocus: false,
        // Retry once on failure before showing error
        retry: 1
    });

    // 4. Wrapper for the manual "Analyze" button.
    //    Instead of imperatively fetching, we just update the 'searchTerm' state.
    //    React Query observes this change and handles the fetching logic.
    const getData = (newTicker) => {
        if (!newTicker) return;
        const upperTicker = newTicker.toUpperCase();
        
        // Update the state that drives the query
        setSearchTerm(upperTicker);
        
        // Persist to localStorage so we remember this ticker if the user navigates away
        localStorage.setItem('last_active_ticker', upperTicker);
        
        // Ensure the input field matches the search (good UX)
        setTickerInput(upperTicker);
    };

    // 5. Return signature matches the original hook for easy drop-in replacement.
    return {
        ticker: tickerInput,       // Bound to Input field (controlled component)
        setTicker: setTickerInput, // Handler for Input field typing
        
        // Data Fallback: Return empty structure if data is undefined (loading/idle)
        data: data || { screening: null, analysis: null }, 
        
        // Combine loading states: True if initial load OR background refetch
        loading: isLoading || isFetching, 
        
        // Standardize error message string
        error: isError ? (error?.message || "An error occurred during analysis") : null,
        
        getData // The function called by handleSubmit
    };
};