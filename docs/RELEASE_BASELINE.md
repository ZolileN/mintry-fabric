# Release Baseline - v0.6.0 / v1.0.0-rc1

**Date Recorded:** 2026-05-20
**Environment:** Clean synced virtual environment via `uv sync`

This document records the exact test suite output across both the Python and Node.js SDKs, establishing the baseline before finalizing the v1.0.0 release.

## Python SDK (pytest)

```text
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: /home/zolile/Documents/mintry-fabric
configfile: pyproject.toml
plugins: anyio-4.13.0, httpx-0.36.2
collecting ... collected 44 items

tests/test_allocated_budget_usage.py::test_allocated_budget_can_be_reused_and_spent PASSED
tests/test_allocated_budget_usage.py::test_allocated_budget_can_be_spent_via_metered_openai_request PASSED
tests/test_audit_log_cli.py::test_wallet_logs_create_and_top_up PASSED
tests/test_audit_log_cli.py::test_wallet_logs_spend_and_exhaust PASSED
tests/test_audit_log_cli.py::test_wallet_logs_expiration PASSED
tests/test_audit_log_cli.py::test_cli_list_mandates PASSED
tests/test_audit_log_cli.py::test_cli_inspect_mandate PASSED
tests/test_audit_log_cli.py::test_cli_inspect_nonexistent_mandate PASSED
tests/test_audit_log_cli.py::test_cli_list_mandates_accepts_db_after_subcommand PASSED
tests/test_audit_log_cli.py::test_cli_dashboard_accepts_db_after_subcommand PASSED
tests/test_dynamic_mandate.py::test_shield_creates_real_mandate PASSED
tests/test_dynamic_mandate.py::test_dynamic_mandate_routing PASSED
tests/test_dynamic_mandate.py::test_budget_exhausted_error_includes_details PASSED
tests/test_dynamic_mandate.py::test_init_rejects_empty_api_key PASSED
tests/test_intent_fabric.py::test_intent_blocking PASSED
tests/test_metering.py::test_real_time_metering PASSED
tests/test_mintry_fabric.py::test_logic_fabric_enforcement PASSED
tests/test_mpp_bridge.py::test_mpp_resurrection PASSED
tests/test_observability.py::test_json_logging_format PASSED
tests/test_observability.py::test_webhook_alert_dispatch PASSED
tests/test_observability.py::test_dashboard_api_stats PASSED
tests/test_observability.py::test_dashboard_server_http PASSED
tests/test_observability.py::test_dashboard_budget_allocation_flow PASSED
tests/test_sprint3.py::test_async_interception_metering[asyncio] PASSED
tests/test_sprint3.py::test_async_budget_enforcement[asyncio] PASSED
tests/test_sprint3.py::test_async_intent_blocking[asyncio] PASSED
tests/test_sprint3.py::test_per_model_pricing_openai PASSED
tests/test_sprint3.py::test_per_model_pricing_anthropic PASSED
tests/test_sprint3.py::test_per_model_pricing_gemini PASSED
tests/test_sprint3.py::test_per_model_pricing_fallback PASSED
tests/test_sprint3.py::test_custom_model_registration PASSED
tests/test_sprint3.py::test_pricing_integrated_with_interceptor PASSED
tests/test_sprint3.py::test_expired_mandate_rejected PASSED
tests/test_sprint3.py::test_active_mandate_not_expired PASSED
tests/test_sprint3.py::test_mandate_without_expiry_never_expires PASSED
tests/test_sprint3.py::test_valid_signature_verification PASSED
tests/test_sprint3.py::test_invalid_signature_rejected PASSED
tests/test_sprint3.py::test_wrong_key_rejected PASSED
tests/test_sprint3.py::test_malformed_signature_raises PASSED
tests/test_sprint3.py::test_expired_mandate_model PASSED
tests/test_three_lines_ergonomics.py::test_mintry_mandate_exceeded_attributes PASSED
tests/test_three_lines_ergonomics.py::test_init_with_env_var PASSED
tests/test_three_lines_ergonomics.py::test_three_line_syntax PASSED
tests/test_three_lines_ergonomics.py::test_auto_init_on_mandate PASSED

============================= 44 passed in 25.32s ==============================
```

## Node.js SDK (node:test)

```text
TAP version 13
# ✨ Mintry Logic Fabric Hooked into fetch
# ✨ Mintry Logic Fabric Active
# ✨ Mintry Logic Fabric Hooked into fetch
# ✨ Mintry Logic Fabric Active
# ✨ Mintry Logic Fabric Hooked into fetch
# ✨ Mintry Logic Fabric Active
# Subtest: TypeScript SDK Ergonomics
    # Subtest: three-line syntax works
    ok 1 - three-line syntax works
      ---
      duration_ms: 1426.177949
      type: 'test'
      ...
    # Subtest: blocks exhausted mandates
    ok 2 - blocks exhausted mandates
      ---
      duration_ms: 177.828407
      type: 'test'
      ...
    # Subtest: blocks malicious intent
    ok 3 - blocks malicious intent
      ---
      duration_ms: 159.509874
      type: 'test'
      ...
    1..3
ok 1 - TypeScript SDK Ergonomics
  ---
  duration_ms: 1765.93845
  type: 'suite'
  ...
1..1
# tests 3
# suites 1
# pass 3
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 2433.06628
```
