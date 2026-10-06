# Contributing to Crypto Flash

Crypto Flash is a personal monitoring system with external-data, AI, and messaging boundaries. Contributions are welcome when they preserve explicit failure behavior and can be verified without production credentials.

## Before opening a change

- Use an issue to describe bugs, new data sources, or behavior changes before a large implementation.
- Keep each pull request focused on one problem.
- Do not include API keys, Telegram chat IDs, private messages, production state, or copied publisher content.
- Do not weaken the fail-closed behavior: an unsuccessful Gemini summary must not be presented as a completed analysis.
- New sources must use permitted HTTPS endpoints, retain source attribution, and define deduplication behavior.

## Local setup

Use Python 3.12 from the repository root:

```bash
python -m venv .venv
python -m pip install -r requirements-dev.txt
```

Activate `.venv` using the command for your operating system, then run:

```bash
python -m ruff check .
python -m pytest
```

The automated test suite must not require network access or real secrets. Add or update a fixture when changing parsers, retry logic, state transitions, or message formatting.

## Pull-request checklist

- Explain the user-visible problem and why the proposed scope is sufficient.
- Describe failure behavior, state-file changes, and external API effects.
- Add tests for the changed behavior.
- Update the relevant English and Traditional Chinese documentation together.
- Confirm that no secret or personal data appears in the diff.
- Include screenshots only when the visible Telegram output changes, and redact identifiers.

## Useful contribution areas

- Reproducible parser fixtures for upstream format changes
- Offline tests for error and recovery paths
- Documentation corrections and Windows/macOS/Linux setup checks
- Additional official or publisher-provided RSS/Atom sources
- Accessibility improvements to screenshots and documentation

Contributions are accepted under the repository's [MIT License](LICENSE).
