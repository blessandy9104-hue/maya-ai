"""Web renderer adapter (Canvas / WebGL-ready stub).

Produces a JSON-serializable surface payload with no GPU work performed here;
the payload is ready for a Canvas or WebGL front-end. Deterministic and
device-neutral.
"""
from __future__ import annotations

from ..rendering import RendererAdapter


class WebRenderer(RendererAdapter):
    kind = "web"
    capabilities = ("canvas", "webgl")

    def render(self, frame):
        data = frame.as_dict()
        return {
            "context": "web",
            "backend": ["canvas", "webgl"],
            "channels": dict(sorted(data["channels"].items())),
            "surface": [list(p) for p in data["mesh"]],
            "primitives": len(data["mesh"]),
            "state": "ready",
        }

    def start(self):
        return {"context": "web", "state": "ready"}

    def stop(self):
        return {"context": "web", "state": "stopped"}