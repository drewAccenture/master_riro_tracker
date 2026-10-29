"""Screen data for the tracker page (US-11): plain, JSON-ready dicts with all display text.

The numbers come from core (status, overview); this module only words and formats them, so the page only draws.
Waiting and hidden joiners are left out of every total (US-03, US-10).
"""

from datetime import date

from riro.core.deadlines import day_offset
from riro.core.models import JoinerStatus, JoinerView
from riro.core.overview import (
    OverviewJoiner,
    bucket_of,
    is_open,
    ladder,
    meter,
    overview,
)
from riro.services.screen_text import (  # re-exported: tests and callers use them from here
    _CELL_CSS,
    _TILES,
    MONTHS,
    attention_badge,
    banner,
    bucket_columns,
    css_name,
    day_label,
    days_text,
    ladder_key,
    long_date,
    owner,
    plural,
    problem_text,
    short_date,
    since_text,
    skipped_text,
    task_title,
    who_line,
)

__all__ = [
    "MONTHS",
    "Screens",
    "attention_badge",
    "banner",
    "bucket_columns",
    "day_label",
    "days_text",
    "long_date",
    "owner",
    "problem_text",
    "short_date",
    "since_text",
    "skipped_text",
    "task_title",
]


class Screens:
    def __init__(self, joiners):
        self._joiners = joiners  # services.joiners.JoinerService

    def overview(self, as_of: date) -> dict:
        views = self._joiners.views(as_of)
        dated = [v for v in views if v.status is not None]
        data = overview(
            [
                OverviewJoiner(
                    v.joiner.id,
                    v.joiner.name,
                    v.joiner.roll_on,
                    v.status,
                    v.checklist.tasks,
                )
                for v in dated
            ],
            as_of,
        )
        rows = [
            {
                "id": row.id,
                "name": row.name,
                "roll_on_text": long_date(row.roll_on),
                "since_text": since_text(row.since),
                "percent": row.percent,
                "cells": [
                    {
                        "bucket": key,
                        "count": row.buckets[key],
                        "css": _CELL_CSS[key] if row.buckets[key] else "hz",
                    }
                    for key in _CELL_CSS
                ],
            }
            for row in data.rows
        ]
        attention = []
        for item in data.attention:
            badge, badge_css = attention_badge(item.days)
            attention.append(
                {
                    "joiner_id": item.joiner_id,
                    "joiner_name": item.joiner_name,
                    "task_index": item.task_index,
                    "task_number": item.task.number,
                    "title": task_title(item.task.description),
                    "who": who_line(item.task, item.joiner_name),
                    "badge": badge,
                    "badge_css": badge_css,
                }
            )
        return {
            "as_of_text": long_date(as_of),
            "kpis": {
                "joiners": data.joiners,
                "delayed": data.delayed,
                "due_soon": data.due_soon,
                "average": f"{data.average}%",
            },
            "columns": bucket_columns(as_of),
            "rows": rows,
            "attention": attention,
            "sidebar": {
                "delayed_total": data.delayed,
                "joiners": [
                    {
                        "id": v.joiner.id,
                        "name": v.joiner.name,
                        "line": f"Roll-on {long_date(v.joiner.roll_on)} · {v.status.percent}% done",
                        "delayed_count": v.status.delayed_count,
                    }
                    for v in dated
                ],
                "waiting": [
                    {"id": v.joiner.id, "name": v.joiner.name}
                    for v in views
                    if v.joiner.roll_on is None
                ],
            },
        }

    def joiner_extra(self, view: JoinerView, as_of: date) -> dict:
        tasks = view.checklist.tasks if view.checklist else ()
        status, roll_on = view.status, view.joiner.roll_on
        statuses = status.tasks if status else (None,) * len(tasks)
        rows = []
        for index, (task, task_status) in enumerate(zip(tasks, statuses, strict=True)):
            track = task_status.track if task_status else ""
            days = task_status.days if task_status else None
            text, css = days_text(track, days)
            due = task_status.due if task_status else None
            rows.append(
                {
                    "index": index,
                    "title": task_title(task.description),
                    "full": task.description,
                    "guidelines": task.guidelines,
                    "who": owner(task, view.joiner.name),
                    "due_text": f"Due {long_date(due)}" if due else "",
                    "days_text": text,
                    "days_css": css,
                    "bucket": bucket_of(days) if is_open(track) else None,
                    "ladder_key": ladder_key(day_offset(task.deadline)),
                    "completion_text": long_date(task.completion_date),
                    "remarks": task.remarks,
                }
            )
        extra = {
            "roll_on_text": long_date(roll_on),
            "as_of_text": long_date(as_of),
            "hidden": view.joiner.hidden,  # US-10: the last sync hid this joiner; the page goes back to the overview
            "skipped_text": skipped_text(
                view.checklist.skipped_rows if view.checklist else ()
            ),
            "problem_text": problem_text(view.problem, view.read_at),
            "roles": sorted({task.role for task in tasks if task.role}),
            "banner": None,
            "meter": [],
            "tiles": [],
            "ladder": None,
            "task_rows": rows,
        }
        if status is None:
            return extra
        extra["banner"] = banner(status)
        extra["meter"] = [
            {"track": m.track, "count": m.count, "percent": m.percent}
            for m in meter(status)
        ]
        extra["tiles"] = [
            {
                "track": track,
                "label": "Not applicable" if track == "N/A" else track,
                "count": status.counts[track],
            }
            for track in _TILES
        ]
        extra["ladder"] = self._ladder(tasks, status, roll_on, as_of)
        return extra

    @staticmethod
    def _ladder(tasks, status: JoinerStatus, roll_on: date, as_of: date) -> dict:
        data = ladder(tasks, status.tasks, roll_on, as_of)
        columns = []
        for column in data.columns:
            count = len(column.squares)
            if column.due is None:
                title = plural(
                    count,
                    "task with an unclear deadline",
                    "tasks with an unclear deadline",
                )
            else:
                title = f"{plural(count, 'task', 'tasks')} due {long_date(column.due)}"
            columns.append(
                {
                    "key": ladder_key(column.offset),
                    "label": day_label(column.offset),
                    "date": short_date(column.due) if column.due else "",
                    "title": title,
                    "squares": [
                        {"index": index, "track": track, "css": css_name(track)}
                        for index, track in column.squares
                    ],
                }
            )
        return {
            "columns": columns,
            "marker_before": data.marker_before,
            "marker_label": short_date(as_of),
        }
