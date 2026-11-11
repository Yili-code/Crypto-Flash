# Google Calendar button test

Updated: 2026-11-11 Asia/Taipei.
Branch: codex/calendar-button-test. Baseline: 16b9c32.

Scope: opt-in test-group preview with a sample event, Telegram URL markup, offline checks, and bilingual usage notes. Production schedule and delivery state are outside this scope. Live test pending test-group destination.

Updated: 2026-11-11T22:54:28+08:00.
- Implemented an opt-in CPI sample with a 15-minute Google Calendar link. The preview bypasses production scheduling and delivery state. Telegram's HTML fallback retains the keyboard.
- Verified: Ruff and diff checks passed, and all 66 focused tests passed. The full suite had 383 passes and two Windows access errors replacing unrelated Gemini and YouTube state files.
- Live preview was rejected before network send because the supplied destination matches the local default. Awaiting confirmation or a different test group.
- Next: verify Telegram delivery and the mobile calendar opening flow. Feature branch publication pending.

Updated: 2026-11-11T22:55:17+08:00.
- Rebased onto b2eb762. The user confirmed the locally configured destination for a single labeled test. Telegram accepted the CPI sample with the inline keyboard using the existing configured bot. The destination guard was overridden only in that process, and the scheduled reminder was not run.
- Mobile opening and saving remain unverified. The feature is on the dedicated branch for remote handoff, without a main merge or deployment.
