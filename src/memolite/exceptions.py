"""Exceptions."""


class MemoliteError(Exception):
    """Base."""


class NotFoundError(MemoliteError):
    pass


class ValidationError(MemoliteError):
    pass
