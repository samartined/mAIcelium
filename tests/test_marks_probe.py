"""Tests proving TR-2: _symlink_privilege() fails loudly on ImportError.

These tests call _symlink_privilege() directly (bypassing the module-level
constant) so they can monkeypatch the imported names.
"""
import sys
import warnings

import pytest


def _get_symlink_privilege_fn():
    """Import _symlink_privilege fresh each time tests need it."""
    import importlib
    import _marks
    importlib.reload(_marks)
    return _marks._symlink_privilege


def test_force_no_symlink_env_returns_false(monkeypatch):
    """MAICELIUM_FORCE_NO_SYMLINK=1 must make _symlink_privilege return False."""
    monkeypatch.setenv("MAICELIUM_FORCE_NO_SYMLINK", "1")
    from _marks import _symlink_privilege
    assert _symlink_privilege() is False


def test_probe_does_not_mask_import_error(monkeypatch):
    """An ImportError from _lib.platform must propagate, NOT be swallowed."""
    # Inject None as the module entry so any 'from _lib.platform import ...'
    # inside _symlink_privilege raises ImportError.
    monkeypatch.setitem(sys.modules, "_lib.platform", None)
    monkeypatch.delenv("MAICELIUM_FORCE_NO_SYMLINK", raising=False)

    from _marks import _symlink_privilege
    with pytest.raises(ImportError):
        _symlink_privilege()


def test_probe_treats_oserror_as_no_privilege(monkeypatch):
    """OSError from check_symlink_privilege must cause _symlink_privilege to return False."""
    import _lib.platform as plat

    monkeypatch.delenv("MAICELIUM_FORCE_NO_SYMLINK", raising=False)
    monkeypatch.setattr(plat, "check_symlink_privilege", lambda: (_ for _ in ()).throw(OSError("probe failed")))

    from _marks import _symlink_privilege
    assert _symlink_privilege() is False


def test_probe_warns_on_unexpected_exception(monkeypatch):
    """Unexpected exceptions from check_symlink_privilege must emit a RuntimeWarning and return False."""
    import _lib.platform as plat

    monkeypatch.delenv("MAICELIUM_FORCE_NO_SYMLINK", raising=False)
    monkeypatch.setattr(plat, "check_symlink_privilege", lambda: (_ for _ in ()).throw(RuntimeError("unexpected")))

    from _marks import _symlink_privilege
    with pytest.warns(RuntimeWarning, match="symlink privilege probe failed unexpectedly"):
        result = _symlink_privilege()
    assert result is False
