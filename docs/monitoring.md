# Daily operational metrics

The live flash monitor writes a durable daily record to `data/monitoring_daily.json`. The GitHub Actions workflow persists this file with the other runtime state when each six-hour monitor run ends. No dashboard or external metrics service is required.

Days use `Asia/Taipei` calendar dates and are retained for 35 days by default. Set `MONITORING_RETENTION_DAYS` to change the retention window or `MONITORING_METRICS_FILE` to change the file path.

## Metric definitions

- `received_events`: source items observed after startup baselines. RSS snapshots include both new and previously seen entries; the latter also contribute to `duplicates_blocked`.
- `keyword_filter_passed`: unique queued events that matched the configured keyword filter.
- `pushes.total` and `pushes.importance`: Telegram-confirmed flash deliveries and their Gemini tier. Failed deliveries are not counted as pushes.
- `duplicates_blocked`: repeated source IDs rejected by the Jin10 in-memory cache or RSS durable seen state.
- `gemini_failures`: event classification or summarization attempts that returned no usable result. Background recovery probes are excluded.
- `telegram_delivery_failures`: flash messages still unsuccessful after Telegram retry handling finishes.
- `latency_ms.p50` and `latency_ms.p95`: end-to-end time from entering the bounded queue to Telegram-confirmed delivery. `sample_count` states the evidence size; raw daily samples remain in `latency_samples_ms` so percentiles can be recomputed exactly.
- `queue_high_water_mark`: largest observed number of waiting events. It excludes the event currently being processed.

The first RSS poll for a newly configured feed establishes a safe deduplication baseline and is excluded from these counts because those historical entries are never processed.
