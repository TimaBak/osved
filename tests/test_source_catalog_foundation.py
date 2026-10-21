"""The optional source catalog is valid but does not silently activate sources."""

from pathlib import Path

from app.config import load_source_registry

ROOT = Path(__file__).resolve().parents[1]


def test_opt_in_source_catalog_has_unique_entries() -> None:
    registry = load_source_registry(ROOT / "examples/source-catalog-foundation.yaml")
    ids = [source.id for source in registry.sources]
    assert len(ids) == 5
    assert len(ids) == len(set(ids))
    assert all(source.kind.value == "rss" for source in registry.sources)
    assert all(source.locator.startswith("https://") for source in registry.sources)
