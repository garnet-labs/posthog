# ai_events: posthog.\* namespace migration blocked by children wipe

## What we tried

Move `ai_events` from `ROOT_TABLES__DO_NOT_ADD_ANY_MORE` to the `posthog` table node, following the convention comment that says "Do NOT add any new table to this, add them to the `posthog` table node."

The change:

- Removed `ai_events` from `ROOT_TABLES__DO_NOT_ADD_ANY_MORE`
- Added it to the `posthog` node children in `build_database_root_node()`
- Updated all HogQL queries to `FROM posthog.ai_events AS ai_events` (alias preserves field references)
- Updated the column rewriter scope detection and FROM swap to match `["posthog", "ai_events"]`
- Updated `filters.py` chain check

## What happened

At query time, the `posthog` node's children dict is empty — `ai_events` (and all other tables) are missing. The resolver walks `["posthog", "ai_events"]`, finds the `posthog` node, then fails to find `ai_events` inside it.

```text
posthog.hogql.errors.ResolutionError: Unknown table `ai_events`.

The above exception was the direct cause of the following exception:

posthog.hogql.errors.QueryError: Unknown table `posthog.ai_events`.
```

### Full trace

```text
File "posthog/hogql/database/database.py", line 328, in get_table
    return cast(Table, self.get_table_node(table_name).get())
File "posthog/hogql/database/database.py", line 324, in get_table_node
    return self.tables.get_child(table_name)
File "posthog/hogql/database/models.py", line 250, in get_child
    return self.children[first].get_child(rest_of_path)
File "posthog/hogql/database/models.py", line 248, in get_child
    raise ResolutionError(f"Unknown table `{first}`.")
ResolutionError: Unknown table `ai_events`.

--- triggered from ---

File "posthog/api/query.py", line 162, in create
    result = process_query_model(...)
File "posthog/api/services/query.py", line 228, in process_query_model
    result = query_runner.run(...)
File "posthog/hogql_queries/query_runner.py", line 1349, in run
    return coalescer.run_coalesced(...)
File "posthog/hogql_queries/query_coalescer.py", line 139, in run_coalesced
    result = execute()
File "posthog/hogql_queries/query_runner.py", line 1385, in _execute_and_cache_blocking
    query_result, query_duration_ms = self._call_with_rate_limits(...)
File "posthog/hogql_queries/query_runner.py", line 1192, in _call_with_rate_limits
    query_result = self.calculate()
File "posthog/hogql_queries/query_runner.py", line 1809, in calculate
    response = self._calculate()
File "posthog/hogql_queries/ai/trace_query_runner.py", line 73, in _calculate
    query_result = execute_with_ai_events_fallback(...)
File "posthog/hogql_queries/ai/ai_table_resolver.py", line 65, in execute_with_ai_events_fallback
    result = execute_hogql_query(query=query, placeholders=ai_placeholders, **kwargs)
File "posthog/hogql/query.py", line 671, in execute_hogql_query
    return HogQLQueryExecutor(*args, **kwargs).execute()
File "posthog/hogql/query.py", line 648, in execute
    prepared_execution = self._prepare_execution()
File "posthog/hogql/query.py", line 559, in _prepare_execution
    self._generate_hogql()
File "posthog/hogql/query.py", line 282, in _generate_hogql
    prepare_ast_for_printing(node=cloned_query, context=self.hogql_context, dialect="hogql"),
File "posthog/hogql/printer/utils.py", line 90, in prepare_ast_for_printing
    node = resolve_types(...)
File "posthog/hogql/resolver.py", line 103, in resolve_types
    return Resolver(...).visit(node)
File "posthog/hogql/resolver.py", line 309, in visit_select_query
    new_node.select_from = self.visit(node.select_from)
File "posthog/hogql/resolver.py", line 481, in visit_join_expr
    database_table = cast(Database, self.database).get_table(table_name_chain)
File "posthog/hogql/database/database.py", line 334, in get_table
    raise QueryError(f"Unknown table `{table_name}`.") from e
```

## What we verified

- `Database(timezone='UTC', include_posthog_tables=True)` — the `posthog` node has 45 children including `ai_events` right after construction. Resolution works.
- `Database.create_for(team=team)` — the `posthog` node has 0 children after `create_for` finishes. Resolution fails.

So something between `Database.__init__` and the end of `create_for` wipes the `posthog` node's children dict.

## Suspected cause

`create_for` does extensive post-init processing: session table overrides (`add_child` with `table_conflict_mode="override"`), warehouse table merging, view merging, data warehouse joins, etc. One of these operations likely replaces or clears the `posthog` node's children through Pydantic deep copy behavior or `merge_with`/`add_child` interactions.

We instrumented `merge_with` and `add_child` with debug logging for the `posthog` node — neither fired, meaning the children are wiped through a different mechanism (possibly Pydantic's `model_copy(deep=True)` in `clone_root_tables`, or a dict reference issue in `TableNode`'s default `children: dict = {}`).
