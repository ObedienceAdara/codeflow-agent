"""Tests for KnowledgeGraph."""

import pytest
from uuid import uuid4

from codeflow.core.knowledge_graph import KnowledgeGraph
from codeflow.models.entities import (
    CodeEntity,
    CodeEntityType,
    Relationship,
    RelationshipType,
)


class TestKnowledgeGraphEntities:
    """Test entity management in KnowledgeGraph."""

    def test_add_entity(self, knowledge_graph, sample_code_entity):
        """Test adding an entity to the graph."""
        knowledge_graph.add_entity(sample_code_entity)

        assert sample_code_entity.id in knowledge_graph.entity_index
        assert sample_code_entity.id in knowledge_graph.graph.nodes

    def test_add_entity_updates_file_index(self, knowledge_graph):
        """Test that file index is updated."""
        entity = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="test_func",
            file_path="test.py",
            line_start=1,
            line_end=5,
            content="def test_func(): pass",
        )

        knowledge_graph.add_entity(entity)

        assert "test.py" in knowledge_graph.file_index
        assert entity.id in knowledge_graph.file_index["test.py"]

    def test_add_entity_updates_name_index(self, knowledge_graph):
        """Test that name index is updated."""
        entity = CodeEntity(
            entity_type=CodeEntityType.CLASS,
            name="UniqueClass",
            file_path="test.py",
            line_start=1,
            line_end=10,
            content="class UniqueClass: pass",
        )

        knowledge_graph.add_entity(entity)

        assert "UniqueClass" in knowledge_graph.name_index
        assert entity.id in knowledge_graph.name_index["UniqueClass"]

    def test_remove_entity(self, knowledge_graph, sample_code_entity):
        """Test removing an entity."""
        knowledge_graph.add_entity(sample_code_entity)
        result = knowledge_graph.remove_entity(sample_code_entity.id)

        assert result is True
        assert sample_code_entity.id not in knowledge_graph.entity_index
        assert sample_code_entity.id not in knowledge_graph.graph.nodes

    def test_remove_nonexistent_entity(self, knowledge_graph):
        """Test removing an entity that doesn't exist."""
        fake_id = uuid4()
        result = knowledge_graph.remove_entity(fake_id)

        assert result is False

    def test_get_entity(self, knowledge_graph, sample_code_entity):
        """Test retrieving an entity by ID."""
        knowledge_graph.add_entity(sample_code_entity)
        retrieved = knowledge_graph.get_entity(sample_code_entity.id)

        assert retrieved is not None
        assert retrieved.id == sample_code_entity.id
        assert retrieved.name == sample_code_entity.name

    def test_get_entities_by_file(self, knowledge_graph):
        """Test querying entities by file path."""
        e1 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="func1",
            file_path="file_a.py",
            line_start=1,
            line_end=3,
        )
        e2 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="func2",
            file_path="file_a.py",
            line_start=5,
            line_end=7,
        )
        e3 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="func3",
            file_path="file_b.py",
            line_start=1,
            line_end=3,
        )

        knowledge_graph.add_entity(e1)
        knowledge_graph.add_entity(e2)
        knowledge_graph.add_entity(e3)

        file_a_entities = knowledge_graph.get_entities_by_file("file_a.py")

        assert len(file_a_entities) == 2
        assert all(e.file_path == "file_a.py" for e in file_a_entities)

    def test_get_entities_by_name(self, knowledge_graph):
        """Test querying entities by name."""
        e1 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="shared_name",
            file_path="file_a.py",
            line_start=1,
            line_end=3,
        )
        e2 = CodeEntity(
            entity_type=CodeEntityType.CLASS,
            name="shared_name",
            file_path="file_b.py",
            line_start=1,
            line_end=10,
        )

        knowledge_graph.add_entity(e1)
        knowledge_graph.add_entity(e2)

        results = knowledge_graph.get_entities_by_name("shared_name")

        assert len(results) == 2

    def test_get_entities_by_type(self, knowledge_graph):
        """Test querying entities by type."""
        e1 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="func1",
            file_path="test.py",
            line_start=1,
            line_end=3,
        )
        e2 = CodeEntity(
            entity_type=CodeEntityType.CLASS,
            name="Class1",
            file_path="test.py",
            line_start=5,
            line_end=15,
        )
        e3 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="func2",
            file_path="test.py",
            line_start=17,
            line_end=20,
        )

        knowledge_graph.add_entity(e1)
        knowledge_graph.add_entity(e2)
        knowledge_graph.add_entity(e3)

        functions = knowledge_graph.get_entities_by_type(CodeEntityType.FUNCTION)

        assert len(functions) == 2


