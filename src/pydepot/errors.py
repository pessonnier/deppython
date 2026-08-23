class PyDepotError(Exception):
    """Expected error that can be shown directly to the user."""


class BundleError(PyDepotError):
    """A bundle is invalid or incompatible."""


class CommandError(PyDepotError):
    """An external command failed."""

