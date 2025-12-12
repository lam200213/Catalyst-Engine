// frontend-app/src/components/AddWatchlistTickerForm.tsx
import React, { useState, type FormEvent, type ChangeEvent } from 'react';
import { 
  HStack, 
  Input, 
  Button, 
  FormControl, 
  Text,
  useColorModeValue 
} from '@chakra-ui/react';
import { Plus } from 'lucide-react';

export interface AddWatchlistTickerFormProps {
  onSubmit?: (ticker: string) => void;
  isSubmitting?: boolean;
}

export const AddWatchlistTickerForm: React.FC<AddWatchlistTickerFormProps> = ({
  onSubmit,
  isSubmitting = false,
}) => {
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const inputBg = useColorModeValue('white', 'gray.700');

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    // Enforce uppercase on input immediately
    setValue(event.target.value.toUpperCase());
    if (error) {
      setError(null);
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();

    if (!onSubmit) {
      return;
    }

    const trimmed = value.trim();

    if (!trimmed) {
      setError('Ticker is required');
      return;
    }

    // Gone: Explicit check for uppercase (trimmed !== upper) is no longer needed
    // as input is forced to uppercase in handleChange.

    const validFormat = /^[A-Z0-9.-]+$/;

    if (!validFormat.test(trimmed)) {
      setError('Invalid ticker format');
      return;
    }

    setError(null);
    onSubmit(trimmed);
    setValue('');
  };

  return (
    <form onSubmit={handleSubmit} style={{ width: '100%' }}>
      <FormControl isInvalid={!!error}>
        <HStack spacing={2} align="start">
          <Input
            aria-label="ticker"
            placeholder="ADD TICKER (e.g. NVDA)"
            value={value}
            onChange={handleChange}
            isDisabled={isSubmitting}
            bg={inputBg}
            maxW="300px"
          />
          <Button 
            type="submit" 
            isLoading={isSubmitting} 
            loadingText="Adding"
            leftIcon={<Plus size={16} />}
            colorScheme="blue"
          >
            Add
          </Button>
        </HStack>
        {/* Render error explicitly as Text to ensure visibility in tests */}
        {error && (
          <Text color="red.300" fontSize="sm" mt={1}>
            {error}
          </Text>
        )}
      </FormControl>
    </form>
  );
};