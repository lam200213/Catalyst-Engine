// frontend-app/src/components/ErrorBoundary.jsx
import React from 'react';
import { Alert, AlertIcon, Box, Button, VStack } from '@chakra-ui/react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box p={6}>
          <Alert status="error">
            <AlertIcon />
            Something went wrong. Please refresh the page.
          </Alert>
          <Button 
            mt={4} 
            onClick={() => this.setState({ hasError: false, error: null })}
            colorScheme="blue"
          >
            Try Again
          </Button>
        </Box>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
