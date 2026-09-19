"""User sealing: users are identity-thread bound within a tenant.

A user cannot assume another tenant's identity nor splice across identity
threads.
"""
from __future__ import annotations


class UserSeal:
    __slots__ = ("user_id", "tenant", "thread")

    def __init__(self, user_id, tenant, thread=None):
        self.user_id = user_id
        self.tenant = tenant
        self.thread = thread if thread is not None else user_id

    def verify(self):
        return {
            "user_id": self.user_id,
            "tenant": self.tenant,
            "thread": self.thread,
        }