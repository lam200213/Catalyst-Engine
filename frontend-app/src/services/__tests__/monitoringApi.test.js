// frontend-app/src/services/__tests__/monitoringApi.test.js
// monitoringApi axios wrapper tests

import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

// define mock holders in a hoisted block so they are available in the mock factory
const axiosMocks = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  putMock: vi.fn(),
  deleteMock: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: axiosMocks.getMock,
      post: axiosMocks.postMock,
      put: axiosMocks.putMock,
      delete: axiosMocks.deleteMock,
    })),
  },
}));

// import fixtures and the service under test
import {
  mockGetWatchlistResponse,
  mockEmptyWatchlistResponse,
  mockGetWatchlistArchiveResponse,
  mockAddWatchlistItemResponseAAPL,
  mockWatchlistFavouriteResponseAAPL,
  mockWatchlistBatchRemoveResponse,
  mockDeleteArchiveResponseCRM,
  mockMarketHealthResponse,
} from './fixtures/monitoringFixtures';

import {
  createAxiosSuccess,
  createAxiosError,
  createNetworkError,
} from './fixtures/httpFixtures';

import {
  getMarketHealth,
  getWatchlist,
  addWatchlistItem,
  removeWatchlistItem,
  setFavouriteStatus,
  removeWatchlistBatch,
  getWatchlistArchive,
  deleteFromArchive,
} from '../monitoringApi';

