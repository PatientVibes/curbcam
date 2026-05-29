## Summary

<!-- 1–3 bullets: what changes and why. Link the spec/plan section if relevant. -->

## Test plan

<!-- How you verified. The CI workflow runs ruff + mypy + pytest; note anything CI can't cover. -->

- [ ] `ruff check .` clean
- [ ] `mypy src/curbcam` (strict) clean
- [ ] `pytest` green (add/adjust tests for the change)
- [ ] Manual / e2e check if UI or wizard behavior changed (`pytest -m e2e`)
