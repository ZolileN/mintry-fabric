## Summary
What does this PR change?

## Why
Why is this change needed?

## Related Ticket
Link ticket / issue / task

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Refactor
- [ ] Performance improvement
- [ ] Security fix
- [ ] Documentation update
- [ ] Test update

## What Was Changed
- 
- 
- 

## Testing Done
- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual testing
- [ ] Existing tests pass

Describe test steps and results:

## Screenshots / Demo
Add screenshots or demo notes if relevant.

## Risks / Impact
Any risky areas, migrations, breaking changes, or rollout concerns?

## Architecture Principles
Please confirm this feature aligns with our [Six Architecture Principles](docs/ARCHITECTURE.md):
- [ ] **Initialize once**: No additional init steps added for new governance changes.
- [ ] **Author centrally**: No in-place mutations of past spend ledgers.
- [ ] **Enforce locally**: No synchronous network calls added to the LLM path.
- [ ] **Sync asynchronously**: State syncs via polling, fail open/closed handles offline gracefully.
- [ ] **Fail to last-known-good**: If unreachable, falls back correctly.
- [ ] **Stay deterministic**: Feature is explicitly "allow/block/number" in the enforcement path.

## Checklist
- [ ] Code builds successfully
- [ ] Tests pass
- [ ] Linting and formatting completed
- [ ] No secrets included
- [ ] Documentation updated if needed
- [ ] Change is scoped and focused
