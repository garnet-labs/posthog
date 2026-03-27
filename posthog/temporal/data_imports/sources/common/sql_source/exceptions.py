class SQLSourceError(Exception):
    """Base exception for SQL source errors."""

    pass


class SSLRequiredError(SQLSourceError):
    """Raised when SSL/TLS is required but the database does not support it."""

    pass
