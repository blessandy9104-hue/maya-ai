"""Wireframe embodiment — Maya's animated 3D wireframe face.

A deterministic, software-projected 3D facial mesh rendered as a live Tk
canvas widget. Pipeline: validated emotion metadata -> emotion mapper ->
expression controller -> mesh deformation -> 3D projection -> canvas.

This package owns no identity state; the neutral mesh is built analytically
once (```mesh_model.build_mesh()```) and deformed per frame. It never writes
to identity or geometry files.
"""
from .face3d import MayaWireframeFace

__all__ = ["MayaWireframeFace"]