"""
04-load-cosmosdb.py
Carrega documentos com embeddings no Azure Cosmos DB for NoSQL.
"""

import json
import os
import time
from pathlib import Path
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# --- Configuração ---
config_path = Path(__file__).parent.parent / "config.json"
with open(config_path) as f:
    config = json.load(f)

COSMOS_ACCOUNT = config["cosmos_name"]
DATABASE_NAME = "vectordb"
CONTAINER_NAME = "documents"
DATA_DIR = Path(__file__).parent.parent / "data"

COSMOS_ENDPOINT = f"https://{COSMOS_ACCOUNT}.documents.azure.com:443/"


def upload_documents(container, documents: list[dict]):
    """Insere documentos no container Cosmos DB."""
    for i, doc in enumerate(documents):
        item = {
            "id": doc["id"],
            "title": doc["title"],
            "content": doc["content"],
            "category": doc["category"],
            "embedding": doc["embedding"],
            "metadata": doc.get("metadata", {}),
        }
        container.upsert_item(item)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(documents)} documentos inseridos...")
            time.sleep(0.2)


def main():
    print("=" * 60)
    print(" CARREGANDO DADOS NO AZURE COSMOS DB (NoSQL)")
    print("=" * 60)

    credential = DefaultAzureCredential()
    client = CosmosClient(COSMOS_ENDPOINT, credential=credential)
    database = client.get_database_client(DATABASE_NAME)
    container = database.get_container_client(CONTAINER_NAME)

    # Carregar documentos
    print("\nCarregando documentos...")
    with open(DATA_DIR / "documents.json", "r", encoding="utf-8") as f:
        documents = json.load(f)

    upload_documents(container, documents)

    print(f"\n✅ {len(documents)} documentos carregados no Cosmos DB")
    print(f"   Account: {COSMOS_ACCOUNT}")
    print(f"   Database: {DATABASE_NAME}")
    print(f"   Container: {CONTAINER_NAME}")


if __name__ == "__main__":
    main()
