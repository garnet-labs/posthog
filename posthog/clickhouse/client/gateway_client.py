"""Gateway client that sends structured JSON to the ClickHouse Query Gateway."""

import threading
from contextlib import contextmanager
from typing import Any, Optional

from django.conf import settings

import requests


class GatewayClient:
    """Sends queries to the ClickHouse Gateway instead of directly to CH.

    Drop-in replacement for ProxyClient — implements the same execute() interface
    but serializes the query as structured JSON and POSTs it to the gateway service.

    NOTE: Uses synchronous ``requests.Session``. Do not call from async Django
    views or async Celery workers — it will block the event loop. If we need
    async support later, swap to ``httpx.AsyncClient`` and add an ``aexecute()``
    method.
    """

    def __init__(self, gateway_url: str, service_token: str):
        self.gateway_url = gateway_url.rstrip("/")
        self.service_token = service_token
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {service_token}"
        self.session.headers["Content-Type"] = "application/json"

    def execute(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
        with_column_types: bool = False,
        external_tables: Any = None,
        query_id: Optional[str] = None,
        settings: Optional[dict[str, Any]] = None,
        types_check: bool = False,
        columnar: bool = False,
    ) -> Any:
        """Execute query via the gateway. Matches ProxyClient.execute() interface."""
        if external_tables:
            raise NotImplementedError("external_tables are not supported by the ClickHouse Gateway")
        # Extract structured metadata from the log_comment JSON that sync_execute
        # packs into settings. The gateway will use these for routing/observability
        # instead of requiring the caller to parse them back out.
        query_tags = _extract_query_tags(settings)

        payload: dict[str, Any] = {
            "sql": query,
            "params": params,
            "settings": _clean_settings(settings),
            "query_tags": query_tags,
            "query_id": query_id,
            "columnar": columnar,
        }

        # Extract routing metadata from query_tags so the gateway can route
        # and enforce limits without parsing log_comment JSON itself.
        if query_tags:
            for field in ("team_id", "workload", "ch_user", "read_only"):
                if field in query_tags and field not in payload:
                    payload[field] = query_tags[field]

        timeout = _get_timeout()
        resp = self.session.post(
            f"{self.gateway_url}/query",
            json=payload,
            timeout=timeout,
        )
        _check_response(resp)
        data = resp.json()

        # Mirror ProxyClient behavior: INSERT queries return written_rows count.
        # Check for key existence, not value > 0 — a zero-row INSERT (e.g.
        # INSERT ... WHERE 1=0) should still return 0, not [].
        if "written_rows" in data:
            return data["written_rows"]

        if with_column_types:
            return data.get("data", []), data.get("column_types", [])
        return data.get("data", [])

    # Context-manager protocol so GatewayClient can be used in all places
    # a clickhouse_driver.Client or ProxyClient is used (with ... as client).
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _extract_query_tags(settings_dict: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Pull the log_comment JSON out of settings and parse it back into a dict.

    sync_execute serializes QueryTags into settings["log_comment"] as a JSON string.
    The gateway wants structured tags, so we deserialize them here.
    """
    if not settings_dict or "log_comment" not in settings_dict:
        return None
    import json

    log_comment = settings_dict["log_comment"]
    if isinstance(log_comment, str):
        try:
            return json.loads(log_comment)
        except (json.JSONDecodeError, ValueError):
            return {"raw": log_comment}
    return None


def _clean_settings(settings_dict: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return settings with log_comment stripped — the gateway gets tags separately."""
    if not settings_dict:
        return settings_dict
    return {k: v for k, v in settings_dict.items() if k != "log_comment"}


def _check_response(resp: requests.Response) -> None:
    """Translate HTTP errors from the gateway into ClickHouse-compatible exceptions.

    The gateway returns structured JSON errors with `error` and `error_type` fields.
    We raise a ServerException (from clickhouse_driver) when possible so that existing
    retry logic and error classification in PostHog's sync_execute still works.
    Falls back to requests.HTTPError for non-JSON or unexpected responses.
    """
    if resp.ok:
        return

    # Try to parse gateway error JSON
    try:
        body = resp.json()
        error_msg = body.get("error", resp.text)
        error_type = body.get("error_type", "unknown")
    except Exception:
        error_msg = resp.text
        error_type = "unknown"

    # Import lazily to avoid hard dependency at module level
    try:
        from clickhouse_driver.errors import ServerException

        raise ServerException(message=f"Gateway {error_type}: {error_msg}", code=resp.status_code)
    except ImportError:
        resp.raise_for_status()


def _get_timeout() -> tuple[int, int]:
    """Read gateway timeout from settings, with a sensible default.

    Returns a (connect, read) tuple so that an unreachable gateway fails
    fast on connect (5s) instead of blocking the thread for the full read timeout.
    """
    read_timeout = getattr(settings, "CLICKHOUSE_GATEWAY_TIMEOUT", 600)
    return (5, read_timeout)


# ---------------------------------------------------------------------------
# Singleton / cached client
# ---------------------------------------------------------------------------

_gateway_client: Optional[GatewayClient] = None
_gateway_client_lock = threading.Lock()


def get_gateway_client() -> GatewayClient:
    """Return a cached GatewayClient instance.

    The client holds a requests.Session which manages its own connection pool,
    so we reuse a single instance for the lifetime of the process.

    Thread-safe: uses double-checked locking to avoid races under WSGI
    multi-threading while keeping the fast path lock-free.

    Raises ValueError if CLICKHOUSE_GATEWAY_SERVICE_TOKEN is empty — running
    the gateway without auth would silently accept any caller.
    """
    global _gateway_client
    if _gateway_client is not None:
        return _gateway_client
    with _gateway_client_lock:
        # Double-check after acquiring lock — re-read the global so mypy
        # doesn't carry the narrowed-to-None type from above.
        client = _gateway_client
        if client is not None:
            return client
        token = settings.CLICKHOUSE_GATEWAY_SERVICE_TOKEN
        if not token:
            raise ValueError("CLICKHOUSE_GATEWAY_SERVICE_TOKEN must be set when CLICKHOUSE_GATEWAY_ENABLED is true")
        _gateway_client = GatewayClient(
            gateway_url=settings.CLICKHOUSE_GATEWAY_URL,
            service_token=token,
        )
    return _gateway_client


class RoutedGatewayClient:
    """Thin wrapper that injects routing defaults (workload, ch_user, etc.)
    into every ``execute()`` call.

    The underlying ``GatewayClient`` is a singleton. This wrapper carries the
    per-call routing context that ``get_client_from_pool()`` receives.
    """

    def __init__(
        self,
        client: GatewayClient,
        *,
        workload: Optional[str] = None,
        team_id: Optional[int] = None,
        readonly: bool = False,
        ch_user: Optional[str] = None,
    ):
        self._client = client
        self._defaults: dict[str, Any] = {}
        if workload is not None:
            self._defaults["workload"] = workload
        if team_id is not None:
            self._defaults["team_id"] = team_id
        if readonly:
            self._defaults["read_only"] = True
        if ch_user is not None:
            self._defaults["ch_user"] = ch_user

    def execute(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
        with_column_types: bool = False,
        external_tables: Any = None,
        query_id: Optional[str] = None,
        settings: Optional[dict[str, Any]] = None,
        types_check: bool = False,
        columnar: bool = False,
    ) -> Any:
        # Inject routing defaults into query_tags via settings["log_comment"].
        # If there's already a log_comment, merge defaults under it so the
        # GatewayClient's _extract_query_tags picks them up. Query's own tags
        # take precedence (handled in GatewayClient.execute's field-level check).
        import json

        merged_settings = dict(settings) if settings else {}
        if self._defaults:
            existing_comment = merged_settings.get("log_comment", "{}")
            try:
                comment_dict = json.loads(existing_comment) if isinstance(existing_comment, str) else {}
            except (json.JSONDecodeError, ValueError):
                comment_dict = {}
            # Defaults don't override existing values
            for k, v in self._defaults.items():
                comment_dict.setdefault(k, v)
            merged_settings["log_comment"] = json.dumps(comment_dict)

        return self._client.execute(
            query,
            params=params,
            with_column_types=with_column_types,
            external_tables=external_tables,
            query_id=query_id,
            settings=merged_settings,
            types_check=types_check,
            columnar=columnar,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@contextmanager
def get_gateway_client_ctx(
    workload: Optional[str] = None,
    team_id: Optional[int] = None,
    readonly: bool = False,
    ch_user: Optional[str] = None,
):
    """Context-manager wrapper matching the get_http_client() interface.

    get_client_from_pool() expects a context manager, so we wrap the singleton.
    Routing params from get_client_from_pool are passed through to every execute().
    """
    client = get_gateway_client()
    if workload or team_id or readonly or ch_user:
        yield RoutedGatewayClient(
            client,
            workload=workload,
            team_id=team_id,
            readonly=readonly,
            ch_user=ch_user,
        )
    else:
        yield client


def reset_gateway_client() -> None:
    """Reset the cached client — useful for tests."""
    global _gateway_client
    _gateway_client = None
