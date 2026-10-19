#!/usr/bin/env python3
"""Convenience launcher so the server can be run from a checkout without
installing: ``python3 ./main.py [options]``.

It simply delegates to the package CLI. Prefer ``dz`` (after
``pipx install .``) or ``python -m dropzone`` once installed.
"""

from dropzone.cli import main

if __name__ == "__main__":
    main()
