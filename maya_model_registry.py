"""Model registry — single owner of Maya's local inference model choice.

The chat layer reads its default model from here instead of a hard-coded
literal, so the model name lives in exactly one place. Deterministic and
I/O-free at import time: this module never touches the network, the clock,
or the filesystem, so importing it cannot fail or block.
"""
from __future__ import annotations

DEFAULT_MODEL = "qwen2.5-coder:3b"

MODELS = {
    "local_default": {
        "name": DEFAULT_MODEL,
        "role": "primary_chat",
        "notes": "Local Ollama model; private, no network egress.",
    },
}


def default_model():
    """The active chat model name (used by the Ollama client)."""
    return DEFAULT_MODEL


def registered_models():
    """All registered model entries, as a fresh dict (callers may read but
    not mutate the registry)."""
    return dict(MODELS)


def describe_models():
    """Plain list of registered models for status/report surfaces."""
    return [
        {
            "key": key,
            "name": entry.get("name"),
            "role": entry.get("role"),
            "notes": entry.get("notes"),
        }
        for key, entry in sorted(MODELS.items())
    ]