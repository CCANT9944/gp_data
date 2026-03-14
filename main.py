"""Compatibility entrypoint for running gp_data as a script or package."""

# When run as a script (python main.py) the module has no package context;
# add the parent folder to sys.path and set __package__ so relative imports
# (used across the package) resolve correctly. If the module is executed
# with -m (python -m gp_data) this block is a no-op.
if __package__ is None:
    import os
    import sys

    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent not in sys.path:
        sys.path.insert(0, parent)
    __package__ = "gp_data"

from .cli import main, run_cli, run_gui


if __name__ == "__main__":
    raise SystemExit(main())
