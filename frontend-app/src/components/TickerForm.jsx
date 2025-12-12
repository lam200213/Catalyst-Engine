// frontend-app/src/components/TickerForm.jsx

import React from 'react';
import { Button, Flex, Input } from '@chakra-ui/react';
import { SearchIcon } from '@chakra-ui/icons'; // Optional: adding icon for better visual weight

const TickerForm = ({ ticker, setTicker, handleSubmit, loading }) => {
  return (
    <form onSubmit={handleSubmit} role="form">
      <Flex direction={{ base: 'column', md: 'row' }} gap={4} align="center">
        <Input
          placeholder="Enter Ticker (e.g., AAPL)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          focusBorderColor="blue.300"
          size="lg"
          isDisabled={loading}
          bg="gray.700"
          border="1px solid"
          borderColor="gray.600"
          _hover={{ borderColor: "gray.500" }}
        />
        <Button
          type="submit"
          colorScheme="blue"
          size="lg"
          px={8} // Horizontal padding to make button wider
          h="48px" // Fixed height to match Input size="lg" usually, or slightly taller
          fontSize="md"
          fontWeight="bold"
          isLoading={loading}
          loadingText="Analyzing..."
          w={{ base: '100%', md: 'auto' }}
          leftIcon={<SearchIcon />}
          boxShadow="md"
          _hover={{ bg: "blue.400", transform: "translateY(-1px)", boxShadow: "lg" }}
          transition="all 0.2s"
        >
          Analyze Stock
        </Button>
      </Flex>
    </form>
  );
};

export default TickerForm;