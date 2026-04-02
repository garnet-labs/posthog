import os
import uuid

import pytest

from databricks.sql.exc import ServerOperationError

from products.batch_exports.backend.temporal.destinations.databricks_batch_export import (
    DatabricksCatalogNotFoundError,
    DatabricksClient,
    DatabricksConnectionError,
    DatabricksSchemaNotFoundError,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.django_db,
]


async def test_get_merge_query_with_schema_evolution():
    """Test that we construct the correct SQL for merging with schema evolution."""
    client = DatabricksClient(
        server_hostname="test",
        http_path="test",
        client_id="test",
        client_secret="test",
        catalog="test",
        schema="test",
    )
    merge_key = ["team_id", "distinct_id"]
    update_key = ["person_version", "person_distinct_id_version"]
    merge_query = client._get_merge_query_with_schema_evolution(
        target_table="test_target",
        source_table="test_source",
        merge_key=merge_key,
        update_key=update_key,
    )
    assert (
        merge_query
        == """
        MERGE WITH SCHEMA EVOLUTION INTO `test_target` AS target
        USING `test_source` AS source
        ON target.`team_id` = source.`team_id` AND target.`distinct_id` = source.`distinct_id`
        WHEN MATCHED AND (target.`person_version` < source.`person_version` OR target.`person_distinct_id_version` < source.`person_distinct_id_version`) THEN
            UPDATE SET *
        WHEN NOT MATCHED THEN
            INSERT *
        """
    )


async def test_get_merge_query_without_schema_evolution():
    """Test that we construct the correct SQL for merging without schema evolution."""
    client = DatabricksClient(
        server_hostname="test",
        http_path="test",
        client_id="test",
        client_secret="test",
        catalog="test",
        schema="test",
    )
    merge_key = ["team_id", "distinct_id"]
    update_key = ["person_version", "person_distinct_id_version"]
    merge_query = client._get_merge_query_without_schema_evolution(
        target_table="test_target",
        source_table="test_source",
        merge_key=merge_key,
        update_key=update_key,
        source_table_fields=[
            ("team_id", "INTEGER"),
            ("distinct_id", "STRING"),
            ("person_version", "INTEGER"),
            ("person_distinct_id_version", "INTEGER"),
            ("properties", "VARIANT"),
        ],
        target_table_field_names=[
            "team_id",
            "distinct_id",
            "person_version",
            "person_distinct_id_version",
            "properties",
        ],
    )
    assert (
        merge_query
        == """
        MERGE INTO `test_target` AS target
        USING `test_source` AS source
        ON target.`team_id` = source.`team_id` AND target.`distinct_id` = source.`distinct_id`
        WHEN MATCHED AND (target.`person_version` < source.`person_version` OR target.`person_distinct_id_version` < source.`person_distinct_id_version`) THEN
            UPDATE SET
                target.`team_id` = source.`team_id`, target.`distinct_id` = source.`distinct_id`, target.`person_version` = source.`person_version`, target.`person_distinct_id_version` = source.`person_distinct_id_version`, target.`properties` = source.`properties`
        WHEN NOT MATCHED THEN
            INSERT (`team_id`, `distinct_id`, `person_version`, `person_distinct_id_version`, `properties`)
            VALUES (source.`team_id`, source.`distinct_id`, source.`person_version`, source.`person_distinct_id_version`, source.`properties`)
        """
    )


