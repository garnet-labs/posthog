import dagster

from products.error_tracking.dags import cache_warming, symbol_set_cleanup

from . import resources

defs = dagster.Definitions(
    assets=[
        symbol_set_cleanup.symbol_sets_to_delete,
        symbol_set_cleanup.symbol_set_cleanup_results,
    ],
    jobs=[
        symbol_set_cleanup.symbol_set_cleanup_job,
        cache_warming.error_tracking_cache_warming_job,
    ],
    schedules=[
        symbol_set_cleanup.daily_symbol_set_cleanup_schedule,
        cache_warming.error_tracking_cache_warming_schedule,
    ],
    resources=resources,
)
