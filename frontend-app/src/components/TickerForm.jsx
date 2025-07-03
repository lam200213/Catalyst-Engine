import React from 'react';
import { Button, Flex, Input } from '@chakra-ui/react';

const TickerForm = ({ ticker, setTicker, handleSubmit, loading }) => {
  return (
    <form onSubmit={handleSubmit} role="form">
      <Flex direction={{ base: 'column', md: 'row' }} gap={4}>
        <Input
          placeholder="Enter Ticker (e.g., AAPL)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          focusBorderColor="blue.300"
          size="lg"
          isDisabled={loading}
        />
        <Button
          type="submit"
          colorScheme="blue"
          size="lg"
          isLoading={loading}
          loadingText="Analyzing..."
          w={{ base: '100%', md: 'auto' }}
        >
          Analyze Stock
        </Button>
      </Flex>
    </form>
  );
};

export default TickerForm;