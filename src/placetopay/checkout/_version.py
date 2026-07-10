"""Single source of truth for the package version.

``hatch`` reads this file at build time (see ``[tool.hatch.version]`` in
``pyproject.toml``), and the runtime code imports it from here, so the two
never drift out of sync.
"""

__version__ = "1.0.0"
