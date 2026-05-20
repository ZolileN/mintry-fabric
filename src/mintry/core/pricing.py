"""
Per-model token pricing registry for the Mintry Logic Fabric.

Prices are in USD per token. The registry supports both input (prompt) and
output (completion) pricing, which vary by model and provider.
"""

from typing import Optional


# Default pricing table — USD per token
# Sources: published provider pricing pages as of 2026-Q2
_PRICING_TABLE: dict[str, dict[str, float]] = {
    # --- OpenAI ---
    "gpt-5-preview":        {"input": 0.000005, "output": 0.000015},
    "gpt-5":                {"input": 0.000005, "output": 0.000015},
    "gpt-4.1":              {"input": 0.000002, "output": 0.000008},
    "gpt-4.1-mini":         {"input": 0.0000004, "output": 0.0000016},
    "gpt-4.1-nano":         {"input": 0.0000001, "output": 0.0000004},
    "gpt-4o":               {"input": 0.0000025, "output": 0.00001},
    "gpt-4o-mini":          {"input": 0.00000015, "output": 0.0000006},
    "o3":                   {"input": 0.00001, "output": 0.00004},
    "o3-mini":              {"input": 0.0000011, "output": 0.0000044},
    "o4-mini":              {"input": 0.0000011, "output": 0.0000044},

    # --- Anthropic ---
    "claude-sonnet-4-20250514":     {"input": 0.000003, "output": 0.000015},
    "claude-opus-4-20250514":       {"input": 0.000015, "output": 0.000075},
    "claude-3-5-haiku-20241022":    {"input": 0.0000008, "output": 0.000004},

    # --- Google Gemini ---
    "gemini-2.5-pro":       {"input": 0.00000125, "output": 0.00001},
    "gemini-2.5-flash":     {"input": 0.00000015, "output": 0.0000006},
    "gemini-2.0-flash":     {"input": 0.0000001, "output": 0.0000004},

    # --- Mistral ---
    "mistral-large-latest": {"input": 0.000002, "output": 0.000006},
    "mistral-small-latest": {"input": 0.0000001, "output": 0.0000003},
}

# Fallback rate when model is not found in the table
_DEFAULT_RATE: dict[str, float] = {"input": 0.000005, "output": 0.000005}


def calculate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """
    Calculate the USD cost for a request based on model-specific pricing.

    Args:
        model: The model identifier (e.g. "gpt-5-preview", "claude-sonnet-4-20250514").
        prompt_tokens: Number of input/prompt tokens.
        completion_tokens: Number of output/completion tokens.

    Returns:
        Total cost in USD.
    """
    rates = get_model_rates(model)
    return (prompt_tokens * rates["input"]) + (completion_tokens * rates["output"])


def get_model_rates(model: str) -> dict[str, float]:
    """
    Look up the per-token rates for a model.

    Falls back to the default rate if the model is not in the pricing table.
    Performs a prefix match for versioned model strings (e.g. "gpt-4o-2024-08-06"
    will match "gpt-4o").
    """
    # Exact match first
    if model in _PRICING_TABLE:
        return _PRICING_TABLE[model]

    # Prefix match for versioned model strings
    for known_model in sorted(_PRICING_TABLE.keys(), key=len, reverse=True):
        if model.startswith(known_model):
            return _PRICING_TABLE[known_model]

    return _DEFAULT_RATE


def register_model(model: str, input_rate: float, output_rate: float) -> None:
    """
    Register a custom model with per-token pricing.

    Use this for fine-tuned models or providers not yet in the default table.

    Args:
        model: The model identifier.
        input_rate: USD per input token.
        output_rate: USD per output token.
    """
    _PRICING_TABLE[model] = {"input": input_rate, "output": output_rate}


def list_models() -> list[str]:
    """Return all model names currently in the pricing table."""
    return sorted(_PRICING_TABLE.keys())
