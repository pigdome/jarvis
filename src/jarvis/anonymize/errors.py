"""Exceptions raised by the anonymize package."""


class ProfileError(ValueError):
    """A profile cannot be found, read or is invalid."""


class DumpFormatError(Exception):
    """A SQL dump cannot be parsed or rewritten safely."""
