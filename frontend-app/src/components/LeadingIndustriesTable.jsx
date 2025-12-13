// frontend-app/src/components/LeadingIndustriesTable.jsx

import React, { useState } from 'react';
import {
    Box, Heading, Table, Thead, Tbody, Tr, Th, Td, TableContainer,
    VStack, HStack, Text, Tag, Tooltip, Icon, Button, useToast, Flex, Spacer
} from '@chakra-ui/react';
import { FiInfo, FiPlusCircle } from 'react-icons/fi'; // Feather Icons - clean, minimal style
import { addWatchlistBatch } from '../services/monitoringApi';

// Default marketLeaders to empty object to prevent "undefined" prop warning
const LeadingIndustriesTable = ({ marketLeaders = {} }) => {
  const toast = useToast();
  const [isAdding, setIsAdding] = useState(false);

  // Normalize to an array of { industry, stocks }
  const normalizeLeaders = (leaders) => {
    // Robust check for null/undefined even with default prop
    if (!leaders || typeof leaders !== 'object') {
      return [];
    }
    const li = leaders.leading_industries;

    // Validate leading_industries structure
    if (!li) {
      return [];
    }

    // Case 1: correct shape (Array)
    if (Array.isArray(li)) {
      // Validate each industry object has required fields
      return li.filter(item => 
        item && 
        typeof item === 'object' && 
        item.industry && 
        Array.isArray(item.stocks)
      );
    }

    // Case 2: backend returns keyed object like { "Semiconductors": ["NVDA", ...], ... }
    if (li && typeof li === 'object') {
      return Object.entries(li).map(([industry, stocks]) => {
        const normalizedStocks = Array.isArray(stocks)
          ? (typeof stocks[0] === 'string'
            ? stocks.map((t) => ({ ticker: t, percent_change_3m: null }))
            : stocks.filter(s => s && s.ticker)) // Filter invalid stocks
          : [];
        return {
          industry,
          stock_count: normalizedStocks.length, // Fallback if backend doesn't provide it
          stocks: normalizedStocks
        };
      });
    }
    // Fallback
    return [];
  };

  const handleBatchAdd = async (allTickers) => {
    if (!allTickers.length) return;
    
    setIsAdding(true);
    try {
        const response = await addWatchlistBatch(allTickers);
        // Response shape from backend: { message: str, added: int, skipped: int }
        const { added, skipped } = response.data;
        
        toast({
            title: "Watchlist Updated",
            description: `Added ${added} new leaders (${skipped} skipped).`,
            status: "success",
            duration: 4000,
            isClosable: true,
            position: "top-right"
        });
    } catch (error) {
        console.error("Batch add failed:", error);
        toast({
            title: "Error adding tickers",
            description: error.response?.data?.error || "Could not add leaders to watchlist.",
            status: "error",
            duration: 5000,
            isClosable: true,
             position: "top-right"
        });
    } finally {
        setIsAdding(false);
    }
  };

  // Wrap in try-catch for extra safety
  try {
      const industries = normalizeLeaders(marketLeaders);
      
      // Extract unique tickers from all industries
      const allTickers = Array.from(new Set(
        industries.flatMap(ind => ind.stocks.map(s => s.ticker))
      ));

      if (!industries.length) {
        return (
          <Box p={4}>
            <Heading size="md" mb={3} color="blue.400">Leading Industries</Heading>
            <Text color="gray.400">No leaders available.</Text>
          </Box>
        );
      }

      return (
        <Box p={4} h="100%">
          {/* Header Flex Container */}
          <Flex mb={4} align="center">
            <Heading size="md" color="blue.400">Leading Industries</Heading>
            <Spacer />
            {allTickers.length > 0 && (
                <Button
                    leftIcon={<FiPlusCircle />}
                    colorScheme="blue"
                    size="sm"
                    variant="outline"
                    isLoading={isAdding}
                    loadingText="Adding..."
                    onClick={() => handleBatchAdd(allTickers)}
                    title={`Add all ${allTickers.length} leading stocks to watchlist`}
                >
                    Add All ({allTickers.length})
                </Button>
            )}
          </Flex>

          <TableContainer>
            <Table variant="simple" size="md"> {/* Increased table size to 'md' for more spacing */}
              <Thead>
                <Tr>
                  <Th fontSize="sm">Industry</Th> {/* Increased font size */}
                  {/* Count column with tooltip */}
                  <Th fontSize="sm">
                    <HStack spacing={1}>
                      <Text>Count</Text>
                      <Tooltip
                        label="Number of stocks in this industry making new 52-week highs"
                        fontSize="sm"
                        hasArrow
                      >
                        <span>
                          <Icon as={FiInfo} boxSize={3} color="gray.500" />
                        </span>
                      </Tooltip>
                    </HStack>
                  </Th>
                  <Th fontSize="sm">
                    <HStack spacing={1}>
                      <Text>Leading Stocks (3M Rtn)</Text>
                      <Tooltip
                        label="Selected by highest marketCap, and sorted by their 3-month returns"
                        fontSize="sm"
                        hasArrow
                        placement="top"
                      >
                        <span>
                          <Icon as={FiInfo} boxSize={3} color="gray.500" />
                        </span>
                      </Tooltip>
                    </HStack>
                  </Th>
                </Tr>
              </Thead>
              <Tbody>
                {industries.map((item, idx) => (
                  <Tr key={idx}>
                    <Td fontWeight="medium" fontSize="md" maxW="200px" isTruncated title={item.industry}> {/* Larger font */}
                        {item.industry}
                    </Td>
                    {/* Display stock_count */}
                    <Td>
                      <Tag colorScheme="blue" size="md" variant="subtle"> {/* Larger Tag */}
                        {item.stock_count || item.stocks.length}
                      </Tag>
                    </Td>
                    <Td>
                      <Flex wrap="wrap" gap={3}> {/* Increased gap */}
                        {/* Display up to 8 stocks to fill vertical space better */}
                        {item.stocks.slice(0, 8).map((stock, i) => (
                          <Tag key={i} size="md" colorScheme="green" variant="solid"> {/* Larger Tag */}
                            {stock.ticker}
                            {stock.percent_change_3m && ` ${stock.percent_change_3m.toFixed(0)}%`}
                          </Tag>
                        ))}
                        {item.stocks.length > 8 && (
                            <Text fontSize="sm" color="gray.500" alignSelf="center">+{item.stocks.length - 8}</Text>
                        )}
                      </Flex>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </TableContainer>
        </Box>
      );
  } catch (error) {
    console.error('[LeadingIndustriesTable] Render error:', error);
    return (
      <Box p={4} bg="red.50">
        <Heading size="md" mb={2} color="red.600">Unable to display industry leaders</Heading>
        <Text color="red.500" fontSize="sm">
          An error occurred while rendering this component.
        </Text>
      </Box>
    );
  }
};

export default LeadingIndustriesTable;