import { v4 as uuidv4 } from 'uuid';
import { MintryWallet } from './wallet';
import { installInterceptor } from './interceptor';
import { mandateStorage, ActiveMandate } from './context';
import { MintryMandateExceeded } from './exceptions';

export { MintryMandateExceeded };

let _globalWallet: MintryWallet | null = null;

export function init(options?: { apiKey?: string; dbPath?: string }): void {
  const resolvedKey = options?.apiKey || process.env.MINTRY_API_KEY;
  if (!resolvedKey) {
    throw new Error(
      "MINTRY_API_KEY must be a non-empty string. Pass apiKey to init() or set the MINTRY_API_KEY environment variable."
    );
  }

  const dbPath = options?.dbPath || '~/.mintry/vouchers.db';
  const wallet = new MintryWallet(dbPath);
  
  installInterceptor(wallet);

  if (process.env.MINTRY_JSON_LOGS !== '1') {
    console.log(`✨ Mintry Logic Fabric Active`);
  }

  _globalWallet = wallet;
}

export async function mandate<T>(task: string, cap: number, callback: () => Promise<T>): Promise<T> {
  if (!_globalWallet) {
    init(); // Will throw if MINTRY_API_KEY is missing
  }

  const wallet = _globalWallet!;
  
  let mandateId = task;
  let isShared = false;
  
  const existing = wallet.getMandate(task);
  
  // If the exact task name matches an existing allocated mandate, reuse it (shared mode)
  if (existing && existing.status !== 'unknown') {
    mandateId = task;
    isShared = true;
  } else {
    // Generate a short ID matching python "mt_" + 12 hex chars
    mandateId = `mt_${uuidv4().replace(/-/g, '').substring(0, 12)}`;
    wallet.createMandate(mandateId, cap);
  }

  const activeMandate: ActiveMandate = { id: mandateId, task, maxUsd: cap };

  try {
    return await mandateStorage.run(activeMandate, callback);
  } finally {
    if (!isShared) {
      wallet.exhaustMandate(mandateId);
    }
  }
}

export default {
  init,
  mandate,
  MintryMandateExceeded
};
