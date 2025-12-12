// frontend-app/src/services/schedulerApi.d.ts
export interface WatchlistRefreshJobResponse {
  data: {
    job_id: string;
  };
}

export function runWatchlistRefreshJob(): Promise<WatchlistRefreshJobResponse>;
