<!--
Thanks for contributing. Delete any section that doesn't apply — this is a
checklist, not a form to fill in exhaustively.
-->

## What and why

<!-- What changes, and what breaks or stays broken without it. The "why" is the
     part reviewers can't reconstruct from the diff. -->

## How it was verified

<!-- Which gates you ran, and anything you tested by hand. If it affects
     detection or speed, say what camera source you tested against. -->

```
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src/curbcam
uv run --frozen pytest
```

## Checklist

- [ ] Gates above pass locally
- [ ] `uv.lock` is unchanged (`git status uv.lock`) — see CONTRIBUTING on `--frozen`
- [ ] New settings are wired into `FIELD_LABELS` **and** a `settings_form` group
- [ ] User-visible changes update `README.md` and `CHANGELOG.md`
- [ ] New validation has a test proving it rejects bad input, not just accepts good input

## Anything left undone

<!-- Known gaps, deferred work, or pre-existing failures you found but chose not
     to fix here. Saying so is better than a reviewer discovering it later. -->
