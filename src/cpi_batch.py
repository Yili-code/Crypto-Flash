"""Conservative CPI release recognition and source-preserving rendering."""

import hashlib
import re
from decimal import Decimal
from html import escape


NUMBER = r"[-+]?\d+(?:\.\d+)?"
TEXT = re.compile(
    rf"(?P<country>[\u4e00-\u9fff]{{2,8}}?)(?P<month>\d{{1,2}}月)"
    rf"(?P<core>核心)?CPI(?P<rate>年率|月率)\s*(?P<actual>{NUMBER})%，?"
    rf"\s*预期(?P<expected>{NUMBER})%，?\s*前值(?P<previous>{NUMBER})%。?"
)


def parse_release(item):
    """Only accept complete percentage releases with an explicit publication date."""
    source = item.get("source") or "Jin10"
    if source != "Jin10":
        return None
    identity = str(item.get("id", ""))
    if not re.fullmatch(r"\d{14,}", identity):
        return None
    data = item.get("data")
    if not isinstance(data, dict):
        return None
    content = str(data.get("content") or "").strip()
    if not content and item.get("type") == 1 and data.get("unit") == "%":
        name = str(data.get("name") or "") + str(data.get("measure") or "")
        indicator = re.fullmatch(r"(核心)?CPI(年率|月率)", name)
        if indicator:
            content = (f'{data.get("country", "")}{data.get("time_period", "")}{name} '
                       f'{data.get("actual") }%，预期{data.get("consensus")}%，前值{data.get("previous")}%。')
    match = TEXT.fullmatch(content)
    if not match:
        return None
    row = match.groupdict()
    if not 1 <= int(row["month"][:-1]) <= 12:
        return None
    row["core"] = bool(row["core"])
    row["key"] = (source, identity[:12], row["country"], row["month"])
    return row


def merge_release(items):
    rows = [parse_release(item) for item in items]
    if not rows or any(row is None or row["key"] != rows[0]["key"] for row in rows):
        raise ValueError("CPI release keys must match")
    unique = {}
    for row in rows:
        values = (row["core"], row["rate"], *(Decimal(row[k]) for k in ("actual", "expected", "previous")))
        unique.setdefault(values, row)
    ordered = sorted(unique.values(), key=lambda r: (r["core"], r["rate"] == "月率"))
    first = rows[0]
    labels = [(r["core"], r["rate"]) for r in ordered]
    conflict = len(set(labels)) != len(labels)
    country = first["country"].translate(str.maketrans("国欧区兰韩", "國歐區蘭韓"))
    title = f'{country}{first["month"]} CPI 公布'
    lines = [f"<b>{escape(title)}</b>"]
    if conflict:
        lines.append("來源數值衝突：同一指標有不同版本，以下並列，請勿視為已核實。")
    for row in ordered:
        label = ("核心 CPI" if row["core"] else "整體 CPI") + (" 年率（YoY）" if row["rate"] == "年率" else " 月率（MoM）")
        lines.append(f'{label}：{row["actual"]}%（預期 {row["expected"]}%；前值 {row["previous"]}%）')
    lines.append("年率比較去年同月；月率比較上月。核心 CPI 排除食品與能源等項目。")
    message = "\n".join(lines)
    digest = hashlib.sha256("|".join(sorted(str(i["id"]) for i in items)).encode()).hexdigest()[:24]
    merged = {
        "id": "cpi-" + digest, "source": first["key"][0],
        "data": {"title": title, "content": re.sub(r"</?b>", "", message)},
        "_cpi_message": message,
    }
    # Preserve the earliest receive timestamp without depending on metrics internals.
    from monitoring_metrics import RECEIVED_AT_KEY
    times = [i[RECEIVED_AT_KEY] for i in items if RECEIVED_AT_KEY in i]
    if times:
        merged[RECEIVED_AT_KEY] = min(times)
    return merged
