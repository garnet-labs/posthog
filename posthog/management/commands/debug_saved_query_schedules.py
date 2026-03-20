"""Debug CLI for connecting DataWarehouseSavedQuery models to their Temporal schedules and runs.

Usage (from the toolbox pod):
    python manage.py debug_saved_query_schedules --team-id 12345
    python manage.py debug_saved_query_schedules --team-id 12345 --saved-query-id <uuid>
    python manage.py debug_saved_query_schedules --team-id 12345 --show-runs --run-limit 5
    python manage.py debug_saved_query_schedules --team-id 12345 --json
"""

from __future__ import annotations

import json as json_module
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

import structlog
from asgiref.sync import sync_to_async
from temporalio.client import Client
from temporalio.service import RPCError

from posthog.temporal.common.client import async_connect
from posthog.temporal.common.search_attributes import POSTHOG_TEAM_ID_KEY

logger = structlog.get_logger(__name__)


def _format_timedelta(td: timedelta | None) -> str:
    if td is None:
        return "-"
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h{minutes}m"
    if minutes > 0:
        return f"{minutes}m{seconds}s"
    return f"{seconds}s"


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_ago(dt: datetime | None) -> str:
    if dt is None:
        return ""
    delta = timezone.now() - dt
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "(in the future)"
    if total_seconds < 60:
        return f"({total_seconds}s ago)"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"({minutes}m ago)"
    hours = minutes // 60
    if hours < 24:
        return f"({hours}h ago)"
    days = hours // 24
    return f"({days}d ago)"


def _temporal_ui_schedule_url(namespace: str, schedule_id: str) -> str:
    base = settings.TEMPORAL_UI_HOST
    return f"{base}/namespaces/{namespace}/schedules/{schedule_id}"


def _temporal_ui_workflow_url(namespace: str, workflow_id: str, run_id: str) -> str:
    base = settings.TEMPORAL_UI_HOST
    return f"{base}/namespaces/{namespace}/workflows/{workflow_id}/{run_id}"


