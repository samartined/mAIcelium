"""Load mesh conventions from mesh/conventions.json.

Replaces `_load_conventions` from bin/_lib.sh (lines 8-27).
"""
import json
import os

DEFAULT_CONVENTIONS = {
    "project_data_dir": ".cursor",
    "project_data_subdirs": ["plans", "bitacora", "config", "agents", "docs"],
    "project_rules_subdir": "rules",
    "project_skills_subdirs": ["skills", "skills-cursor"],
}


def load_conventions(root):
    """Return convention dict from mesh/conventions.json or defaults if absent."""
    conv_path = os.path.join(root, "mesh", "conventions.json")
    if not os.path.isfile(conv_path):
        return dict(DEFAULT_CONVENTIONS)

    with open(conv_path, encoding="utf-8") as f:
        data = json.load(f)

    out = dict(DEFAULT_CONVENTIONS)
    for k in DEFAULT_CONVENTIONS:
        if k in data:
            out[k] = data[k]
    return out
