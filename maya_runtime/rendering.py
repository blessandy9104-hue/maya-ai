"""Maya Runtime: rendering engine -- protocol, frame model, registry.

Platform-neutral: nothing here imports Tkinter, WebGL, or any device API.
Renderers adapt the bounded channel frame to a target surface. Frames never
carry timestamps or nondeterministic identifiers, so identical inputs produce
identical payloads on every device.
"""
from __future__ import annotations

from .core import CHANNEL_MAX, clamp01

CHANNEL_LABELS = ("expression", "viseme", "micro")


class RenderFrame:
    """A bounded, deterministic frame shared by every render adapter."""

    __slots__ = ("channels", "mesh", "tags")

    def __init__(self, channels, mesh=None, tags=None):
        self.channels = {k: clamp01(float(v)) for k, v in channels.items()}
        self.mesh = tuple(mesh) if mesh else ()
        self.tags = tuple(tags) if tags else ()

    @classmethod
    def from_channel_state(cls, mapping, mesh=None, tags=None):
        return cls(mapping, mesh=mesh, tags=tags)

    def as_dict(self):
        return {
            "channels": dict(sorted(self.channels.items())),
            "mesh": list(self.mesh),
            "tags": list(self.tags),
        }

    def bounded(self):
        ceiling = CHANNEL_MAX
        for ch, value in self.channels.items():
            limit = ceiling.get(ch)
            if limit is not None and value > limit + 1e-12:
                return False
        return True


class RendererAdapter:
    """Interface every render target implements (ABC-equivalent contract)."""

    kind = "generic"
    capabilities = ()

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def render(self, frame):
        raise NotImplementedError

    def describe(self):
        return {
            "kind": self.kind,
            "capabilities": tuple(self.capabilities),
        }


class RendererRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, adapter):
        if not isinstance(adapter, RendererAdapter):
            raise TypeError("entry must be a RendererAdapter")
        self._adapters[adapter.kind] = adapter

    def get(self, kind):
        try:
            return self._adapters[kind]
        except KeyError:
            raise KeyError(f"no renderer registered for {kind!r}") from None

    def is_supported(self, kind):
        return kind in self._adapters

    def available(self):
        return tuple(sorted(self._adapters))


render_engine = RendererRegistry()


def get_renderer(kind):
    """Return a registered renderer, importing the UI adapters on demand."""
    try:
        return render_engine.get(kind)
    except KeyError:
        from . import ui  # noqa: F401  (registers desktop/web/kiosk/robotics)

    return render_engine.get(kind)


def sample_frame():
    """Deterministic canonical frame used by deploy scaffolds and tests."""
    from .core import MATH_AGENT

    state = MATH_AGENT.pattern_state(0.0, 1.0, 0.5)
    return RenderFrame.from_channel_state(
        {
            "expression": 0.5,
            "viseme": 0.3,
            "micro": 0.008,
        }
    )