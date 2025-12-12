// frontend-app/src/pages/WatchlistPage.jsx
// WatchlistPage Orchestration with selection, batch remove, row actions, and ErrorBoundaries.

import React, { useMemo } from 'react';
import {
  Box,
  Heading,
  Button,
  Tabs,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
  useToast,
  Flex,
  Text,
  HStack,
  Container,
  Badge,
  Icon,
} from '@chakra-ui/react';
import { RefreshCw, Trash2, Clock } from 'lucide-react';

import { useWatchlistQuery } from '../hooks/useWatchlistQuery';
import { useWatchlistArchiveQuery } from '../hooks/useWatchlistArchiveQuery';
import { useWatchlistRefreshJobMutation } from '../hooks/useWatchlistRefreshJobMutation';
import { useScreeningJobMutations } from '../hooks/useScreeningJobMutations';

import { WatchlistTable } from '../components/WatchlistTable';
import { ArchivedWatchlistTable } from '../components/ArchivedWatchlistTable';
import { AddWatchlistTickerForm } from '../components/AddWatchlistTickerForm';
import ErrorBoundary from '../components/ErrorBoundary';

const WatchlistPage = () => {
  const toast = useToast();

  // FIX: Added 'refetchInterval' to poll for updates every 3 seconds.
  // This ensures changes from external sources (CLI/Scheduler) appear "instantly".
  const watchlistQueryResult =
    useWatchlistQuery({ refetchInterval: 3000 }) || {
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    };

  const archiveQueryResult =
    useWatchlistArchiveQuery({ refetchInterval: 5000 }) || {
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    };

  const {
    data: watchlistData,
    isLoading: isWatchlistLoading,
    isError: isWatchlistError,
    error: watchlistError,
  } = watchlistQueryResult;

  const {
    data: archiveData,
    isLoading: isArchiveLoading,
    isError: isArchiveError,
    error: archiveError,
  } = archiveQueryResult;

  const refreshMutationResult =
    useWatchlistRefreshJobMutation() || {
      mutateAsync: async () => {},
      isLoading: false,
    };

  const { mutateAsync: refreshAsync, isLoading: isRefreshing } =
    refreshMutationResult;

  const items = watchlistData?.items ?? [];
  const archivedItems = archiveData?.archived_items ?? [];

  // Derive the last refresh time from the items list
  const lastRefreshDate = useMemo(() => {
    if (!items || items.length === 0) return null;
    
    const dates = items
      .map((item) => item.last_refresh_at)
      .filter((date) => date) // Filter out nulls/undefined
      .map((date) => new Date(date).getTime());

    if (dates.length === 0) return null;

    return new Date(Math.max(...dates));
  }, [items]);

  // Selection & batch remove
  const [selectedTickers, setSelectedTickers] = React.useState([]);

  const screeningMutations =
    useScreeningJobMutations() || {
      useRemoveWatchlistBatch: () => ({
        mutateAsync: async () => {},
        isLoading: false,
      }),
      useToggleFavourite: () => ({
        mutateAsync: async () => {},
        isLoading: false,
      }),
      useRemoveWatchlistItem: () => ({
        mutateAsync: async () => {},
        isLoading: false,
      }),
      useDeleteFromArchive: () => ({
        mutateAsync: async () => {},
        isLoading: false,
      }),
      useAddWatchlistItem: () => ({
        mutateAsync: async () => {},
        isLoading: false,
      }),
    };

  const {
    mutateAsync: removeBatchAsync,
    isLoading: isBatchRemoving,
  } = screeningMutations.useRemoveWatchlistBatch();

  const {
    mutateAsync: toggleFavouriteAsync,
    isLoading: isToggleFavouriteLoading,
  } = screeningMutations.useToggleFavourite();

  const {
    mutateAsync: removeWatchlistItemAsync,
    isLoading: isRemoveItemLoading,
  } = screeningMutations.useRemoveWatchlistItem();

  const {
    mutateAsync: deleteFromArchiveAsync,
    isLoading: isDeleteArchiveLoading,
  } = screeningMutations.useDeleteFromArchive();

  const {
    mutateAsync: addWatchlistItemAsync,
    isLoading: isAddLoading,
  } = screeningMutations.useAddWatchlistItem();

  const rowActionsDisabled =
    isToggleFavouriteLoading || isRemoveItemLoading || isDeleteArchiveLoading || isAddLoading;

  const handleToggleSelect = (ticker) => {
    setSelectedTickers((prev) =>
      prev.includes(ticker)
        ? prev.filter((t) => t !== ticker)
        : [...prev, ticker],
    );
  };

  const handleAddTicker = async (ticker) => {
    try {
      await addWatchlistItemAsync(ticker);
      toast({ status: 'success', title: `Added ${ticker} to watchlist` });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      toast({
        status: 'error',
        title: 'Failed to add ticker',
        description: message,
      });
    }
  };

  const handleRestoreTicker = async (ticker) => {
      try {
          await addWatchlistItemAsync(ticker);
          toast({ status: 'success', title: `Restored ${ticker} to watchlist`});
      } catch (err) {
          const message = err instanceof Error ? err.message : 'Unknown error';
          toast({
              status: 'error',
              title: 'Failed to restore ticker',
              description: message,
          });
      }
  }

  const handleRemoveSelected = async () => {
    if (!selectedTickers.length) return;

    try {
      await removeBatchAsync({ tickers: selectedTickers });
      setSelectedTickers([]);
      toast({ status: 'success', title: 'Removed selected tickers' });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unknown error';
      toast({
        status: 'error',
        title: 'Failed to remove selected',
        description: message,
      });
    }
  };

  const handleRefreshClick = async () => {
    try {
      // 1. Trigger the job
      const result = await refreshAsync();
      
      toast({
        status: 'success',
        title: 'Watchlist health refresh complete',
        description: result?.job_id ? `Job ID: ${result.job_id}` : undefined,
      });

    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unknown error';
      toast({
        status: 'error',
        title: 'Failed to start refresh',
        description: message,
      });
    }
  };

  const handleToggleFavourite = async (ticker, is_favourite) => {
    try {
      await toggleFavouriteAsync({ ticker, is_favourite });
      toast({
        status: 'success',
        title: is_favourite
          ? 'Marked as favourite'
          : 'Removed from favourites',
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unknown error';
      toast({
        status: 'error',
        title: 'Failed to update favourite',
        description: message,
      });
    }
  };

  const handleRemoveItem = async (ticker) => {
    try {
      await removeWatchlistItemAsync(ticker);
      toast({
        status: 'success',
        title: `Removed ${ticker} from watchlist`,
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unknown error';
      toast({
        status: 'error',
        title: `Failed to remove ${ticker} from watchlist`,
        description: message,
      });
    }
  };

  const handleDeleteFromArchive = async (ticker) => {
    try {
      await deleteFromArchiveAsync(ticker);
      toast({
        status: 'success',
        title: 'Deleted from archive',
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unknown error';
      toast({
        status: 'error',
        title: 'Failed to delete from archive',
        description: message,
      });
    }
  };

  return (
    <Container maxW="100%" px={6} py={6}>
      <Flex mb={6} justify="space-between" align="center" wrap="wrap" gap={4}>
        <Box>
          <Heading as="h1" size="lg" color="blue.300" mb={1}>
            Watchlist
          </Heading>
          <Text color="gray.400" fontSize="sm">
            Monitor and screen your candidate stocks
          </Text>
          {/* Last Updated display */}
          {lastRefreshDate && (
            <HStack spacing={1.5} mt={2} color="gray.500">
              <Icon as={Clock} boxSize={3.5} />
              <Text fontSize="xs" fontWeight="medium">
                Last health check: {lastRefreshDate.toLocaleString()}
              </Text>
            </HStack>
          )}
        </Box>
        <HStack spacing={3}>
           <AddWatchlistTickerForm 
              onSubmit={handleAddTicker} 
              isSubmitting={isAddLoading} 
           />
           <Button
            leftIcon={<RefreshCw size={16} />}
            colorScheme="blue"
            variant="outline"
            onClick={handleRefreshClick}
            isLoading={isRefreshing}
            loadingText="Refreshing"
            size="md"
            px={4}
            flexShrink={0}
            whiteSpace="nowrap"
            minW="fit-content"
          >
            Refresh Watchlist Health
          </Button>
          
          <Button
             leftIcon={<Trash2 size={16} />}
             colorScheme="red"
             variant="solid"
             onClick={handleRemoveSelected}
             isDisabled={selectedTickers.length === 0 || isBatchRemoving}
             isLoading={isBatchRemoving}
             size="md"
             px={4}
             flexShrink={0}
             whiteSpace="nowrap"
             minW="fit-content"
           >
             Remove Selected
           </Button>
        </HStack>
      </Flex>

      {isWatchlistLoading && <Box mb={2}>Loading watchlist...</Box>}

      {isWatchlistError && (
        <Box mb={4} p={4} bg="red.900" color="red.100" borderRadius="md">
          Failed to load watchlist:{' '}
          {watchlistError instanceof Error
            ? watchlistError.message
            : 'Unknown error'}
        </Box>
      )}

      {isArchiveError && (
        <Box mb={4} p={4} bg="red.900" color="red.100" borderRadius="md">
          Failed to load archive:{' '}
          {archiveError instanceof Error
            ? archiveError.message
            : 'Unknown error'}
        </Box>
      )}

      <Tabs variant="enclosed" colorScheme="blue">
        <TabList mb={4}>
          <Tab>
            Active Watchlist 
            {items.length > 0 && (
              <Badge ml={2} colorScheme="blue" variant="solid" borderRadius="full">
                {items.length}
              </Badge>
            )}
          </Tab>
          <Tab>Recently Archived</Tab>
        </TabList>

        <TabPanels>
          <TabPanel p={0}>
            <ErrorBoundary>
              <WatchlistTable
                items={items}
                selectedTickers={selectedTickers}
                onToggleSelect={handleToggleSelect}
                onRemoveSelected={handleRemoveSelected}
                onToggleFavourite={handleToggleFavourite}
                onRemoveItem={handleRemoveItem}
                rowActionsDisabled={rowActionsDisabled}
              />
            </ErrorBoundary>
          </TabPanel>
          <TabPanel p={0}>
            <ErrorBoundary>
              <ArchivedWatchlistTable
                items={archivedItems}
                onDelete={handleDeleteFromArchive}
                onRestore={handleRestoreTicker}
                rowActionsDisabled={rowActionsDisabled}
              />
            </ErrorBoundary>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Container>
  );
};

export default WatchlistPage;