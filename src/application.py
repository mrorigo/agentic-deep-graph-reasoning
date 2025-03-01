import sys
import logging
import os

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.config import Settings
from clients.neo4j import Neo4jClient
from clients.openai import OpenAIClient
from services.knowledge_graph_generator import KnowledgeGraphGenerator
from services.embedder import Embedder

def main():
    """
    Main entry point
    """
    load_dotenv()

    # Instantiate settings once
    SETTINGS = Settings()
    SETTINGS.configure_logging(SETTINGS.log_level)

    logger = logging.getLogger(__name__)

    if len(sys.argv) < 3:
        print("Usage: python knowledge_graph_generation.py <prompt> <iterations>")
        sys.exit(1)

    initial_prompt = sys.argv[1]
    try:
        max_iterations = int(sys.argv[2])
        if max_iterations <= 0:
            raise ValueError("Iterations must be a positive integer.")
    except ValueError:
        print("Error: Iterations must be a positive integer.")
        sys.exit(1)

    # Initialize Clients
    openai_client = OpenAIClient(SETTINGS.think_tags, SETTINGS.reasoning_model_config, SETTINGS.entity_extraction_model_config)
    neo4j_client = Neo4jClient(SETTINGS.neo4j_uri, SETTINGS.neo4j_user, SETTINGS.neo4j_password)
    embedder = Embedder(SETTINGS.embedding_model_config)
    kg_generator = KnowledgeGraphGenerator(openai_client, neo4j_client, embedder)

    try:
        kg_generator.run_kg_generation_iterations(initial_prompt, max_iterations)
    except Exception as e:
        logger.exception("Unhandled exception during knowledge graph generation process.")
        print(f"An unexpected error occurred: {e}")
        sys.exit(2)
    finally:
        neo4j_client.close()
        logger.info("Application finished.")


if __name__ == "__main__":
    main()
