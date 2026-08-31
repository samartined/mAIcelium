"""Either-order resolution of a (name, path) pair for inject-style commands.

`add_project` and `add_mesh_layer` take a project/layer NAME and a filesystem
PATH. Historically the order was fixed (name first, path second). This helper lets
the two positionals be given in EITHER order and figures out which is which:

- A PATH points at a directory that exists on disk (resolved relative to the current
  working directory, so a bare folder name written WITHOUT a slash also counts).
- A NAME is a bare identifier (``^[a-zA-Z0-9_-]+$`` -- no slash, dot or ``~``).

Resolution (first rule that applies):
  1. Explicit ``--path`` / ``--name`` flags win. A lone flag pairs with the single
     remaining positional.
  2. Exactly one positional is an existing directory -> that is the path, the other
     the name (handles both orders and the bare-cwd-folder case).
  3. Both are existing directories -> use name-shape to disambiguate (a slash/dot
     token can only be the path). If both are bare identifiers it is a genuine tie
     -> raise ``AmbiguousArgsError`` (callers turn this into a hard error that forces
     the user to pass ``--path`` / ``--name``).
  4. Neither is an existing directory (an error case downstream) -> use name-shape to
     name the real path in the "does not exist" message; if that cannot decide, fall
     back to the classic order (name first, path second) for backwards compatibility.

The path is returned RAW; callers apply their own ``os.path.realpath`` / existence
validation exactly as before.
"""
import os
import re

# A bare, sluggable identifier: no slash, dot, tilde or whitespace.
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class AmbiguousArgsError(Exception):
    """Both positionals are existing directories AND both look like bare names."""

    def __init__(self, a, b):
        self.a = a
        self.b = b
        super().__init__(
            f"ambiguous: {a!r} and {b!r} are both existing directories"
        )


def _is_existing_dir(value):
    """True if `value` resolves (relative to cwd) to an existing directory."""
    try:
        return os.path.isdir(os.path.realpath(value))
    except OSError:
        return False


def _is_name_like(value):
    """True if `value` is a bare identifier (a plausible name, never a path)."""
    return bool(NAME_RE.match(value))


def resolve_name_and_path(positionals, name_flag=None, path_flag=None):
    """Return ``(name, raw_path)`` from up to two positionals, in either order.

    Raises:
        AmbiguousArgsError: both positionals are existing dirs and both are bare names.
        ValueError: wrong number of positionals for the given flags (caller prints Usage).
    """
    pos = list(positionals)

    # 1. Explicit flags win.
    if name_flag is not None or path_flag is not None:
        name = name_flag
        path = path_flag
        if name is None:
            if len(pos) != 1:
                raise ValueError("with --path, give exactly one positional (the name)")
            name = pos[0]
        elif path is None:
            if len(pos) != 1:
                raise ValueError("with --name, give exactly one positional (the path)")
            path = pos[0]
        elif pos:
            raise ValueError("--path and --name given; no positionals expected")
        return name, path

    # 2-4. Two positionals, resolve by existence then name-shape.
    if len(pos) != 2:
        raise ValueError(f"expected 2 positionals, got {len(pos)}")
    a, b = pos
    a_dir, b_dir = _is_existing_dir(a), _is_existing_dir(b)

    if a_dir and not b_dir:
        return b, a  # a is the path
    if b_dir and not a_dir:
        return a, b  # b is the path

    a_name, b_name = _is_name_like(a), _is_name_like(b)

    if a_dir and b_dir:
        # Both exist: a slash/dot token can only be the path.
        if a_name and not b_name:
            return a, b
        if b_name and not a_name:
            return b, a
        raise AmbiguousArgsError(a, b)

    # Neither exists (downstream will error): name the real path if shape decides.
    if a_name and not b_name:
        return a, b
    if b_name and not a_name:
        return b, a
    # Cannot tell -> classic order (name first, path second).
    return a, b