async def test_get_merge_query_without_schema_evolution_and_target_table_has_less_fields():
    """Test that we construct the correct SQL for merging without schema evolution and the target table has less
    fields.

    In this example, the "new_field" field should be ignored.
    """
    client = DatabricksClient(
        server_hostname="test",
        http_path="test",
        client_id="test",
        client_secret="test",
        catalog="test",
        schema="test",
    )
    merge_key = ["team_id", "distinct_id"]
    update_key = ["person_version", "person_distinct_id_version"]
    merge_query = client._get_merge_query_without_schema_evolution(
        target_table="test_target",
        source_table="test_source",
        merge_key=merge_key,
        update_key=update_key,
        source_table_fields=[
            ("team_id", "INTEGER"),
            ("distinct_id", "STRING"),
            ("person_version", "INTEGER"),
            ("person_distinct_id_version", "INTEGER"),
            ("properties", "VARIANT"),
            ("new_field", "STRING"),
        ],
        target_table_field_names=[
            "team_id",
            "distinct_id",
            "person_version",
            "person_distinct_id_version",
            "properties",
        ],
    )
    assert (
        merge_query
        == """
        MERGE INTO `test_target` AS target
        USING `test_source` AS source
        ON target.`team_id` = source.`team_id` AND target.`distinct_id` = source.`distinct_id`
        WHEN MATCHED AND (target.`person_version` < source.`person_version` OR target.`person_distinct_id_version` < source.`person_distinct_id_version`) THEN
            UPDATE SET
                target.`team_id` = source.`team_id`, target.`distinct_id` = source.`distinct_id`, target.`person_version` = source.`person_version`, target.`person_distinct_id_version` = source.`person_distinct_id_version`, target.`properties` = source.`properties`
        WHEN NOT MATCHED THEN
            INSERT (`team_id`, `distinct_id`, `person_version`, `person_distinct_id_version`, `properties`)
            VALUES (source.`team_id`, source.`distinct_id`, source.`person_version`, source.`person_distinct_id_version`, source.`properties`)
        """
    )


async def test_get_copy_into_table_from_volume_query():
    client = DatabricksClient(
        server_hostname="test",
        http_path="test",
        client_id="test",
        client_secret="test",
        catalog="test",
        schema="test",
    )
    fields = [
        ("uuid", "STRING"),
        ("event", "STRING"),
        ("properties", "VARIANT"),
        ("distinct_id", "STRING"),
        ("team_id", "BIGINT"),
        ("timestamp", "TIMESTAMP"),
        ("databricks_ingested_timestamp", "TIMESTAMP"),
    ]
    query = client._get_copy_into_table_from_volume_query(
        table_name="test_table",
        volume_path="/Volumes/my_volume/path/file.parquet",
        fields=fields,
    )
    assert (
        query
        == """
        COPY INTO `test_table`
        FROM (
            SELECT `uuid`, `event`, PARSE_JSON(`properties`) as `properties`, `distinct_id`, CAST(`team_id` as BIGINT) as `team_id`, `timestamp`, `databricks_ingested_timestamp` FROM '/Volumes/my_volume/path/file.parquet'
        )
        FILEFORMAT = PARQUET
        COPY_OPTIONS ('force' = 'true', 'mergeSchema' = 'true')
        """
    )


async def test_connect_when_invalid_host():
    """Test that we raise an error when the host is invalid."""
    client = DatabricksClient(
        server_hostname="invalid",
        http_path="test",
        client_id="test",
        client_secret="test",
        catalog="test",
        schema="test",
    )
    with pytest.raises(
        DatabricksConnectionError,
        match="Failed to connect to Databricks. Please check that your connection details are valid.",
    ):
        async with client.connect():
            pass


# --- SQL injection integration tests ---
# These tests run against a real Databricks instance to verify that SQL injection
# via backtick/quote characters in identifiers is not possible.

REQUIRED_ENV_VARS = (
    "DATABRICKS_BE_SERVER_HOSTNAME",
    "DATABRICKS_BE_HTTP_PATH",
    "DATABRICKS_BE_CLIENT_ID",
    "DATABRICKS_BE_CLIENT_SECRET",
)

SKIP_IF_MISSING_DATABRICKS_CREDENTIALS = pytest.mark.skipif(
    not all(env_var in os.environ for env_var in REQUIRED_ENV_VARS),
    reason=f"Databricks required env vars are not set: {', '.join(REQUIRED_ENV_VARS)}",
)

TEST_CATALOG = os.getenv("DATABRICKS_CATALOG", "batch_export_tests")


@pytest.fixture(scope="class")
async def sqli_schema_name():
    """Generate a unique schema name for this test session to avoid collisions."""
    return f"sqli_tests_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="class")
async def sqli_other_schema_name(sqli_schema_name: str):
    """Generate the companion 'other' schema name used by cross-schema tests."""
    return f"{sqli_schema_name}_other"


@pytest.fixture(scope="class")
async def databricks_client(sqli_schema_name: str):
    """Create a connected DatabricksClient for SQL injection tests."""
    client = DatabricksClient(
        server_hostname=os.getenv("DATABRICKS_BE_SERVER_HOSTNAME", ""),
        http_path=os.getenv("DATABRICKS_BE_HTTP_PATH", ""),
        client_id=os.getenv("DATABRICKS_BE_CLIENT_ID", ""),
        client_secret=os.getenv("DATABRICKS_BE_CLIENT_SECRET", ""),
        catalog=TEST_CATALOG,
        schema=sqli_schema_name,
    )
    async with client.connect(set_context=False) as connected_client:
        yield connected_client


