"""A SQLite projection of the world, so retrieval is a real query layer.

`WorldState` remains the source of truth. Nothing here writes into `data/`, and
`DatasetStore` refuses a path inside the shipped dataset.
"""

from crewops.store.projection import SCHEMA, DatasetStore, open_store

__all__ = ["SCHEMA", "DatasetStore", "open_store"]