class TestKnowledgeGraphRelationships:
    """Test relationship management."""

    def test_add_relationship(self, knowledge_graph):
        """Test adding a relationship between two entities."""
        e1 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="caller",
            file_path="test.py",
            line_start=1,
            line_end=5,
        )
        e2 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="callee",
            file_path="test.py",
            line_start=7,
            line_end=10,
        )

        knowledge_graph.add_entity(e1)
        knowledge_graph.add_entity(e2)

        rel = Relationship(
            source_id=e1.id,
            target_id=e2.id,
            relationship_type=RelationshipType.CALLS,
        )
        knowledge_graph.add_relationship(rel)

        related = knowledge_graph.get_related_entities(e1.id)
        assert len(related) == 1
        assert related[0][0] == RelationshipType.CALLS
        assert related[0][1].id == e2.id

    def test_add_relationship_missing_entity(self, knowledge_graph):
        """Test adding relationship when one entity doesn't exist."""
        rel = Relationship(
            source_id=uuid4(),
            target_id=uuid4(),
            relationship_type=RelationshipType.CALLS,
        )

        with pytest.raises(ValueError, match="Both source and target"):
            knowledge_graph.add_relationship(rel)

    def test_remove_relationship(self, knowledge_graph):
        """Test removing a relationship."""
        e1 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="f1",
            file_path="test.py",
            line_start=1,
            line_end=3,
        )
        e2 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="f2",
            file_path="test.py",
            line_start=5,
            line_end=7,
        )

        knowledge_graph.add_entity(e1)
        knowledge_graph.add_entity(e2)

        rel = Relationship(
            source_id=e1.id,
            target_id=e2.id,
            relationship_type=RelationshipType.CALLS,
        )
        knowledge_graph.add_relationship(rel)

        result = knowledge_graph.remove_relationship(rel.id)
        assert result is True

        # Relationship should be gone
        related = knowledge_graph.get_related_entities(e1.id)
        assert len(related) == 0


class TestKnowledgeGraphTraversals:
    """Test graph traversal methods."""

    def test_find_callers(self, knowledge_graph):
        """Test finding functions that call another."""
        caller = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="caller",
            file_path="test.py",
            line_start=1,
            line_end=5,
        )
        callee = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="callee",
            file_path="test.py",
            line_start=7,
            line_end=10,
        )

        knowledge_graph.add_entity(caller)
        knowledge_graph.add_entity(callee)

        rel = Relationship(
            source_id=caller.id,
            target_id=callee.id,
            relationship_type=RelationshipType.CALLS,
        )
        knowledge_graph.add_relationship(rel)

        callers = knowledge_graph.find_callers(callee.id)

        assert len(callers) == 1
        assert callers[0].name == "caller"

    def test_find_callees(self, knowledge_graph):
        """Test finding functions called by another."""
        caller = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="caller",
            file_path="test.py",
            line_start=1,
            line_end=5,
        )
        callee = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="callee",
            file_path="test.py",
            line_start=7,
            line_end=10,
        )

        knowledge_graph.add_entity(caller)
        knowledge_graph.add_entity(callee)

        rel = Relationship(
            source_id=caller.id,
            target_id=callee.id,
            relationship_type=RelationshipType.CALLS,
        )
        knowledge_graph.add_relationship(rel)

        callees = knowledge_graph.find_callees(caller.id)

        assert len(callees) == 1
        assert callees[0].name == "callee"

    def test_find_dependencies(self, knowledge_graph):
        """Test finding dependencies of an entity."""
        dependent = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="dependent",
            file_path="test.py",
            line_start=1,
            line_end=5,
        )
        dependency = CodeEntity(
            entity_type=CodeEntityType.CLASS,
            name="Dependency",
            file_path="test.py",
            line_start=7,
            line_end=20,
        )

        knowledge_graph.add_entity(dependent)
        knowledge_graph.add_entity(dependency)

        rel = Relationship(
            source_id=dependent.id,
            target_id=dependency.id,
            relationship_type=RelationshipType.DEPENDS_ON,
        )
        knowledge_graph.add_relationship(rel)

        deps = knowledge_graph.find_dependencies(dependent.id)

        assert len(deps) == 1
        assert deps[0].name == "Dependency"

    def test_find_dependents(self, knowledge_graph):
        """Test finding entities that depend on another."""
        dependent = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="dependent",
            file_path="test.py",
            line_start=1,
            line_end=5,
        )
        dependency = CodeEntity(
            entity_type=CodeEntityType.CLASS,
            name="Dependency",
            file_path="test.py",
            line_start=7,
            line_end=20,
        )

        knowledge_graph.add_entity(dependent)
        knowledge_graph.add_entity(dependency)

        rel = Relationship(
            source_id=dependent.id,
            target_id=dependency.id,
            relationship_type=RelationshipType.DEPENDS_ON,
        )
        knowledge_graph.add_relationship(rel)

        dependents = knowledge_graph.find_dependents(dependency.id)

        assert len(dependents) == 1
        assert dependents[0].name == "dependent"


