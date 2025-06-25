import os
from datetime import datetime
from statistics import mean
from typing import List, Dict


def compute_call_metrics(
    transcripts: List[dict],
    start_time: str,
    stop_time: str,
    guardrail_rejects: int,
    calendar_errors: int,
    latencies: List[float],
) -> Dict[str, float]:
    """Return computed metrics for a call."""
    try:
        duration = (
            datetime.fromisoformat(stop_time) - datetime.fromisoformat(start_time)
        ).total_seconds()
    except Exception:
        duration = 0.0
    tps = len(transcripts) / duration if duration else 0.0
    avg_latency = mean(latencies) if latencies else 0.0
    return {
        "tps": tps,
        "avg_latency": avg_latency,
        "guardrail_rejects": guardrail_rejects,
        "calendar_errors": calendar_errors,
        "duration": duration,
    }


def write_report(call_id: str, metrics: Dict[str, float], reports_dir: str = "reports") -> str:
    """Write metrics to a markdown report file and return its path."""
    os.makedirs(reports_dir, exist_ok=True)
    path = os.path.join(reports_dir, f"{call_id}_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Call Report {call_id}\n\n")
        f.write(f"TPS: {metrics['tps']:.2f}\n")
        f.write(f"Average Latency: {metrics['avg_latency']:.3f} seconds\n")
        f.write(f"Guardrail Rejects: {metrics['guardrail_rejects']}\n")
        f.write(f"Calendar Errors: {metrics['calendar_errors']}\n")
    return path
