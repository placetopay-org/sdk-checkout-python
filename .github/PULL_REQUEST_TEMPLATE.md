# Pull Request

## Summary

<!-- One sentence. What does this PR change and why is it needed? -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking, additive)
- [ ] Breaking change (requires major version bump)
- [ ] Docs / tests only
- [ ] Dependency update

## Checklist

- [ ] `pytest tests/` passes locally (coverage ≥ 85% enforced).
- [ ] `ruff check` + `ruff format` + `mypy src` are clean.
- [ ] I updated `CHANGELOG.md` under `Unreleased` if this is a user-visible change.
- [ ] If the auth test vector was touched, the regression still matches the `.NET` and `Java` SDKs (see ARCHITECTURE.md §3).
- [ ] I did NOT commit credentials, tokens or sandbox payloads (`*.webhook.json` is gitignored).

## Cross-SDK parity

- [ ] This change is Python-only.
- [ ] This change should also be mirrored in `checkout-dotnet` and `checkout-java`.
       <!-- Link sibling PRs or open issues: -->

## Testing

<!--
How did you verify this works? Include:
  - the command you ran
  - screenshots / log snippets if UI / behavior changed
  - sandbox output if you ran an E2E test
-->