describe('monitoringApi service layer', () => {
  beforeEach(() => {
    axiosMocks.getMock.mockReset();
    axiosMocks.postMock.mockReset();
    axiosMocks.putMock.mockReset();
    axiosMocks.deleteMock.mockReset();
  });

  it('getWatchlist sends GET /monitor/watchlist and returns data on 200 OK', async () => {
    // Arrange
    axiosMocks.getMock.mockResolvedValueOnce(
      createAxiosSuccess(mockGetWatchlistResponse, 200),
    );

    // Act
    const response = await getWatchlist();

    // Assert
    expect(axiosMocks.getMock).toHaveBeenCalledWith('/monitor/watchlist');
    expect(response.data).toEqual(mockGetWatchlistResponse);
  });

  it('getWatchlist propagates 503 Service Unavailable as a rejected promise with ApiError', async () => {
    // Arrange
    axiosMocks.getMock.mockRejectedValueOnce(
      createAxiosError(503, 'Service unavailable - database connection failed'),
    );

    // Act / Assert
    await expect(getWatchlist()).rejects.toMatchObject({
      response: { status: 503 },
    });
  });

  it('getWatchlist propagates 500 Internal Server Error with invalid format message', async () => {
    // Arrange
    axiosMocks.getMock.mockRejectedValueOnce(
      createAxiosError(500, 'Invalid response format'),
    );

    // Act / Assert
    await expect(getWatchlist()).rejects.toMatchObject({
      response: { status: 500, data: { error: 'Invalid response format' } },
    });
  });

  it('getWatchlist propagates network failures (no response) as-is', async () => {
    // Arrange
    axiosMocks.getMock.mockRejectedValueOnce(createNetworkError('Network timeout'));

    // Act / Assert
    await expect(getWatchlist()).rejects.toMatchObject({
      code: 'ECONNABORTED',
    });
  });

  it('addWatchlistItem uppercases ticker and calls PUT /monitor/watchlist/{TICKER} with no body', async () => {
    // Arrange
    axiosMocks.putMock.mockResolvedValueOnce(
      createAxiosSuccess(mockAddWatchlistItemResponseAAPL, 201),
    );

    // Act
    const response = await addWatchlistItem('aapl');

    // Assert
    expect(axiosMocks.putMock).toHaveBeenCalledWith('/monitor/watchlist/AAPL');
    expect(response.data).toEqual(mockAddWatchlistItemResponseAAPL);
  });

  it('addWatchlistItem surfaces 400 Bad Request for invalid ticker format', async () => {
    // Arrange
    axiosMocks.putMock.mockRejectedValueOnce(
      createAxiosError(400, 'Invalid ticker format'),
    );

    // Act / Assert
    await expect(addWatchlistItem('@@@')).rejects.toMatchObject({
      response: { status: 400 },
    });
  });

  it('addWatchlistItem surfaces 503 Service Unavailable errors', async () => {
    // Arrange
    axiosMocks.putMock.mockRejectedValueOnce(
      createAxiosError(503, 'Service Unavailable'),
    );

    // Act / Assert
    await expect(addWatchlistItem('AAPL')).rejects.toMatchObject({
      response: { status: 503 },
    });
  });

  it('removeWatchlistItem calls DELETE /monitor/watchlist/{TICKER} with uppercase ticker', async () => {
    // Arrange
    axiosMocks.deleteMock.mockResolvedValueOnce(
      createAxiosSuccess({ message: 'ok' }, 200),
    );

    // Act
    const response = await removeWatchlistItem('net');

    // Assert
    expect(axiosMocks.deleteMock).toHaveBeenCalledWith('/monitor/watchlist/NET');
    expect(response.data).toEqual({ message: 'ok' });
  });

  it('removeWatchlistItem surfaces 503 Service Unavailable errors', async () => {
    // Arrange
    axiosMocks.deleteMock.mockRejectedValueOnce(
      createAxiosError(503, 'DB unavailable'),
    );

    // Act / Assert
    await expect(removeWatchlistItem('NET')).rejects.toMatchObject({
      response: { status: 503 },
    });
  });

  it('setFavouriteStatus calls POST /monitor/watchlist/{TICKER}/favourite with { is_favourite: boolean } body', async () => {
    // Arrange
    axiosMocks.postMock.mockResolvedValueOnce(
      createAxiosSuccess(mockWatchlistFavouriteResponseAAPL, 200),
    );

    // Act
    const response = await setFavouriteStatus('aapl', true);

    // Assert
    expect(axiosMocks.postMock).toHaveBeenCalledWith(
      '/monitor/watchlist/AAPL/favourite',
      { is_favourite: true },
    );
    expect(response.data).toEqual(mockWatchlistFavouriteResponseAAPL);
  });

  it('setFavouriteStatus surfaces 400 Bad Request when body is invalid', async () => {
    // Arrange
    axiosMocks.postMock.mockRejectedValueOnce(
      createAxiosError(400, 'Field is_favourite must be a boolean'),
    );

    // Act / Assert
    await expect(setFavouriteStatus('AAPL', true)).rejects.toMatchObject({
      response: { status: 400 },
    });
  });

  it('setFavouriteStatus surfaces 404 Not Found when watchlist item does not exist', async () => {
    // Arrange
    axiosMocks.postMock.mockRejectedValueOnce(
      createAxiosError(404, 'Watchlist item ZZZZZ not found'),
    );

    // Act / Assert
    await expect(setFavouriteStatus('ZZZZZ', true)).rejects.toMatchObject({
      response: { status: 404 },
    });
  });

  it('setFavouriteStatus surfaces 503 Service Unavailable', async () => {
    // Arrange
    axiosMocks.postMock.mockRejectedValueOnce(
      createAxiosError(503, 'Service Unavailable'),
    );

    // Act / Assert
    await expect(setFavouriteStatus('AAPL', false)).rejects.toMatchObject({
      response: { status: 503 },
    });
  });

  it('removeWatchlistBatch calls POST /monitor/watchlist/batch/remove with uppercase tickers body', async () => {
    // Arrange
    axiosMocks.postMock.mockResolvedValueOnce(
      createAxiosSuccess(mockWatchlistBatchRemoveResponse, 200),
    );

    // Act
    const response = await removeWatchlistBatch(['aapl', 'net']);

    // Assert
    expect(axiosMocks.postMock).toHaveBeenCalledWith(
      '/monitor/watchlist/batch/remove',
      { tickers: ['AAPL', 'NET'] },
    );
    expect(response.data).toEqual(mockWatchlistBatchRemoveResponse);
  });

  it('removeWatchlistBatch surfaces 400 Bad Request for invalid payload', async () => {
    // Arrange
    axiosMocks.postMock.mockRejectedValueOnce(
      createAxiosError(400, 'Field tickers is required'),
    );

    // Act / Assert
    await expect(removeWatchlistBatch([])).rejects.toMatchObject({
      response: { status: 400 },
    });
  });

  it('removeWatchlistBatch surfaces 400 Bad Request when over ticker limit', async () => {
    // Arrange
    axiosMocks.postMock.mockRejectedValueOnce(
      createAxiosError(
        400,
        'Cannot remove more than 1000 tickers in a single request',
      ),
    );

    // Act / Assert
    await expect(
      removeWatchlistBatch(new Array(1001).fill('AAPL')),
    ).rejects.toMatchObject({
      response: { status: 400 },
    });
  });

  it('removeWatchlistBatch surfaces 503 Service Unavailable errors', async () => {
    // Arrange
    axiosMocks.postMock.mockRejectedValueOnce(
      createAxiosError(503, 'Service Unavailable'),
    );

    // Act / Assert
    await expect(removeWatchlistBatch(['AAPL'])).rejects.toMatchObject({
      response: { status: 503 },
    });
  });

  it('getWatchlistArchive sends GET /monitor/archive and returns data on 200 OK', async () => {
    // Arrange
    axiosMocks.getMock.mockResolvedValueOnce(
      createAxiosSuccess(mockGetWatchlistArchiveResponse, 200),
    );

    // Act
    const response = await getWatchlistArchive();

    // Assert
    expect(axiosMocks.getMock).toHaveBeenCalledWith('/monitor/archive');
    expect(response.data).toEqual(mockGetWatchlistArchiveResponse);
  });

  it('getWatchlistArchive surfaces 503 Service Unavailable errors', async () => {
    // Arrange
    axiosMocks.getMock.mockRejectedValueOnce(
      createAxiosError(503, 'Service Unavailable'),
    );

    // Act / Assert
    await expect(getWatchlistArchive()).rejects.toMatchObject({
      response: { status: 503 },
    });
  });

  it('deleteFromArchive calls DELETE /monitor/archive/{TICKER} with uppercase ticker', async () => {
    // Arrange
    axiosMocks.deleteMock.mockResolvedValueOnce(
      createAxiosSuccess(mockDeleteArchiveResponseCRM, 200),
    );

    // Act
    const response = await deleteFromArchive('crm');

    // Assert
    expect(axiosMocks.deleteMock).toHaveBeenCalledWith('/monitor/archive/CRM');
    expect(response.data).toEqual(mockDeleteArchiveResponseCRM);
  });

  it('deleteFromArchive surfaces 400 Bad Request for invalid ticker format', async () => {
    // Arrange
    axiosMocks.deleteMock.mockRejectedValueOnce(
      createAxiosError(400, 'Invalid ticker format'),
    );

    // Act / Assert
    await expect(deleteFromArchive('@@@')).rejects.toMatchObject({
      response: { status: 400 },
    });
  });

  it('deleteFromArchive surfaces 404 Not Found when ticker not found', async () => {
    // Arrange
    axiosMocks.deleteMock.mockRejectedValueOnce(
      createAxiosError(404, 'Ticker not found'),
    );

    // Act / Assert
    await expect(deleteFromArchive('ZZZZZ')).rejects.toMatchObject({
      response: { status: 404 },
    });
  });

  it('deleteFromArchive surfaces 503 Service Unavailable errors', async () => {
    // Arrange
    axiosMocks.deleteMock.mockRejectedValueOnce(
      createAxiosError(503, 'Service Unavailable'),
    );

    // Act / Assert
    await expect(deleteFromArchive('CRM')).rejects.toMatchObject({
      response: { status: 503 },
    });
  });

  it('getMarketHealth sends GET /monitor/market-health and returns MarketHealthResponse on 200 OK', async () => {
    // Arrange
    axiosMocks.getMock.mockResolvedValueOnce(
      createAxiosSuccess(mockMarketHealthResponse, 200),
    );

    // Act
    const response = await getMarketHealth();

    // Assert
    expect(axiosMocks.getMock).toHaveBeenCalledWith('/monitor/market-health');
    expect(response.data).toEqual(mockMarketHealthResponse);
  });

  it('getMarketHealth surfaces 503 and 500 error responses and network failures', async () => {
    // 503
    axiosMocks.getMock.mockRejectedValueOnce(
      createAxiosError(503, 'Service Unavailable'),
    );
    await expect(getMarketHealth()).rejects.toMatchObject({
      response: { status: 503 },
    });

    // 500
    axiosMocks.getMock.mockRejectedValueOnce(
      createAxiosError(500, 'Internal Server Error'),
    );
    await expect(getMarketHealth()).rejects.toMatchObject({
      response: { status: 500 },
    });

    // network
    axiosMocks.getMock.mockRejectedValueOnce(createNetworkError('timeout'));
    await expect(getMarketHealth()).rejects.toMatchObject({
      code: 'ECONNABORTED',
    });
  });

  it('monitoringApi does not override global auth headers configured on axios client', async () => {
    // Arrange
    // Here we only assert that headers are not explicitly passed or mutated;
    // global auth configuration should be applied in axios.create, not per call.
    axiosMocks.getMock.mockResolvedValueOnce(
      createAxiosSuccess(mockEmptyWatchlistResponse, 200),
    );

    // Act
    await getWatchlist();

    // Assert
    const callArgs = axiosMocks.getMock.mock.calls[0];
    expect(callArgs.length).toBe(1);
    expect(callArgs[0]).toBe('/monitor/watchlist');
  });
});
