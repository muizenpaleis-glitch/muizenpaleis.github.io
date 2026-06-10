"""Pluggable source modules (req. 4). Importing this package registers
all built-in collectors; adding a source means adding a module here
and registering it - the core is never touched."""

from .base import REGISTRY, Collector, CollectorContext, register  # noqa: F401
from . import setlistfm  # noqa: F401  (registers itself)
