"""Thin application-facing Cognityx Python SDK."""

from cognityx.client import Cogni
from cognityx.ingest_config import IngestConfiguration, load_ingest_configuration

__all__ = ["Cogni", "IngestConfiguration", "load_ingest_configuration"]
