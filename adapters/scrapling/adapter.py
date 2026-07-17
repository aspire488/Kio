"""Scrapling Adapter – placeholder implementation.

Exposes HTML parsing and selector capabilities required by the spec.
No actual third‑party imports are performed.
"""

__adapter_id__ = "scrapling"
__version__ = "0.1.0"
CAPABILITIES = ["html_parsing", "dom_parsing", "css_selectors", "xpath", "forms", "tables", "metadata", "jsonld", "schema_org", "structured_extraction"]

class Adapter:
    """Full Scrapling adapter exposing extraction capabilities.

    Implements the contract required by AdapterRegistry. Uses internal
    stub modules for parsing, selection and extraction. All heavy‑weight work
    is delegated to these modules; the adapter itself only wires them together.
    """

    def __init__(self):
        self.id = __adapter_id__
        self.version = __version__
        self._capabilities = CAPABILITIES
        # Simple health state – can be expanded later
        self._last_error = None

    def health(self):
        """Return health information.

        Fields: status (bool), version, backend (str), supported_features (list),
        latency (ms placeholder), last_error (optional).
        """
        return {
            "status": True,
            "version": self.version,
            "backend": "scrapling_stub",
            "supported_features": self._capabilities,
            "latency": 0,
            "last_error": self._last_error,
        }

    def capabilities(self):
        return self._capabilities

    # Extraction methods – each accepts the raw input from BrowserFacade and
    # returns a simple placeholder structure. Real implementations would parse
    # and transform the data.
    def extract_html(self, html: str):
        return {"html": html}

    def extract_dom(self, html: str):
        from .parser import parse
        return parse(html)

    def extract_tables(self, dom):
        from .tables import extract_tables
        return extract_tables(dom)

    def extract_forms(self, dom):
        from .forms import extract_forms
        return extract_forms(dom)

    def extract_metadata(self, dom):
        from .metadata import extract_metadata
        return extract_metadata(dom)

    def extract_jsonld(self, dom):
        from .jsonld import extract_jsonld
        return extract_jsonld(dom)

    def extract_schema(self, dom):
        from .schema import extract_schema
        return extract_schema(dom)

    def extract_links(self, dom):
        from .extractor import extract
        return extract(dom, "a[href]")

    def extract_images(self, dom):
        from .extractor import extract
        return extract(dom, "img[src]")

    def extract_text(self, dom):
        from .extractor import extract
        return extract(dom, "body")

    def normalize(self, data):
        from .normalizer import normalize
        return normalize(data)

    def health(self):
        return {"status": True, "details": "Scrapling stub healthy"}
    def shutdown(self):
        pass
