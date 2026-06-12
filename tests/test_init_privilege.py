"""Init must abort cleanly when symlink privilege is unavailable."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"))

import init  # noqa: E402


def test_init_aborts_without_privilege(tmp_path, monkeypatch):
    """When symlink privilege is missing, init returns non-zero and creates nothing."""
    monkeypatch.setattr("init.check_symlink_privilege", lambda: False)
    rc = init.main(root=str(tmp_path))
    assert rc != 0
    # Nothing should have been created
    assert not os.path.exists(os.path.join(str(tmp_path), ".cursor"))
    assert not os.path.exists(os.path.join(str(tmp_path), "WORKSPACE.md"))
    assert not os.path.exists(os.path.join(str(tmp_path), "mesh"))
