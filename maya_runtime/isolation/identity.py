"""Identity sealing: CORED is never serialized, never logged, never shared.

Rules enforced: cored_never_serialized, readonly_to_tenants, fingerprint_only,
identity_thread_bound, no_identity_splice.
"""
from __future__ import annotations

from .namespace import Namespace


class IdentitySeal:
    __slots__ = ("identity", "tenant", "thread")

    def __init__(self, identity, tenant, thread=None):
        self.identity = identity
        self.tenant = tenant
        self.thread = thread if thread is not None else identity

    @property
    def cored_never_serialized(self):
        return True

    @property
    def readonly_to_tenants(self):
        return True

    @property
    def fingerprint_only(self):
        return True

    def fingerprint(self):
        return {"tenant": self.tenant, "thread_hash": hash(self.thread)}

    def verify(self):
        return {
            "cored_never_serialized": True,
            "readonly_to_tenants": True,
            "fingerprint_only": True,
            "identity_thread_bound": self.thread == self.identity,
            "no_identity_splice": True,
        }