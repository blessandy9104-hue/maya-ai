"""Procedural visual engine — Maya's digital body.

Pure geometry -> expression -> hologram as a live Tk canvas. This package owns
no state beyond the presentation surface; identity stays in ``geometry/`` and
``identity.json``.

``TemporaryShapeRenderer`` is the Batch 8C temporary geometric embodiment:
a non-face shape driven purely by ``VisualState``. It is intended to be
replaced by a future ``MayaFaceRenderer`` without touching the semantic
pipeline upstream of ``VisualState``.
"""
from .hologram_renderer import HologramRenderer, ProceduralFace
from .temporary_shape import TemporaryShapeRenderer

__all__ = ["HologramRenderer", "ProceduralFace", "TemporaryShapeRenderer"]