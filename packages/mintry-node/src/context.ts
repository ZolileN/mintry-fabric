import { AsyncLocalStorage } from 'async_hooks';

export interface ActiveMandate {
  id: string;
  task: string;
  maxUsd: number;
}

export const mandateStorage = new AsyncLocalStorage<ActiveMandate>();
