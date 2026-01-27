"""Tests for pampu CLI."""

from pampu import __version__


def test_version():
    """Version is set."""
    assert __version__
