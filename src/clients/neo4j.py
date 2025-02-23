import logging
from typing import List, Optional

from neo4j import GraphDatabase, Driver

from core.models import Entity, Relationship

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Client for interacting with the Neo4j database."""

    def __init__(self, uri: str, user: str, password: str):
        """Initializes the Neo4j client with connection details."""
        self.uri = uri
        self.user = user
        self.password = password
        self._driver: Driver | None = None
        try:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.verify_connection()
            logger.info("Successfully connected to Neo4j.")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            if self._driver:
                self._driver.close()
            raise

    def verify_connection(self):
        """Verifies the connection to Neo4j by running a simple query."""
        try:
            with self._driver.session() as session:
                session.run("RETURN 1").consume()  # Simple query to check connection
        except Exception as e:
            logger.error(f"Failed to verify connection to Neo4j: {e}")
            raise

    def close(self):
        """Closes the Neo4j driver connection."""
        if self._driver:
            self._driver.close()
            logger.info("Neo4j driver closed.")
        else:
            logger.warning("Neo4j driver already closed or not initialized.")

    def query_node_names(self) -> List[str]:
        """Queries Neo4j for all node names."""

        def _query(tx):
            result = tx.run("MATCH (n) RETURN n.name AS name")
            return [record["name"] for record in result]

        try:
            with self._driver.session() as session:
                names = session.execute_read(_query)
                logger.info(f"Fetched {len(names)} node names from Neo4j.")
                logger.debug(f"Node names: {names}")  # Use debug level for listing names
                return names
        except Exception as e:
            logger.error(f"Error querying node names from Neo4j: {e}")
            return []

    def create_node(self, entity: Entity) -> Optional[str]:
        """Creates a node in Neo4j for the given entity, handling duplicates and label merging."""

        def _create_node_tx(tx, entity_data: Entity):
            category_labels = ":".join([f"`{category}`" for category in entity_data.category]) if entity_data.category else ""
            query = "MATCH (n {name: $name}) RETURN elementId(n) AS existing_node_id"
            result = tx.run(query, name=entity_data.name).single()

            if result:
                node_id = result["existing_node_id"]
                logger.info(f"Node with name '{entity_data.name}' already exists (ID: {node_id}). Merging labels.")
                merge_labels_query = f"MATCH (n) WHERE elementId(n) = $node_id SET n:{category_labels}"
                tx.run(merge_labels_query, node_id=node_id)
                return node_id
            else:
                create_query = (
                    f"CREATE (n:{category_labels} {{name: $name, description: $description}}) RETURN elementId(n) AS node_id"
                )
                result = tx.run(create_query, name=entity_data.name, description=entity_data.description).single()
                node_id = result["node_id"]
                logger.info(f"Created node for '{entity_data.name}' with Neo4j ID: {node_id}")
                return node_id

        try:
            with self._driver.session() as session:
                return session.execute_write(_create_node_tx, entity)
        except Exception as e:
            logger.error(f"Error creating Neo4j node for entity '{entity.name}': {e}")
            return None

    def create_relationship(self, relationship: Relationship) -> None:
        """Creates a relationship in Neo4j, merging duplicates."""

        def _create_relationship_tx(tx, relationship_data: Relationship):
            if not isinstance(relationship_data.attributes, dict):
                relationship_data.attributes = {"stored_data": relationship_data.attributes}  # Fallback for non-dict attributes

            # Format the relationship type directly into the query
            rel_type = relationship_data.relation_type.replace("`", "").replace('"', "").replace("'", "")
            query = f"""
                MATCH (source) WHERE source.name = $source_entity_name
                MATCH (target) WHERE target.name = $target_entity_name
                MERGE (source)-[r:`{rel_type}`]->(target)
                SET r += $attributes
            """
            logger.info(f"Executing Neo4j query: {query}")
            tx.run(
                query,
                source_entity_name=relationship_data.source_entity_name,
                target_entity_name=relationship_data.target_entity_name,
                attributes=relationship_data.attributes,
            )
            logger.info(
                f"Created/merged relationship: {relationship_data.relation_type} between entities {relationship_data.source_entity_name} and {relationship_data.target_entity_name}"
            )

        try:
            with self._driver.session() as session:
                session.execute_write(_create_relationship_tx, relationship)
        except Exception as e:
            logger.error(f"Error creating Neo4j relationship: {e}")

    def find_longest_paths(self) -> List[str]:
        """Finds the longest path in the Neo4j graph and returns a list of node IDs."""
        def _find_longest_path_tx(tx):
            query = """
            MATCH p = (n)-[*]->(m)
            ORDER BY length(p) DESC
            LIMIT 3
            RETURN [node in nodes(p) | node.name] AS nodeNames, length(p) AS pathLength
            """
            logging.info(f"query: {query}")
            result = tx.run(query)
            results = []
            for record in result:
                results.append(record["nodeNames"])
            return results

        try:
            with self._driver.session() as session:
                print("Running query..")
                node_ids = session.execute_read(_find_longest_path_tx)
                if node_ids:
                    logger.info(f"Longest path found with {len(node_ids)} nodes.")
                    logger.debug(f"Node IDs along the longest path: {node_ids}")
                    return node_ids
                else:
                    logger.warning("No path found in the graph.")
                    return None
        except Exception as e:
            logger.error(f"Error finding the longest path in Neo4j: {e}")
            return None
