"""
Knowledge Graph for CodeFlow Agent.

Manages the graph-based representation of code entities and their relationships,
enabling deep understanding of codebase structure and dependencies.
"""

import asyncio
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import networkx as nx

from ..models.entities import (
    CodeEntity,
    CodeEntityType,
    Relationship,
    RelationshipType,
)


class KnowledgeGraph:
    """
    In-memory knowledge graph for code entities and relationships.

    Uses NetworkX for graph operations and provides methods for
    adding entities, creating relationships, and querying the graph.
    """

    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self.entity_index: dict[UUID, CodeEntity] = {}
        self.file_index: dict[str, list[UUID]] = {}
        self.name_index: dict[str, list[UUID]] = {}

    def add_entity(self, entity: CodeEntity) -> None:
        """Add a code entity to the graph."""
        self.entity_index[entity.id] = entity
        self.graph.add_node(
            entity.id,
            entity_type=entity.entity_type.value,
            name=entity.name,
            file_path=entity.file_path,
            line_start=entity.line_start,
            line_end=entity.line_end,
            language=entity.language,
            metadata=entity.metadata,
        )

        # Update file index
        if entity.file_path not in self.file_index:
            self.file_index[entity.file_path] = []
        self.file_index[entity.file_path].append(entity.id)

        # Update name index
        if entity.name not in self.name_index:
            self.name_index[entity.name] = []
        self.name_index[entity.name].append(entity.id)

    def remove_entity(self, entity_id: UUID) -> bool:
        """Remove an entity and all its relationships from the graph."""
        if entity_id not in self.entity_index:
            return False

        # Remove from indices
        entity = self.entity_index[entity_id]
        if entity.file_path in self.file_index:
            self.file_index[entity.file_path] = [
                eid for eid in self.file_index[entity.file_path] if eid != entity_id
            ]
        if entity.name in self.name_index:
            self.name_index[entity.name] = [
                eid for eid in self.name_index[entity.name] if eid != entity_id
            ]

        # Remove from graph
        self.graph.remove_node(entity_id)
        del self.entity_index[entity_id]
        return True

    def add_relationship(self, relationship: Relationship) -> None:
        """Add a relationship between two entities."""
        if relationship.source_id not in self.graph or relationship.target_id not in self.graph:
            raise ValueError("Both source and target entities must exist in the graph")

        self.graph.add_edge(
            relationship.source_id,
            relationship.target_id,
            key=relationship.id,
            relationship_type=relationship.relationship_type.value,
            metadata=relationship.metadata,
        )

    def remove_relationship(self, relationship_id: UUID) -> bool:
        """Remove a relationship from the graph."""
        for u, v, key, data in self.graph.edges(keys=True, data=True):
            if data.get("key") == str(relationship_id) or key == relationship_id:
                self.graph.remove_edge(u, v, key)
                return True
        return False

    def get_entity(self, entity_id: UUID) -> Optional[CodeEntity]:
        """Get an entity by its ID."""
        return self.entity_index.get(entity_id)

    def get_entities_by_file(self, file_path: str) -> list[CodeEntity]:
        """Get all entities in a specific file."""
        entity_ids = self.file_index.get(file_path, [])
        return [self.entity_index[eid] for eid in entity_ids if eid in self.entity_index]

    def get_entities_by_name(self, name: str) -> list[CodeEntity]:
        """Get all entities with a specific name."""
        entity_ids = self.name_index.get(name, [])
        return [self.entity_index[eid] for eid in entity_ids if eid in self.entity_index]

    def get_entities_by_type(self, entity_type: CodeEntityType) -> list[CodeEntity]:
        """Get all entities of a specific type."""
        return [
            entity
            for entity in self.entity_index.values()
            if entity.entity_type == entity_type
        ]

    def get_related_entities(
        self,
        entity_id: UUID,
        relationship_type: Optional[RelationshipType] = None,
        direction: str = "both",
    ) -> list[tuple[RelationshipType, CodeEntity]]:
        """
        Get entities related to a specific entity.

        Args:
            entity_id: The ID of the entity to find relationships for
            relationship_type: Filter by specific relationship type (optional)
            direction: 'incoming', 'outgoing', or 'both'

        Returns:
            List of tuples containing relationship type and related entity
        """
        if entity_id not in self.graph:
            return []

        results = []

        if direction in ("outgoing", "both"):
            for neighbor, edge_data in self.graph[entity_id].items():
                for key, data in edge_data.items():
                    rel_type = RelationshipType(data["relationship_type"])
                    if relationship_type is None or rel_type == relationship_type:
                        if neighbor in self.entity_index:
                            results.append((rel_type, self.entity_index[neighbor]))

        if direction in ("incoming", "both"):
            for neighbor, edge_data in self.graph.pred[entity_id].items():
                for key, data in edge_data.items():
                    rel_type = RelationshipType(data["relationship_type"])
                    if relationship_type is None or rel_type == relationship_type:
                        if neighbor in self.entity_index:
                            results.append((rel_type, self.entity_index[neighbor]))

        return results

    def find_callers(self, function_id: UUID) -> list[CodeEntity]:
        """Find all functions/methods that call a specific function."""
        callers = []
        for rel_type, entity in self.get_related_entities(
            function_id, RelationshipType.CALLS, direction="incoming"
        ):
            if entity.entity_type in (CodeEntityType.FUNCTION, CodeEntityType.METHOD):
                callers.append(entity)
        return callers

    def find_callees(self, function_id: UUID) -> list[CodeEntity]:
        """Find all functions/methods called by a specific function."""
        callees = []
        for rel_type, entity in self.get_related_entities(
            function_id, RelationshipType.CALLS, direction="outgoing"
        ):
            if entity.entity_type in (CodeEntityType.FUNCTION, CodeEntityType.METHOD):
                callees.append(entity)
        return callees

    def find_dependencies(self, entity_id: UUID) -> list[CodeEntity]:
        """Find all entities that an entity depends on."""
        deps = []
        for rel_type, entity in self.get_related_entities(
            entity_id, RelationshipType.DEPENDS_ON, direction="outgoing"
        ):
            deps.append(entity)
        return deps

    def find_dependents(self, entity_id: UUID) -> list[CodeEntity]:
        """Find all entities that depend on a specific entity."""
        dependents = []
        for rel_type, entity in self.get_related_entities(
            entity_id, RelationshipType.DEPENDS_ON, direction="incoming"
        ):
            dependents.append(entity)
        return dependents

    def get_import_chain(self, entity_id: UUID) -> list[CodeEntity]:
        """Get the full import chain for an entity."""
        chain = []
        visited = set()
        queue = [entity_id]

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            for rel_type, entity in self.get_related_entities(
                current_id, RelationshipType.IMPORTS, direction="outgoing"
            ):
                chain.append(entity)
                queue.append(entity.id)

        return chain

    def find_cycles(self) -> list[list[UUID]]:
        """Find all cycles in the dependency graph."""
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return cycles
        except nx.NetworkXError:
            return []

    def get_entity_depth(self, entity_id: UUID) -> int:
        """Calculate the depth of an entity in the dependency graph."""
        if entity_id not in self.graph:
            return 0

        try:
            # Find longest path to any root node
            lengths = nx.single_source_shortest_path_length(
                self.graph.reverse(), entity_id
            )
            return max(lengths.values()) if lengths else 0
        except nx.NetworkXError:
            return 0

    def get_subgraph_for_file(self, file_path: str) -> "KnowledgeGraph":
        """Create a subgraph containing only entities from a specific file."""
        entity_ids = self.file_index.get(file_path, [])
        subgraph = KnowledgeGraph()

        for eid in entity_ids:
            if eid in self.entity_index:
                subgraph.add_entity(self.entity_index[eid])

        # Add relationships within the file
        for u, v, data in self.graph.edges(data=True):
            if u in entity_ids and v in entity_ids:
                rel = Relationship(
                    source_id=u,
                    target_id=v,
                    relationship_type=RelationshipType(data["relationship_type"]),
                    metadata=data.get("metadata", {}),
                )
                subgraph.add_relationship(rel)

        return subgraph

    def get_impact_analysis(self, entity_id: UUID) -> dict[str, Any]:
        """
        Analyze the impact of changing a specific entity.

        Returns a dictionary containing:
        - direct_dependents: Entities directly depending on this entity
        - transitive_dependents: All entities transitively depending
        - risk_score: Calculated risk score (0-100)
        - affected_files: Set of files that would be affected
        """
        direct_deps = self.find_dependents(entity_id)
        all_deps = set()
        queue = [d.id for d in direct_deps]
        visited = {entity_id}

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            all_deps.add(current_id)

            more_deps = self.find_dependents(current_id)
            queue.extend([d.id for d in more_deps])

        affected_files = set()
        for dep_id in all_deps:
            if dep_id in self.entity_index:
                affected_files.add(self.entity_index[dep_id].file_path)

        # Calculate risk score
        risk_score = min(100, len(all_deps) * 10 + len(affected_files) * 5)

        return {
            "direct_dependents": [self.entity_index[d.id] for d in direct_deps],
            "transitive_dependents": [self.entity_index[did] for did in all_deps],
            "risk_score": risk_score,
            "affected_files": affected_files,
        }

    def to_dict(self) -> dict[str, Any]:
        """Export the graph to a dictionary format."""
        nodes = []
        for node_id, data in self.graph.nodes(data=True):
            node_data = data.copy()
            node_data["id"] = str(node_id)
            nodes.append(node_data)

        edges = []
        for u, v, key, data in self.graph.edges(keys=True, data=True):
            edge_data = data.copy()
            edge_data["source"] = str(u)
            edge_data["target"] = str(v)
            edge_data["key"] = str(key)
            edges.append(edge_data)

        return {"nodes": nodes, "edges": edges}

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the graph."""
        return {
            "total_entities": len(self.entity_index),
            "total_relationships": self.graph.number_of_edges(),
            "total_files": len(self.file_index),
            "entity_types": {
                et.value: len(self.get_entities_by_type(et))
                for et in CodeEntityType
            },
            "avg_degree": (
                sum(dict(self.graph.degree()).values()) / len(self.graph.nodes())
                if self.graph.nodes()
                else 0
            ),
            "has_cycles": len(self.find_cycles()) > 0,
        }
