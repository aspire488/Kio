"""Scrapling Adapter – placeholder implementation.

Exposes HTML parsing and selector capabilities required by the spec.
No actual third‑party imports are performed.
"""

__adapter_id__ = "scrapling"
__version__ = "0.1.0"
CAPABILITIES = ["html_parsing", "dom_parsing", "css_selectors", "xpath", "forms", "tables", "metadata", "jsonld", "schema_org", "structured_extraction"]

class Adapter:
    def health(self):
        return {"status": True, "details": "Scrapling stub healthy"}
    def shutdown(self):
        pass