@pytest.fixture(scope="class")
async def setup_sqli_schema(databricks_client: DatabricksClient, sqli_schema_name: str):
    """Create and tear down the test schema used by SQL injection tests."""
    await databricks_client.use_catalog(TEST_CATALOG)
    await databricks_client.execute_query(f"CREATE SCHEMA IF NOT EXISTS `{sqli_schema_name}`", fetch_results=False)
    await databricks_client.use_schema(sqli_schema_name)

    yield

    await databricks_client.use_catalog(TEST_CATALOG)
    await databricks_client.execute_query(f"DROP SCHEMA IF EXISTS `{sqli_schema_name}` CASCADE", fetch_results=False)


@pytest.fixture
async def canary_table(databricks_client: DatabricksClient, setup_sqli_schema: None):
    """Create a canary table that injection attacks will attempt to drop.

    If any injection succeeds, this table will be missing when we check for it.
    """
    table_name = f"canary_{uuid.uuid4().hex[:8]}"
    await databricks_client.acreate_table(
        table_name=table_name,
        fields=[("id", "INTEGER")],
    )
    yield table_name
    # clean up (may already be gone if injection succeeded)
    try:
        await databricks_client.adelete_table(table_name)
    except Exception:
        pass


async def _assert_table_exists(client: DatabricksClient, table_name: str, schema_name: str):
    """Re-establish catalog/schema context and assert that a table exists."""
    await client.use_catalog(TEST_CATALOG)
    await client.use_schema(schema_name)
    results = await client.execute_query(f"SELECT 1 FROM `{table_name}` LIMIT 0")
    assert results is not None


@pytest.fixture(scope="class")
async def other_schema_with_table(
    databricks_client: DatabricksClient, setup_sqli_schema: None, sqli_other_schema_name: str
):
    """Create a table in a separate schema that cross-schema injection attacks will try to target."""
    await databricks_client.execute_query(
        f"CREATE SCHEMA IF NOT EXISTS `{sqli_other_schema_name}`", fetch_results=False
    )
    table_name = f"target_{uuid.uuid4().hex[:8]}"
    await databricks_client.execute_query(
        f"CREATE TABLE IF NOT EXISTS `{sqli_other_schema_name}`.`{table_name}` (id INTEGER)", fetch_results=False
    )

    yield table_name

    # Clean up
    try:
        await databricks_client.execute_query(
            f"DROP SCHEMA IF EXISTS `{sqli_other_schema_name}` CASCADE", fetch_results=False
        )
    except Exception:
        pass


async def _assert_table_exists_in_schema(client: DatabricksClient, schema: str, table_name: str):
    """Assert that a table exists in a specific schema."""
    try:
        results = await client.execute_query(f"SELECT 1 FROM `{schema}`.`{table_name}` LIMIT 0")
    except ServerOperationError as e:
        if "TABLE_OR_VIEW_NOT_FOUND" in str(e):
            raise AssertionError(f"Table `{schema}`.`{table_name}` not found")
        raise
    assert results is not None


