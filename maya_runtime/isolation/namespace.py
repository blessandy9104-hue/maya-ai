"""Namespace sealing: the NS(t, k) model -- NS(t,k) :: /t/k/*.

Every tenant lives in exactly one namespace. Resource kinds (data, logs,
policies, brand, outputs, metadata) are namespaced and disjoint across
tenants. A namespace is a pure value object: no IO, no randomness, no globals.
"""
from __future__ import annotations

RESOURCE_KINDS = ("data", "logs", "policies", "brand", "outputs", "metadata")


class Namespace:
    __slots__ = ("tenant", "kind", "_path")

    def __init__(self, tenant, kind):
        if kind not in RESOURCE_KINDS:
            raise ValueError(f"unknown resource kind: {kind!r}")
        self.tenant = tenant
        self.kind = kind
        self._path = f"/{tenant}/{kind}"

    @property
    def path(self):
        return self._path

    def contains(self, path):
        return path is not None and path.startswith(self._path + "/") or path == self._path

    def disjoint(self, other):
        return self.tenant != other.tenant or self.kind != other.kind

    def __eq__(self, other):
        return isinstance(other, Namespace) and (self.tenant, self.kind) == (other.tenant, other.kind)

    def __hash__(self):
        return hash((self.tenant, self.kind))

    def __repr__(self):
        return f"Namespace({self._path!r})"


NAMESPACE_FORMULA = "NS(t,k) :: /t/k/*"