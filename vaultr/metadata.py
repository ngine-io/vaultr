"""Project identity and stable paths surfaced in the UI.

Kept next to the code rather than in the template so the values stay in one place and
can be asserted on in tests.
"""

from vaultr.version import __version__

PROJECT_NAME = "Vaultr"
PROJECT_URL = "https://github.com/ngine-io/vaultr"
DOCS_URL = "https://ngine-io.github.io/vaultr/"
LICENSE_NAME = "Apache-2.0"
LICENSE_URL = f"{PROJECT_URL}/blob/main/LICENSE"

API_DOCS_PATH = "/api"
"""Where the interactive OpenAPI browser is served."""

MCP_PATH = "/mcp"
"""Mount point of the MCP endpoint."""

__all__ = [
    "API_DOCS_PATH",
    "DOCS_URL",
    "LICENSE_NAME",
    "LICENSE_URL",
    "MCP_PATH",
    "PROJECT_NAME",
    "PROJECT_URL",
    "__version__",
]
