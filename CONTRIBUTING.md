# Contributing

## Scope

This repository is a research prototype. Contributions should preserve scientific traceability and experimental honesty.

## Before opening a pull request

1. Run `python3 -m unittest discover -s tests -v`.
2. Document any behavioral change in `CHANGELOG.md`.
3. Do not hardcode personal paths, wallets, secrets, or hardware-specific assumptions.
4. Distinguish experimental claims from verified results.

## Contribution guidelines

- Prefer small, reviewable pull requests.
- Add or update tests for bug fixes.
- Keep artifact schemas stable unless a migration is documented.
- Do not replace measured values with constants just to satisfy tests.
