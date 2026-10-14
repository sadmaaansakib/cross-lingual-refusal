# Contributing

Thank you for your interest in contributing to this project. We welcome
improvements that remain within the project's representational-analysis
scope.

## Before Opening a Pull Request

1. **Fork** the repository and create a feature branch from `main`.
2. **Ensure** your changes pass `ruff check src/ scripts/` (zero warnings).
3. **Add or update** docstrings and comments for any changed logic.
4. **Run the full pipeline** on the template dataset to confirm end-to-end
   correctness before submission.

## Code Style

- Python 3.10+ compatible syntax.
- Use type hints for all public functions.
- Follow the existing import ordering (stdlib → third-party → local).
- Keep line length under 100 characters.

## Scope and Safety Policy

This repository performs **representation analysis only** — it does not
fine-tune models, generate text, or produce actionable harmful content.

**Do not open PRs that:**
- Add real harmful instructions to any data template or fixture.
- Weaken or bypass deployed model safety mechanisms.
- Include API keys, passwords, or other credentials.
- Introduce optional dependencies that require closed-source or licensed
  data not available to all users.

## Reporting Issues

Please use the GitHub Issue templates:
- **Bug report** – for reproducibility failures or incorrect output.
- **Feature request** – for new analysis modules within the research scope.
- **Data quality** – for issues with the public template dataset.

## Sensitive Data

All sensitive benchmark files must remain in restricted institutional storage
and must **never** be committed to this repository. The `.gitignore` excludes
`data/processed/prompts.csv` and all `.npy` activation artifacts for this reason.

## License

By contributing you agree that your contributions will be released under the
project's [MIT License](LICENSE).
