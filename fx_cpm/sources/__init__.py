"""Pluggable, provenance-preserving source adapters."""

from .base import DataSource, SourceDescriptor, SourceFetchResult, StaticSource, source_health

__all__ = ["DataSource", "SourceDescriptor", "SourceFetchResult", "StaticSource", "source_health"]
