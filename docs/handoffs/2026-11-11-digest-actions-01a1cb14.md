# Daily digest workflow recovery

Updated: 2026-11-11T22:50:26+08:00
Branch: main. Baseline: 23ba36e.

- Fast-forwarded after checking tracked changes and upstream paths. Preserved two untracked handoffs.
- Reviewed the latest 50 runs. The three failures were Daily news digest: HTTP 503 in 42572467398 and 42773762143, and aggregate length validation in 42970555768.
- Scope: daily digest generation and retry, offline regression tests, English and Traditional Chinese docs. Keep delivery failures visible and preserve quota, source checks and delivery state.
- Implementation, verification and push pending.
- Implemented tighter generation budgets, a two-topic repair for aggregate overflow, and validation of the rendered body length. The scheduled job can retry one transient provider failure after its persisted cooldown, up to 120 seconds. The existing request guard still authorizes each request.
- Ruff passed. Focused digest and Gemini policy tests: 62 passed. The local full suite encountered three Windows file replacement access errors in the unchanged YouTube scheduler tests. Linux CI pending.
- The recent failure history shows later successful runs for Jin10, YouTube, calendar, and CI. Historical failures remain visible in GitHub.
- Next: publish this change and inspect Linux CI and the next scheduled digest. No manual production dispatch.
