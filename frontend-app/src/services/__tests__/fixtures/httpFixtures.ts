// frontend-app/src/services/__tests__/fixtures/httpFixtures.ts
// generic axios response/error fixtures.

import type {
  AxiosError,
  AxiosResponse,
  InternalAxiosRequestConfig,
  AxiosRequestHeaders,
} from 'axios';

export interface ApiError {
  error: string;
}

// We must satisfy InternalAxiosRequestConfig, which requires strictly typed headers.
const minimalConfig: InternalAxiosRequestConfig = {
  headers: {} as AxiosRequestHeaders,
};

export const createAxiosSuccess = <T>(
  data: T,
  status = 200,
): AxiosResponse<T> =>
  ({
    data,
    status,
    statusText: String(status),
    headers: {}, // Response headers can be simple object
    config: minimalConfig,
  } as AxiosResponse<T>);

export const createAxiosError = (
  status: number,
  message: string,
): AxiosError<ApiError> => {
  const error = new Error(message) as AxiosError<ApiError>;

  error.config = minimalConfig;
  error.code = String(status);
  error.response = {
    data: { error: message },
    status,
    statusText: String(status),
    headers: {},
    config: minimalConfig,
  } as AxiosResponse<ApiError>;

  return error;
};

export const createNetworkError = (
  message = 'Network Error',
): AxiosError<ApiError> => {
  const error = new Error(message) as AxiosError<ApiError>;
  error.config = minimalConfig;
  error.code = 'ECONNABORTED';
  error.response = undefined;
  return error;
};

// If you later add shared auth headers or pagination helpers, corresponding fixtures can live here as well.