class Command(BaseCommand):
    help = "Debug DataWarehouseSavedQuery Temporal schedules and runs for a team"

    def add_arguments(self, parser):
        parser.add_argument(
            "--team-id",
            type=int,
            required=True,
            help="Team ID to inspect",
        )
        parser.add_argument(
            "--saved-query-id",
            type=str,
            default=None,
            help="Filter to a specific saved query UUID",
        )
        parser.add_argument(
            "--show-runs",
            action="store_true",
            default=False,
            help="Also show recent Temporal workflow runs for each schedule",
        )
        parser.add_argument(
            "--run-limit",
            type=int,
            default=3,
            help="Max recent runs to show per saved query (default: 3)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            dest="json_output",
            help="Output as JSON instead of formatted table",
        )
        parser.add_argument(
            "--include-deleted",
            action="store_true",
            default=False,
            help="Include soft-deleted saved queries",
        )

    def handle(self, **options):
        logging.basicConfig(level=logging.WARNING)
        asyncio.run(self._run(options))

    async def _run(self, options: dict[str, Any]):
        team_id: int = options["team_id"]
        saved_query_id: str | None = options["saved_query_id"]
        show_runs: bool = options["show_runs"]
        run_limit: int = options["run_limit"]
        json_output: bool = options["json_output"]
        include_deleted: bool = options["include_deleted"]

        if saved_query_id:
            try:
                UUID(saved_query_id)
            except ValueError:
                raise CommandError(f"Invalid UUID: {saved_query_id}")

        # Step 1: Fetch saved queries from Postgres
        saved_queries = await sync_to_async(self._get_saved_queries)(team_id, saved_query_id, include_deleted)

        if not saved_queries:
            self.stderr.write(f"No saved queries found for team {team_id}")
            return

        # Step 2: Fetch recent data modeling jobs from Postgres
        saved_query_ids = [sq["id"] for sq in saved_queries]
        jobs_by_query = await sync_to_async(self._get_recent_jobs)(saved_query_ids, run_limit)

        # Step 3: Connect to Temporal and enrich with schedule info
        temporal = await async_connect()
        namespace = settings.TEMPORAL_NAMESPACE

        schedule_infos = await self._get_schedule_infos(temporal, saved_queries)

        # Step 4: Optionally fetch recent workflow runs from Temporal
        run_infos: dict[str, list[dict[str, Any]]] = {}
        if show_runs:
            run_infos = await self._get_recent_runs(temporal, team_id, saved_query_ids, run_limit)

        # Step 5: Output
        results = self._build_results(saved_queries, schedule_infos, jobs_by_query, run_infos, namespace)

        if json_output:
            self.stdout.write(json_module.dumps(results, indent=2, default=str))
        else:
            self._print_formatted(results, team_id, show_runs, namespace)

    def _get_saved_queries(
        self, team_id: int, saved_query_id: str | None, include_deleted: bool
    ) -> list[dict[str, Any]]:
        from products.data_warehouse.backend.models.datawarehouse_saved_query import DataWarehouseSavedQuery

        qs = DataWarehouseSavedQuery.objects.filter(team_id=team_id).select_related("table", "managed_viewset")

        if not include_deleted:
            qs = qs.exclude(deleted=True)

        if saved_query_id:
            qs = qs.filter(id=saved_query_id)

        qs = qs.order_by("-updated_at")

        results = []
        for sq in qs:
            results.append(
                {
                    "id": str(sq.id),
                    "name": sq.name,
                    "is_materialized": sq.is_materialized,
                    "status": sq.status or "-",
                    "sync_frequency_interval": sq.sync_frequency_interval,
                    "last_run_at": sq.last_run_at,
                    "latest_error": sq.latest_error,
                    "deleted": sq.deleted,
                    "origin": sq.origin,
                    "table_id": str(sq.table_id) if sq.table_id else None,
                    "managed_viewset_kind": sq.managed_viewset.kind if sq.managed_viewset else None,
                    "created_at": sq.created_at,
                    "updated_at": sq.updated_at,
                }
            )
        return results

    def _get_recent_jobs(self, saved_query_ids: list[str], limit: int) -> dict[str, list[dict[str, Any]]]:
        from products.data_warehouse.backend.models.data_modeling_job import DataModelingJob

        jobs_by_query: dict[str, list[dict[str, Any]]] = {sqid: [] for sqid in saved_query_ids}

        # Get recent jobs for each saved query, ordered by last_run_at desc
        jobs = (
            DataModelingJob.objects.filter(saved_query_id__in=saved_query_ids)
            .order_by("-last_run_at")
            .values(
                "id",
                "saved_query_id",
                "status",
                "rows_materialized",
                "rows_expected",
                "error",
                "workflow_id",
                "workflow_run_id",
                "last_run_at",
                "storage_delta_mib",
                "created_at",
            )
        )

        counts: dict[str, int] = {}
        for job in jobs:
            sqid = str(job["saved_query_id"])
            if sqid not in counts:
                counts[sqid] = 0
            if counts[sqid] >= limit:
                continue
            counts[sqid] += 1
            jobs_by_query[sqid].append(
                {
                    "id": str(job["id"]),
                    "status": job["status"],
                    "rows_materialized": job["rows_materialized"],
                    "rows_expected": job["rows_expected"],
                    "error": job["error"],
                    "workflow_id": job["workflow_id"],
                    "workflow_run_id": job["workflow_run_id"],
                    "last_run_at": job["last_run_at"],
                    "storage_delta_mib": job["storage_delta_mib"],
                    "created_at": job["created_at"],
                }
            )

        return jobs_by_query

    async def _get_schedule_infos(
        self, temporal: Client, saved_queries: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Describe Temporal schedules for each saved query (schedule_id = saved_query.id)."""
        schedule_infos: dict[str, dict[str, Any]] = {}
        semaphore = asyncio.Semaphore(10)

        async def describe_one(sq_id: str) -> tuple[str, dict[str, Any]]:
            async with semaphore:
                try:
                    handle = temporal.get_schedule_handle(sq_id)
                    desc = await handle.describe()

                    intervals = desc.schedule.spec.intervals
                    interval_str = _format_timedelta(intervals[0].every) if intervals else "-"

                    paused = desc.schedule.state.paused
                    note = desc.schedule.state.note or ""

                    # Recent actions from schedule info
                    recent_actions = []
                    for action in desc.info.recent_actions:
                        ra: dict[str, Any] = {
                            "schedule_time": action.schedule_time,
                            "actual_time": action.actual_time,
                        }
                        if action.start_result:
                            ra["workflow_id"] = action.start_result.workflow_id
                            ra["run_id"] = action.start_result.first_execution_run_id
                        recent_actions.append(ra)

                    next_action_times = list(desc.info.next_action_times[:3])

                    return sq_id, {
                        "exists": True,
                        "paused": paused,
                        "note": note,
                        "interval": interval_str,
                        "recent_actions": recent_actions,
                        "next_action_times": next_action_times,
                        "num_actions_taken": desc.info.num_actions,
                    }
                except RPCError as e:
                    if "not found" in str(e).lower():
                        return sq_id, {"exists": False}
                    return sq_id, {"exists": False, "error": str(e)}
                except Exception as e:
                    return sq_id, {"exists": False, "error": str(e)}

        tasks = [asyncio.create_task(describe_one(sq["id"])) for sq in saved_queries]
        for task in asyncio.as_completed(tasks):
            sq_id, info = await task
            schedule_infos[sq_id] = info

        return schedule_infos

    async def _get_recent_runs(
        self, temporal: Client, team_id: int, saved_query_ids: list[str], limit: int
    ) -> dict[str, list[dict[str, Any]]]:
        """List recent workflow runs from Temporal for the given team's data-modeling-run workflows."""
        run_infos: dict[str, list[dict[str, Any]]] = {sqid: [] for sqid in saved_query_ids}

        try:
            query = f'TaskQueue = "{settings.DATA_MODELING_TASK_QUEUE}" AND {POSTHOG_TEAM_ID_KEY.name} = {team_id}'
            count = 0
            async for wf in temporal.list_workflows(query=query):
                # workflow IDs for schedule-triggered runs have the format:
                # <schedule_id>-<timestamp> but we need to match to saved_query_ids
                # The schedule itself uses workflow_id from the schedule action
                wf_info: dict[str, Any] = {
                    "workflow_id": wf.id,
                    "run_id": wf.run_id,
                    "status": wf.status.name if wf.status else "UNKNOWN",
                    "start_time": wf.start_time,
                    "close_time": wf.close_time,
                    "execution_time": wf.execution_time,
                }

                # Try to associate with a saved query by checking if any saved_query_id
                # appears in the workflow_id (schedules create workflows like "<schedule_id>-<timestamp>")
                for sqid in saved_query_ids:
                    if sqid in wf.id:
                        if len(run_infos[sqid]) < limit:
                            run_infos[sqid].append(wf_info)
                        break

                count += 1
                if count >= limit * len(saved_query_ids) * 2:
                    # Stop after enough results to reasonably cover all queries
                    break
        except Exception as e:
            self.stderr.write(f"Warning: Could not list Temporal workflows: {e}")

        return run_infos

    def _build_results(
        self,
        saved_queries: list[dict[str, Any]],
        schedule_infos: dict[str, dict[str, Any]],
        jobs_by_query: dict[str, list[dict[str, Any]]],
        run_infos: dict[str, list[dict[str, Any]]],
        namespace: str,
    ) -> list[dict[str, Any]]:
        results = []
        for sq in saved_queries:
            sq_id = sq["id"]
            sched = schedule_infos.get(sq_id, {"exists": False})
            jobs = jobs_by_query.get(sq_id, [])
            runs = run_infos.get(sq_id, [])

            entry: dict[str, Any] = {
                **sq,
                "schedule": sched,
                "schedule_url": _temporal_ui_schedule_url(namespace, sq_id) if sched.get("exists") else None,
                "recent_jobs": jobs,
                "temporal_runs": runs,
            }
            results.append(entry)
        return results

    def _print_formatted(self, results: list[dict[str, Any]], team_id: int, show_runs: bool, namespace: str):
        total = len(results)
        materialized = sum(1 for r in results if r["is_materialized"])
        with_schedule = sum(1 for r in results if r["schedule"].get("exists"))

        self.stdout.write("")
        self.stdout.write(f"{'=' * 80}")
        self.stdout.write(f"  Saved Query Debug Report for Team {team_id}")
        self.stdout.write(
            f"  {total} saved queries | {materialized} materialized | {with_schedule} with Temporal schedule"
        )
        self.stdout.write(f"{'=' * 80}")

        # Summary of issues
        issues: list[str] = []
        for r in results:
            if r["is_materialized"] and not r["schedule"].get("exists"):
                issues.append(f"  MISSING SCHEDULE: {r['name']} ({r['id']})")
            if not r["is_materialized"] and r["schedule"].get("exists"):
                issues.append(f"  ORPHAN SCHEDULE: {r['name']} ({r['id']}) - not materialized but schedule exists")
            if r["status"] == "Failed":
                issues.append(f"  FAILED: {r['name']} ({r['id']})")
            if r["schedule"].get("exists") and r["schedule"].get("paused"):
                issues.append(f"  PAUSED: {r['name']} ({r['id']})")

        if issues:
            self.stdout.write("")
            self.stdout.write("  ISSUES DETECTED:")
            for issue in issues:
                self.stdout.write(f"    ! {issue}")

        for r in results:
            self.stdout.write("")
            self.stdout.write(f"{'─' * 80}")

            # Header
            flags = []
            if r["is_materialized"]:
                flags.append("MATERIALIZED")
            if r["deleted"]:
                flags.append("DELETED")
            if r["managed_viewset_kind"]:
                flags.append(f"MANAGED:{r['managed_viewset_kind']}")
            flag_str = f" [{', '.join(flags)}]" if flags else ""

            self.stdout.write(f"  {r['name']}{flag_str}")
            self.stdout.write(f"  ID: {r['id']}")
            self.stdout.write(
                f"  Origin: {r['origin']}  |  Status: {r['status']}  |  Sync interval: {_format_timedelta(r['sync_frequency_interval'])}"
            )
            self.stdout.write(f"  Last run: {_format_dt(r['last_run_at'])} {_format_ago(r['last_run_at'])}")
            self.stdout.write(f"  Created: {_format_dt(r['created_at'])}  |  Updated: {_format_dt(r['updated_at'])}")

            if r["latest_error"]:
                error_preview = r["latest_error"][:200]
                if len(r["latest_error"]) > 200:
                    error_preview += "..."
                self.stdout.write(f"  Latest error: {error_preview}")

            if r["table_id"]:
                self.stdout.write(f"  Materialized table: {r['table_id']}")

            # Schedule info
            sched = r["schedule"]
            self.stdout.write("")
            if sched.get("exists"):
                paused_str = " (PAUSED)" if sched.get("paused") else ""
                self.stdout.write(f"  Temporal Schedule:{paused_str}")
                self.stdout.write(
                    f"    Interval: {sched.get('interval', '-')}  |  Actions taken: {sched.get('num_actions_taken', '-')}"
                )

                if sched.get("note"):
                    self.stdout.write(f"    Note: {sched['note']}")

                if sched.get("recent_actions"):
                    self.stdout.write(f"    Recent actions:")
                    for action in sched["recent_actions"][-3:]:
                        wf_id = action.get("workflow_id", "-")
                        actual = _format_dt(action.get("actual_time"))
                        run_id = action.get("run_id", "")
                        url = ""
                        if wf_id != "-" and run_id:
                            url = f"  {_temporal_ui_workflow_url(namespace, wf_id, run_id)}"
                        self.stdout.write(f"      {actual} -> {wf_id}{url}")

                if sched.get("next_action_times"):
                    next_times = [_format_dt(t) for t in sched["next_action_times"][:2]]
                    self.stdout.write(f"    Next: {', '.join(next_times)}")

                self.stdout.write(f"    Schedule URL: {r['schedule_url']}")
            elif sched.get("error"):
                self.stdout.write(f"  Temporal Schedule: ERROR - {sched['error']}")
            else:
                if r["is_materialized"]:
                    self.stdout.write("  Temporal Schedule: MISSING (materialized but no schedule found!)")
                else:
                    self.stdout.write("  Temporal Schedule: None (not materialized)")

            # Recent jobs from Postgres
            if r["recent_jobs"]:
                self.stdout.write("")
                self.stdout.write("  Recent jobs (from Postgres):")
                for job in r["recent_jobs"]:
                    rows = f"{job['rows_materialized']}"
                    if job["rows_expected"]:
                        rows += f"/{job['rows_expected']}"
                    storage = f", {job['storage_delta_mib']:.1f} MiB" if job.get("storage_delta_mib") else ""
                    error_str = ""
                    if job["error"]:
                        err_preview = job["error"][:100]
                        if len(job["error"]) > 100:
                            err_preview += "..."
                        error_str = f"\n              Error: {err_preview}"

                    wf_str = ""
                    if job["workflow_id"] and job["workflow_run_id"]:
                        wf_str = f"\n              Workflow: {_temporal_ui_workflow_url(namespace, job['workflow_id'], job['workflow_run_id'])}"

                    self.stdout.write(
                        f"    [{job['status']:>9}] {_format_dt(job['last_run_at'])} {_format_ago(job['last_run_at'])} | rows: {rows}{storage}{error_str}{wf_str}"
                    )

            # Temporal workflow runs
            if show_runs and r["temporal_runs"]:
                self.stdout.write("")
                self.stdout.write("  Recent Temporal runs:")
                for run in r["temporal_runs"]:
                    duration_str = ""
                    if run.get("start_time") and run.get("close_time"):
                        duration = run["close_time"] - run["start_time"]
                        duration_str = f" (took {_format_timedelta(duration)})"
                    self.stdout.write(f"    [{run['status']:>11}] {_format_dt(run.get('start_time'))}{duration_str}")
                    self.stdout.write(
                        f"              {_temporal_ui_workflow_url(namespace, run['workflow_id'], run['run_id'])}"
                    )

        self.stdout.write("")
        self.stdout.write(f"{'=' * 80}")
