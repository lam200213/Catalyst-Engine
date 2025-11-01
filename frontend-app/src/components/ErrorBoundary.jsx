// frontend-app/src/components/ErrorBoundary.jsx
import React from 'react';
import { Alert, AlertIcon, Box, Button, VStack, Text, Code } from '@chakra-ui/react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // Log to console with full stack trace
    console.error('[ErrorBoundary] Component crashed:', error);
    console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack);
    
    // Store error info for display in dev mode
    this.setState({ errorInfo });
    
    // Send to error monitoring service in production
    if (import.meta.env.PROD) {
      // Example: Sentry.captureException(error, { contexts: { react: errorInfo } });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box p={4} borderWidth="1px" borderRadius="md" bg="red.50">
          <VStack align="stretch" spacing={3}>
            <Alert status="error">
              <AlertIcon />
              <Box flex="1">
                <Text fontWeight="bold">Something went wrong</Text>
                <Text fontSize="sm">
                  {this.state.error?.message || 'An unexpected error occurred'}
                </Text>
              </Box>
            </Alert>
            
            {/* Show details in dev mode */}
            {import.meta.env.DEV && this.state.errorInfo && (
              <Box bg="gray.100" p={3} borderRadius="md" fontSize="xs" overflow="auto">
                <Text fontWeight="bold" mb={2}>Error Details (Dev Mode):</Text>
                <Code display="block" whiteSpace="pre-wrap">
                  {this.state.errorInfo.componentStack}
                </Code>
              </Box>
            )}
            
            <Button 
              onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
              colorScheme="blue"
              size="sm"
            >
              Try Again
            </Button>
          </VStack>
        </Box>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
