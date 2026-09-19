"""MAYA batch 8J — live adaptive runtime binding (top-level package).

Deliberately does NOT live inside ``maya_conversation``: the 8G package
carries a verified purity invariant (no clock/random/io/subprocess/os in its
modules, enforced by ``test_conversational_intelligence.py``). The 8J adapter
is the one component that legitimately reads the environment (opt-in gate) and
optionally writes a bounded journal, so it is hosted OUTSIDE that package and
imports ``maya_conversation`` read-only.
"""