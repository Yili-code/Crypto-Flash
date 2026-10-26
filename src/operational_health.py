"""Read-only operational health summary across Crypto Flash pipelines."""

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import classification_backlog
import gemini_policy
from common import STATE_DIR
from gemini import current_config_id

TAIPEI = timezone(timedelta(hours=8))
SCOPES = ("live", "youtube", "digest")


@dataclass(frozen=True)
class HealthIssue:
    severity: str
    component: str
    message: str


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot read {path.name}: {type(exc).__name__}") from exc


def current_scope_block(scope: str) -> str:
    state = gemini_policy.read_state(scope)
    if state and state.get("config") == current_config_id() and state.get("blocked"):
        return str(state.get("last_error") or "configuration_blocked")
    return ""


def collect_health() -> tuple[list[HealthIssue], dict]:
    issues: list[HealthIssue] = []
    details: dict = {"gemini": {}, "youtube_pending": 0, "classification_pending": 0}
    for scope in SCOPES:
        try:
            state = gemini_policy.read_state(scope)
        except gemini_policy.PolicyStateError as exc:
            issues.append(HealthIssue("critical", scope, str(exc)))
            continue
        blocked = bool(state and state.get("config") == current_config_id() and state.get("blocked"))
        details["gemini"][scope] = {
            "blocked": blocked,
            "last_error": state.get("last_error", "") if state else "",
            "used": state.get("used", 0) if state else 0,
        }
        if blocked:
            issues.append(HealthIssue("critical", scope, f"Gemini permanently blocked: {state.get('last_error') or 'unknown'}"))

    try:
        progress = _read_json(STATE_DIR / "yt_progress.json", {})
        if not isinstance(progress, dict):
            raise RuntimeError("yt_progress.json must be an object")
        pending = sum(
            isinstance(record, dict) and not record.get("research_delivered", False)
            for record in progress.values()
        )
        details["youtube_pending"] = pending
        if pending:
            issues.append(HealthIssue("warning", "youtube", f"{pending} videos are pending completion"))
    except RuntimeError as exc:
        issues.append(HealthIssue("critical", "youtube", str(exc)))

    try:
        backlog = classification_backlog.load()
        details["classification_pending"] = len(backlog)
        if backlog:
            issues.append(HealthIssue("warning", "live", f"{len(backlog)} flashes await classification"))
    except RuntimeError as exc:
        issues.append(HealthIssue("critical", "live", str(exc)))

    try:
        metrics = _read_json(STATE_DIR / "monitoring_daily.json", {})
        days = metrics.get("days", {}) if isinstance(metrics, dict) else {}
        latest = max(days) if isinstance(days, dict) and days else ""
        details["latest_metrics_day"] = latest
        yesterday = (datetime.now(TAIPEI).date() - timedelta(days=1)).isoformat()
        if latest and latest < yesterday:
            issues.append(HealthIssue("critical", "live", f"monitoring heartbeat is stale: {latest}"))
    except RuntimeError as exc:
        issues.append(HealthIssue("critical", "live", str(exc)))

    if not os.getenv("TELEGRAM_OWNER_USER_IDS", "").strip():
        issues.append(HealthIssue("warning", "telegram", "owner allowlist is not configured"))
    return issues, details


def render_health_html() -> str:
    issues, details = collect_health()
    if not issues:
        return "<b>服務檢查</b>\n目前未發現異常。"
    critical = any(issue.severity == "critical" for issue in issues)
    rows = ["<b>服務需要處理</b>" if critical else "<b>服務需要留意</b>"]
    labels = {"live": "新聞", "youtube": "YouTube", "digest": "日報", "telegram": "管理權限"}
    ordered = sorted(issues, key=lambda issue: issue.severity != "critical")
    for issue in ordered[:8]:
        if issue.message.startswith("Gemini permanently blocked"):
            message = "AI 服務設定有誤，請檢查設定。"
        elif "videos are pending completion" in issue.message:
            message = f"{details['youtube_pending']} 部影片待完成。"
        elif "flashes await classification" in issue.message:
            message = f"{details['classification_pending']} 則消息待整理。"
        elif "owner allowlist" in issue.message:
            message = "尚未設定管理者。"
        elif "heartbeat is stale" in issue.message:
            message = "較久未更新，請檢查監控。"
        else:
            message = "狀態資料無法讀取，請檢查服務。"
        rows.append(f"• {escape(labels.get(issue.component, '服務'))}：{message}")
    if len(issues) > 8:
        rows.append(f"另有 {len(issues) - 8} 項問題待檢查。")
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=("all", "live", "youtube", "digest", "telegram"), default="all")
    args = parser.parse_args()
    issues, _ = collect_health()
    selected = [issue for issue in issues if args.check == "all" or issue.component == args.check]
    for issue in selected:
        print(f"{issue.severity.upper()} {issue.component}: {issue.message}")
    return 1 if any(issue.severity == "critical" for issue in selected) else 0


if __name__ == "__main__":
    raise SystemExit(main())