class TestKnowledgeGraphAnalysis:
    """Test graph analysis methods."""

    def test_get_statistics_empty(self, knowledge_graph):
        """Test statistics on empty graph."""
        stats = knowledge_graph.get_statistics()

        assert stats["total_entities"] == 0
        assert stats["total_relationships"] == 0
        assert stats["total_files"] == 0
        assert stats["has_cycles"] is False

    def test_get_statistics_with_data(self, knowledge_graph):
        """Test statistics with entities and relationships."""
        e1 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="f1",
            file_path="test.py",
            line_start=1,
            line_end=5,
        )
        e2 = CodeEntity(
            entity_type=CodeEntityType.CLASS,
            name="C1",
            file_path="test.py",
            line_start=7,
            line_end=20,
        )

        knowledge_graph.add_entity(e1)
        knowledge_graph.add_entity(e2)

        rel = Relationship(
            source_id=e1.id,
            target_id=e2.id,
            relationship_type=RelationshipType.CALLS,
        )
        knowledge_graph.add_relationship(rel)

        stats = knowledge_graph.get_statistics()

        assert stats["total_entities"] == 2
        assert stats["total_relationships"] == 1
        assert stats["total_files"] == 1
        assert stats["entity_types"]["function"] == 1
        assert stats["entity_types"]["class"] == 1

    def test_get_impact_analysis(self, knowledge_graph):
        """Test impact analysis for an entity."""
        base = CodeEntity(
            entity_type=CodeEntityType.CLASS,
            name="BaseClass",
            file_path="base.py",
            line_start=1,
            line_end=20,
        )
        user1 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="func1",
            file_path="user.py",
            line_start=1,
            line_end=5,
        )
        user2 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="func2",
            file_path="user2.py",
            line_start=1,
            line_end=5,
        )

        knowledge_graph.add_entity(base)
        knowledge_graph.add_entity(user1)
        knowledge_graph.add_entity(user2)

        for user in [user1, user2]:
            rel = Relationship(
                source_id=user.id,
                target_id=base.id,
                relationship_type=RelationshipType.DEPENDS_ON,
            )
            knowledge_graph.add_relationship(rel)

        impact = knowledge_graph.get_impact_analysis(base.id)

        assert "direct_dependents" in impact
        assert "transitive_dependents" in impact
        assert "risk_score" in impact
        assert "affected_files" in impact
        assert len(impact["direct_dependents"]) == 2

    def test_get_subgraph_for_file(self, knowledge_graph):
        """Test extracting a subgraph for a specific file."""
        e1 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="f1",
            file_path="test.py",
            line_start=1,
            line_end=5,
        )
        e2 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="f2",
            file_path="test.py",
            line_start=7,
            line_end=10,
        )

        knowledge_graph.add_entity(e1)
        knowledge_graph.add_entity(e2)

        rel = Relationship(
            source_id=e1.id,
            target_id=e2.id,
            relationship_type=RelationshipType.CALLS,
        )
        knowledge_graph.add_relationship(rel)

        subgraph = knowledge_graph.get_subgraph_for_file("test.py")

        assert subgraph.graph.number_of_nodes() == 2
        assert subgraph.graph.number_of_edges() == 1

    def test_find_cycles(self, knowledge_graph):
        """Test cycle detection."""
        e1 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="f1",
            file_path="test.py",
            line_start=1,
            line_end=5,
        )
        e2 = CodeEntity(
            entity_type=CodeEntityType.FUNCTION,
            name="f2",
            file_path="test.py",
            line_start=7,
            line_end=10,
        )

        knowledge_graph.add_entity(e1)
        knowledge_graph.add_entity(e2)

        # Create cycle: e1 -> e2 -> e1
        r1 = Relationship(
            source_id=e1.id,
            target_id=e2.id,
            relationship_type=RelationshipType.CALLS,
        )
        r2 = Relationship(
            source_id=e2.id,
            target_id=e1.id,
            relationship_type=RelationshipType.CALLS,
        )
        knowledge_graph.add_relationship(r1)
        knowledge_graph.add_relationship(r2)

        cycles = knowledge_graph.find_cycles()
        assert len(cycles) > 0

    def test_to_dict(self, knowledge_graph, sample_code_entity):
        """Test graph serialization."""
        knowledge_graph.add_entity(sample_code_entity)

        data = knowledge_graph.to_dict()

        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 1
