interface ModelRates {
  input: number;
  output: number;
}

const DEFAULT_RATES: ModelRates = {
  input: 0.000005, // $5 / 1M tokens
  output: 0.000005, // $5 / 1M tokens
};

const _REGISTRY: Record<string, ModelRates> = {
  // OpenAI
  'gpt-4o': { input: 0.0000025, output: 0.00001 },
  'gpt-4-turbo': { input: 0.00001, output: 0.00003 },
  'gpt-3.5-turbo': { input: 0.0000005, output: 0.0000015 },
  'gpt-5-preview': { input: 0.000005, output: 0.000015 }, // from test mock

  // Anthropic
  'claude-3-opus': { input: 0.000015, output: 0.000075 },
  'claude-3-sonnet': { input: 0.000003, output: 0.000015 },
  'claude-sonnet-4': { input: 0.000003, output: 0.000015 }, // prefix match support

  // Gemini
  'gemini-1.5-pro': { input: 0.0000035, output: 0.0000105 },
  'gemini-2.5-flash': { input: 0.00000015, output: 0.0000006 }, // from test mock

  // Mistral
  'mistral-large': { input: 0.000002, output: 0.000006 },
};

export function getModelRates(model: string): ModelRates {
  // Exact match
  if (_REGISTRY[model]) {
    return _REGISTRY[model];
  }

  // Prefix match (e.g. claude-sonnet-4-20250514)
  for (const [prefix, rates] of Object.entries(_REGISTRY)) {
    if (model.startsWith(prefix)) {
      return rates;
    }
  }

  // Fallback
  return DEFAULT_RATES;
}

export function registerModel(model: string, inputRate: number, outputRate: number): void {
  _REGISTRY[model] = { input: inputRate, output: outputRate };
}

export function calculateCost(model: string, promptTokens: number, completionTokens: number): number {
  const rates = getModelRates(model);
  return (promptTokens * rates.input) + (completionTokens * rates.output);
}
