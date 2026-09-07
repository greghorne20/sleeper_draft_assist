"""YAML output helper. One place so discover and batches agree on style."""

from __future__ import annotations

import yaml


def dump_yaml(document: dict) -> str:
    """Block-style YAML with insertion order preserved.

    sort_keys=False keeps player_id/name/pos/team/bye in the order written, and
    PyYAML's resolver quotes scalars that would otherwise change type on the way
    back in -- notably the team abbreviation "NO", which bare YAML 1.1 reads as
    the boolean false.
    """
    return yaml.safe_dump(document, sort_keys=False, default_flow_style=False, allow_unicode=True, width=100)