@SKIP_IF_MISSING_DATABRICKS_CREDENTIALS
class TestSQLInjection:
    """Test that SQL injection via backtick/quote characters in identifiers is not possible.

    Two categories of attack are tested:

    1. Multi-statement injection: Databricks doesn't support multi-statement execution,
       so payloads like "`; DROP TABLE t; --" will be rejected with a syntax error.
       These tests verify that even if the backtick quoting is broken, no damage occurs.

    2. Cross-schema targeting: breaking out of backtick quoting to form a
       fully-qualified reference that targets a different schema's objects.
       E.g. table_name = 'other_schema`.`target_table' produces:
         DROP TABLE IF EXISTS `other_schema`.`target_table`  (cross-schema drop)
    """

    # --- Multi-statement injection ---

    async def test_use_schema_multi_statement_injection(
        self, databricks_client: DatabricksClient, canary_table: str, sqli_schema_name: str
    ):
        malicious_schema = f"{sqli_schema_name}`; DROP TABLE {canary_table}; --"
        with pytest.raises(DatabricksSchemaNotFoundError):
            await databricks_client.use_schema(malicious_schema)

        await _assert_table_exists(databricks_client, canary_table, sqli_schema_name)

    async def test_use_catalog_multi_statement_injection(
        self, databricks_client: DatabricksClient, canary_table: str, sqli_schema_name: str
    ):
        malicious_catalog = f"{TEST_CATALOG}`; DROP TABLE {canary_table}; --"
        with pytest.raises(DatabricksCatalogNotFoundError):
            await databricks_client.use_catalog(malicious_catalog)

        await _assert_table_exists(databricks_client, canary_table, sqli_schema_name)

    async def test_create_table_name_multi_statement_injection(
        self, databricks_client: DatabricksClient, canary_table: str, sqli_schema_name: str
    ):
        malicious_table = f"{canary_table}` (id INTEGER); DROP TABLE {canary_table}; --"
        with pytest.raises(ServerOperationError, match="INVALID_PARAMETER_VALUE"):
            await databricks_client.acreate_table(
                table_name=malicious_table,
                fields=[("id", "INTEGER")],
            )

        await _assert_table_exists(databricks_client, canary_table, sqli_schema_name)

    async def test_create_table_field_name_multi_statement_injection(
        self, databricks_client: DatabricksClient, canary_table: str, sqli_schema_name: str
    ):
        malicious_field = f"id` INTEGER); DROP TABLE {canary_table}; CREATE TABLE x (y"
        with pytest.raises(ServerOperationError, match="DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES"):
            await databricks_client.acreate_table(
                table_name=f"safe_{uuid.uuid4().hex[:8]}",
                fields=[(malicious_field, "INTEGER")],
            )

        await _assert_table_exists(databricks_client, canary_table, sqli_schema_name)

    async def test_delete_table_multi_statement_injection(
        self, databricks_client: DatabricksClient, canary_table: str, sqli_schema_name: str
    ):
        # adelete_table uses IF EXISTS, therefore isn't expected to raise an
        # error if an invalid table name is provided - the important thing is the canary survives
        await databricks_client.adelete_table(f"{canary_table}`; DROP TABLE {canary_table}; --")
        await _assert_table_exists(databricks_client, canary_table, sqli_schema_name)

    async def test_create_volume_multi_statement_injection(
        self, databricks_client: DatabricksClient, canary_table: str, sqli_schema_name: str
    ):
        malicious_volume = f"x` COMMENT 'ok'; DROP TABLE {canary_table}; --"
        with pytest.raises(ServerOperationError, match="INVALID_ATTRIBUTE_NAME_SYNTAX"):
            await databricks_client.acreate_volume(malicious_volume)

        await _assert_table_exists(databricks_client, canary_table, sqli_schema_name)

    async def test_delete_volume_multi_statement_injection(
        self, databricks_client: DatabricksClient, canary_table: str, sqli_schema_name: str
    ):
        malicious_volume = f"x`; DROP TABLE {canary_table}; --"
        with pytest.raises(ServerOperationError, match="INVALID_ATTRIBUTE_NAME_SYNTAX"):
            await databricks_client.adelete_volume(malicious_volume)

        await _assert_table_exists(databricks_client, canary_table, sqli_schema_name)

    # --- Cross-schema targeting (single-statement attacks) ---

    async def test_cross_schema_use_schema(
        self,
        databricks_client: DatabricksClient,
        other_schema_with_table: str,
        sqli_schema_name: str,
        sqli_other_schema_name: str,
    ):
        await databricks_client.use_catalog(TEST_CATALOG)
        await databricks_client.use_schema(sqli_schema_name)

        malicious_schema = f"{TEST_CATALOG}`.`{sqli_other_schema_name}"
        with pytest.raises(DatabricksSchemaNotFoundError):
            await databricks_client.use_schema(malicious_schema)

    async def test_cross_schema_delete_table(
        self,
        databricks_client: DatabricksClient,
        other_schema_with_table: str,
        sqli_other_schema_name: str,
    ):
        # We use DROP TABLE IF EXISTS so in this test it will just attempt to
        # drop a nonexistent table, so no error is raised — the important thing
        # is the target table survives
        malicious_table = f"{sqli_other_schema_name}`.`{other_schema_with_table}"
        await databricks_client.adelete_table(malicious_table)
        await _assert_table_exists_in_schema(databricks_client, sqli_other_schema_name, other_schema_with_table)
