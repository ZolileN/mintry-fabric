import { calculateCost } from './pricing';
import { MintryMandateExceeded } from './exceptions';
import { MintryWallet } from './wallet';
import { mandateStorage } from './context';

const LLM_HOSTS = [
  'api.openai.com',
  'api.anthropic.com',
  'generativelanguage.googleapis.com',
  'api.mistral.ai',
];

function isLlmRequest(url: string | URL | Request): boolean {
  const urlStr = url.toString();
  return LLM_HOSTS.some(host => urlStr.includes(host));
}

function extractModel(body: any): string {
  if (typeof body === 'string') {
    try {
      const parsed = JSON.parse(body);
      return parsed.model || 'unknown';
    } catch {
      return 'unknown';
    }
  }
  return 'unknown';
}

function checkIntent(body: any, mandateId: string): void {
  if (typeof body === 'string') {
    try {
      const parsed = JSON.parse(body);
      const messages = parsed.messages || [];
      const prompt = messages.map((m: any) => m.content).join(' ').toLowerCase();
      const prohibited = ["bypass wallet", "disable mintry", "delete vouchers.db"];
      if (prohibited.some(p => prompt.includes(p))) {
        if (process.env.MINTRY_JSON_LOGS === '1') {
          console.log(JSON.stringify({ event: 'security_violation', mandate_id: mandateId, reason: 'prohibited_intent' }));
        }
        throw new Error("Mintry Logic Fabric: Prohibited Intent Detected (Security Violation).");
      }
    } catch (e) {
      if (e instanceof Error && e.message.includes("Mintry Logic Fabric")) {
        throw e;
      }
    }
  }
}

let installed = false;
let originalFetch: typeof globalThis.fetch | null = null;

export function installInterceptor(wallet: MintryWallet) {
  if (installed) return;
  
  originalFetch = globalThis.fetch;
  
  globalThis.fetch = async function (input: string | URL | Request, init?: RequestInit): Promise<Response> {
    const urlStr = input.toString();
    const isLlm = isLlmRequest(urlStr);
    
    // Check if we have an active mandate in context, otherwise fallback to headers or default
    let mandateId = 'mt_task_882x';
    const activeMandate = mandateStorage.getStore();
    
    if (activeMandate) {
      mandateId = activeMandate.id;
    } else if (init?.headers) {
      // Check for x-mintry-mandate header
      let headers: Headers;
      if (init.headers instanceof Headers) {
        headers = init.headers;
      } else if (Array.isArray(init.headers)) {
        headers = new Headers(init.headers);
      } else {
        headers = new Headers(init.headers as Record<string, string>);
      }
      const headerVal = headers.get('x-mintry-mandate');
      if (headerVal) mandateId = headerVal;
    }

    if (isLlm) {
      // Phase 1: Expiry check
      if (wallet.isExpired(mandateId)) {
        const mandate = wallet.getMandate(mandateId);
        throw new MintryMandateExceeded(mandate.id, mandate.budget_usd, mandate.spent_usd);
      }

      // Phase 2: Budget check
      const mandate = wallet.getMandate(mandateId);
      if (mandate.status === 'exhausted') {
        throw new MintryMandateExceeded(mandate.id, mandate.budget_usd, mandate.spent_usd);
      }

      const remaining = mandate.budget_usd - mandate.spent_usd;
      if (remaining < 0.01) {
        throw new MintryMandateExceeded(mandate.id, mandate.budget_usd, mandate.spent_usd);
      }

      // Phase 3: Intent check
      if (init?.body) {
        checkIntent(init.body, mandateId);
      }
    }

    // 3. FLIGHT
    const response = await originalFetch!(input, init);

    // 4. POST-FLIGHT METERING
    if (isLlm && response.status === 200) {
      // We need to clone the response to read the body without consuming it for the caller
      const clonedResponse = response.clone();
      try {
        const data = await clonedResponse.json();
        const usage = data.usage || {};
        const model = data.model || extractModel(init?.body);
        
        const promptTokens = usage.prompt_tokens || 0;
        const completionTokens = usage.completion_tokens || 0;

        const actualCost = calculateCost(model, promptTokens, completionTokens);
        wallet.recordUsage(mandateId, actualCost);
      } catch (err) {
        // Silently ignore if response isn't JSON or can't be parsed
      }
    }

    return response;
  };
  
  installed = true;
  if (process.env.MINTRY_JSON_LOGS === '1') {
    console.log(JSON.stringify({ event: 'hooks_installed', status: 'success' }));
  } else {
    console.log("✨ Mintry Logic Fabric Hooked into fetch");
  }
}

export function resetInterceptor() {
  if (originalFetch) {
    globalThis.fetch = originalFetch;
    originalFetch = null;
  }
  installed = false;
}
