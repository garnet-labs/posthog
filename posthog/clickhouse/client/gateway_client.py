"""Gateway client that sends structured JSON to the ClickHouse Query Gateway."""

from contextlib import contextmanager
from typing import Any, Optional

from django.conf import settings

import requests


class GatewayClient:
    """Sends queries to the ClickHouse Gateway instead of directly to CH.

    Drop-in replacement for ProxyClient — implements the same execute() interface
    but serializes the query as structured JSON and POSTs it to the gateway service.
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

        timeout = _get_timeout()
        resp = self.session.post(
            f"{self.gateway_url}/query",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        # Mirror ProxyClient behavior: INSERT queries return written_rows count
        written_rows = data.get("written_rows", 0)
        if written_rows > 0:
            return written_rows

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


def _get_timeout() -> int:
    """Read gateway timeout from settings, with a sensible default."""
    return getattr(settings, "CLICKHOUSE_GATEWAY_TIMEOUT", 600)


# ---------------------------------------------------------------------------
# Singleton / cached client
# ---------------------------------------------------------------------------

_gateway_client: Optional[GatewayClient] = None


def get_gateway_client() -> GatewayClient:
    """Return a cached GatewayClient instance.

    The client holds a requests.Session which manages its own connection pool,
    so we reuse a single instance for the lifetime of the process.
    """
    global _gateway_client
    if _gateway_client is None:
        _gateway_client = GatewayClient(
            gateway_url=settings.CLICKHOUSE_GATEWAY_URL,
            service_token=settings.CLICKHOUSE_GATEWAY_SERVICE_TOKEN,
        )
    return _gateway_client


@contextmanager
def get_gateway_client_ctx():
    """Context-manager wrapper matching the get_http_client() interface.

    get_client_from_pool() expects a context manager, so we wrap the singleton.
    """
    yield get_gateway_client()


def reset_gateway_client() -> None:
    """Reset the cached client — useful for tests."""
    global _gateway_client
    _gateway_client = None
