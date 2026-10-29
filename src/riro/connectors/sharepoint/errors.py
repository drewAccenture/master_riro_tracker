"""Errors the SharePoint connector raises. Services turn them into plain words (services/sync.py)."""


class ConnectorError(Exception):
    kind = "ConnectorError"


class NeedsSignIn(ConnectorError):
    kind = "NeedsSignIn"


class NoAccess(ConnectorError):
    kind = "NoAccess"


class NotFound(ConnectorError):
    kind = "NotFound"


class Unreachable(ConnectorError):
    kind = "Unreachable"


class TimedOut(ConnectorError):
    kind = "TimedOut"


class EdgeNotStarted(TimedOut):
    """ADR-003/ADR-009: Edge did not answer on its DevTools port in time. Still the TimedOut kind."""


class EdgeMissing(ConnectorError):
    kind = "EdgeMissing"
