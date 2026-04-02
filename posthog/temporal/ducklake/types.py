import typing
import dataclasses

from psycopg import sql
from temporalio.exceptions import ApplicationError

from posthog.ducklake.common import get_duckgres_server_for_team, is_dev_mode
from posthog.ducklake.storage import connect_to_duckgres, connect_to_local_duckgres


class QueryResult(typing.Protocol):
    def fetchone(self) -> tuple | None: ...

    def fetchall(self) -> list[tuple]: ...


class QueryConnection(typing.Protocol):
    def execute(self, statement: str | sql.Composed, params: list | None = None) -> QueryResult: ...


def create_schema_if_missing_query(schema_name: str) -> sql.Composed:
    return sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema_name))


def create_replace_table_from_delta_query(schema_name: str, table_name: str) -> sql.Composed:
    return sql.SQL("CREATE OR REPLACE TABLE {}.{} AS SELECT * FROM delta_scan(%s)").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
    )


def connect_to_duckgres_for_team(team_id: int):
    if is_dev_mode():
        return connect_to_local_duckgres(team_id)

    server = get_duckgres_server_for_team(team_id)
    if server is None:
        raise ApplicationError(f"No DuckgresServer configured for team {team_id}", non_retryable=True)
    return connect_to_duckgres(server)


@dataclasses.dataclass
class DuckLakeCopyModelInput:
    """Metadata for a single model that needs to be copied into DuckLake."""

    model_label: str
    saved_query_id: str
    table_uri: str


@dataclasses.dataclass
class DataModelingDuckLakeCopyInputs:
    """Workflow inputs passed to DuckLakeCopyDataModelingWorkflow."""

    team_id: int
    job_id: str
    models: list[DuckLakeCopyModelInput]

    @property
    def properties_to_log(self) -> dict[str, typing.Any]:
        return {
            "team_id": self.team_id,
            "job_id": self.job_id,
            "model_labels": [model.model_label for model in self.models],
        }
