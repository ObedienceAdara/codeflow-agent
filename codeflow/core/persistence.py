"""
Persistence Layer for CodeFlow Agent.

Provides a pluggable storage backend abstraction for workflow state,
agent state, and knowledge graph data. Supports in-memory (default)
and file-based JSON persistence, with a ChromaDB interface ready
for Phase 1 (Living Memory) integration.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StateBackend(ABC):
    """Abstract base class for state persistence backends."""

    @abstractmethod
    async def save(self, key: str, data: dict[str, Any]) -> None:
        """Persist state by key."""
        ...

    @abstractmethod
    async def load(self, key: str) -> Optional[dict[str, Any]]:
        """Load state by key, or None if not found."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete state by key."""
        ...

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys, optionally filtered by prefix."""
        ...


class MemoryBackend(StateBackend):
    """
    In-memory backend. Default for development/testing.
    State is lost on process restart.
    """

    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {}

    async def save(self, key: str, data: dict[str, Any]) -> None:
        self._store[key] = data

    async def load(self, key: str) -> Optional[dict[str, Any]]:
        return self._store.get(key)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def list_keys(self, prefix: str = "") -> list[str]:
        return [k for k in self._store if k.startswith(prefix)]


class FileBackend(StateBackend):
    """
    File-based JSON persistence backend.
    Stores state as JSON files on disk for durability.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        """Convert a dotted key to a file path."""
        safe_key = key.replace("/", "_").replace(" ", "_")
        return self.data_dir / f"{safe_key}.json"

    async def save(self, key: str, data: dict[str, Any]) -> None:
        path = self._key_to_path(key)
        path.write_text(
            json.dumps(data, default=str, indent=2),
            encoding="utf-8",
        )

    async def load(self, key: str) -> Optional[dict[str, Any]]:
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load state for {key}: {e}")
            return None

    async def delete(self, key: str) -> None:
        path = self._key_to_path(key)
        if path.exists():
            path.unlink()

    async def list_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        prefix_safe = prefix.replace("/", "_").replace(" ", "_")
        for path in self.data_dir.glob(f"{prefix_safe}*.json"):
            keys.append(path.stem)
        return keys


class VectorIndex:
    """
    Vector embedding index for semantic code search.

    Phase 1 (Living Memory) foundation. Wraps ChromaDB when available,
    falls back to in-memory storage.
    """

    def __init__(self, chroma_path: Optional[str] = None, collection_name: str = "codeflow"):
        self.collection_name = collection_name
        self._client: Any = None
        self._collection: Any = None
        self._initialized = False

        if chroma_path:
            self._chroma_path = chroma_path
        else:
            self._chroma_path = None

    def _ensure_client(self) -> Any:
        """Lazy-initialize the ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                if self._chroma_path:
                    self._client = chromadb.PersistentClient(path=self._chroma_path)
                else:
                    self._client = chromadb.Client()
                self._collection = self._client.get_or_create_collection(self.collection_name)
                self._initialized = True
                logger.info(f"VectorIndex initialized with ChromaDB: {self.collection_name}")
            except ImportError:
                logger.warning("ChromaDB not installed. VectorIndex disabled.")
                self._initialized = False
            except Exception as e:
                logger.warning(f"ChromaDB initialization failed: {e}. VectorIndex disabled.")
                self._initialized = False
        return self._client

    async def add(self, entity_id: str, content: str, metadata: Optional[dict] = None) -> None:
        """
        Add a code entity to the vector index.

        Args:
            entity_id: Unique identifier for the entity
            content: Code content to embed
            metadata: Additional metadata (file_path, entity_type, etc.)
        """
        client = self._ensure_client()
        if not self._initialized:
            return

        try:
            meta = metadata or {}
            meta["entity_id"] = entity_id
            meta["indexed_at"] = datetime.now(UTC).isoformat()

            self._collection.add(
                documents=[content],
                ids=[entity_id],
                metadatas=[meta],
            )
        except Exception as e:
            logger.warning(f"Failed to add entity {entity_id} to vector index: {e}")

    async def search(
        self, query: str, n_results: int = 10, filters: Optional[dict] = None
    ) -> list[dict[str, Any]]:
        """
        Semantic search for code entities.

        Args:
            query: Natural language query
            n_results: Maximum number of results
            filters: Optional metadata filters

        Returns:
            List of matching entities with distance scores
        """
        client = self._ensure_client()
        if not self._initialized:
            return []

        try:
            kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": n_results,
            }
            if filters:
                kwargs["where"] = filters

            results = self._collection.query(**kwargs)

            matches = []
            if results.get("ids") and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    match = {
                        "entity_id": doc_id,
                        "content": results.get("documents", [[]])[0][i] if results.get("documents") else "",
                        "metadata": results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {},
                        "distance": results.get("distances", [[]])[0][i] if results.get("distances") else None,
                    }
                    matches.append(match)

            return matches
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []

    async def count(self) -> int:
        """Return the number of indexed entities."""
        if not self._initialized:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    @property
    def is_available(self) -> bool:
        """Whether the vector index is initialized and functional."""
        return self._initialized


class StateManager:
    """
    Manages persistence for the entire orchestrator.

    Coordinates workflow state, agent state, and knowledge graph
    persistence across sessions.
    """

    def __init__(self, backend: Optional[StateBackend] = None):
        self.backend = backend or MemoryBackend()

    async def save_workflow_state(self, state: dict[str, Any]) -> None:
        """Save complete workflow state."""
        await self.backend.save("workflow_state", state)

    async def load_workflow_state(self) -> Optional[dict[str, Any]]:
        """Load complete workflow state."""
        return await self.backend.load("workflow_state")

    async def save_agent_state(self, agent_type: str, state: dict[str, Any]) -> None:
        """Save agent state."""
        await self.backend.save(f"agent_{agent_type}", state)

    async def load_agent_state(self, agent_type: str) -> Optional[dict[str, Any]]:
        """Load agent state."""
        return await self.backend.load(f"agent_{agent_type}")

    async def save_knowledge_graph(self, graph_data: dict[str, Any]) -> None:
        """Save knowledge graph data."""
        await self.backend.save("knowledge_graph", graph_data)

    async def load_knowledge_graph(self) -> Optional[dict[str, Any]]:
        """Load knowledge graph data."""
        return await self.backend.load("knowledge_graph")

    async def clear(self) -> None:
        """Clear all persisted state."""
        keys = await self.backend.list_keys()
        for key in keys:
            await self.backend.delete(key)
