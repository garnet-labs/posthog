from posthog.temporal.ducklake.compaction_workflow import DucklakeCompactionWorkflow, run_ducklake_compaction
from posthog.temporal.ducklake.ducklake_copy_data_imports_workflow import (
    DuckLakeCopyDataImportsWorkflow,
    cleanup_data_imports_staging_activity,
    copy_data_imports_to_ducklake_activity,
    ducklake_copy_data_imports_gate_activity,
    prepare_data_imports_ducklake_metadata_activity,
    verify_data_imports_ducklake_copy_activity,
)
from posthog.temporal.ducklake.ducklake_copy_data_modeling_workflow import (
    DuckLakeCopyDataModelingWorkflow,
    cleanup_data_modeling_staging_activity,
    copy_data_modeling_model_to_ducklake_activity,
    ducklake_copy_workflow_gate_activity,
    prepare_data_modeling_ducklake_metadata_activity,
    verify_ducklake_copy_activity,
)
from posthog.temporal.ducklake.duckling_backfill_activities import (
    check_auto_pause_activity,
    copy_partition_files_activity,
    register_with_ducklake_activity,
    resolve_duckling_config_activity,
    update_backfill_run_status_activity,
)
from posthog.temporal.ducklake.duckling_backfill_workflow import DucklingBackfillWorkflow

WORKFLOWS = [DucklakeCompactionWorkflow, DuckLakeCopyDataImportsWorkflow, DuckLakeCopyDataModelingWorkflow]
ACTIVITIES = [
    cleanup_data_imports_staging_activity,
    cleanup_data_modeling_staging_activity,
    copy_data_imports_to_ducklake_activity,
    copy_data_modeling_model_to_ducklake_activity,
    ducklake_copy_data_imports_gate_activity,
    ducklake_copy_workflow_gate_activity,
    prepare_data_imports_ducklake_metadata_activity,
    prepare_data_modeling_ducklake_metadata_activity,
    run_ducklake_compaction,
    verify_data_imports_ducklake_copy_activity,
    verify_ducklake_copy_activity,
]

DUCKLING_BACKFILL_WORKFLOWS = [DucklingBackfillWorkflow]
DUCKLING_BACKFILL_ACTIVITIES = [
    check_auto_pause_activity,
    copy_partition_files_activity,
    register_with_ducklake_activity,
    resolve_duckling_config_activity,
    update_backfill_run_status_activity,
]
