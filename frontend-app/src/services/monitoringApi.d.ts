// src/services/monitoringApi.d.ts

export function getWatchlist(): Promise<any>;
export function getWatchlistArchive(): Promise<any>;
export function addWatchlistItem(ticker: string): Promise<any>;
export function removeWatchlistItem(ticker: string): Promise<any>;
export function setFavouriteStatus(ticker: string, is_favourite: boolean): Promise<any>;
export function removeWatchlistBatch(tickers: string[]): Promise<any>;
export function deleteFromArchive(ticker: string): Promise<any>;
export function runWatchlistRefreshJob(): Promise<any>;
