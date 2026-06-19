from typing import Any


METRIC_DEFINITIONS = [
    (
        "ivp_jobs_current",
        "gauge",
        "Number of IVP jobs by status.",
        "jobs",
        ("status",),
    ),
    (
        "ivp_devices_current",
        "gauge",
        "Number of registered IVP devices by status and backend.",
        "devices",
        ("status", "backend"),
    ),
    (
        "ivp_heartbeats_total",
        "counter",
        "Total IVP worker heartbeat records by backend and health.",
        "heartbeats",
        ("backend", "healthy"),
    ),
    (
        "ivp_events_total",
        "counter",
        "Total IVP platform events by event type.",
        "events",
        ("event_type",),
    ),
    (
        "ivp_validation_results_total",
        "counter",
        "Total completed IVP validation results by outcome.",
        "validation_results",
        ("result",),
    ),
]


def render_prometheus_metrics(snapshot: dict[str, list[dict[str, Any]]]) -> str:
    lines: list[str] = []

    for name, metric_type, help_text, section, label_names in METRIC_DEFINITIONS:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {metric_type}")

        for row in snapshot.get(section, []):
            labels = {
                label: _format_label_value(row[label])
                for label in label_names
            }
            lines.append(f"{name}{_format_labels(labels)} {row['value']}")

    lines.append("")
    return "\n".join(lines)


def _format_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""

    label_text = ",".join(
        f'{key}="{value}"'
        for key, value in labels.items()
    )
    return f"{{{label_text}}}"


def _format_label_value(value: Any) -> str:
    text = str(value).lower() if isinstance(value, bool) else str(value)
    return (
        text
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )
