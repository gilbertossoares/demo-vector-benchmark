"""
03-load-ai-search.py
Carrega documentos com embeddings no Azure AI Search.
"""

import json
import os
import time
from pathlib import Path
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SearchIndex,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# --- Configuração ---
config_path = Path(__file__).parent.parent / "config.json"
with open(config_path) as f:
    config = json.load(f)

SEARCH_SERVICE_NAME = config["ai_search_name"]
SEARCH_ENDPOINT = f"https://{SEARCH_SERVICE_NAME}.search.windows.net"
INDEX_NAME = "vector-benchmark"
DATA_DIR = Path(__file__).parent.parent / "data"

def create_index(client: SearchIndexClient):
    """Cria índice vetorial no AI Search."""
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="category", type=SearchFieldDataType.String, filterable=True),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536,
            vector_search_profile_name="vector-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="hnsw-config"),
        ],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw-config",
            ),
        ],
    )

    index = SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
    )

    client.create_or_update_index(index)
    print(f"  ✓ Índice '{INDEX_NAME}' criado/atualizado")


def upload_documents(search_client: SearchClient, documents: list[dict]):
    """Faz upload dos documentos em batches."""
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        # Formatar para AI Search
        docs_batch = []
        for doc in batch:
            docs_batch.append({
                "id": doc["id"],
                "title": doc["title"],
                "content": doc["content"],
                "category": doc["category"],
                "embedding": doc["embedding"],
            })
        search_client.upload_documents(documents=docs_batch)
        print(f"  Batch {i//batch_size + 1}: {len(docs_batch)} documentos enviados")
        time.sleep(0.5)


def main():
    print("=" * 60)
    print(" CARREGANDO DADOS NO AZURE AI SEARCH")
    print("=" * 60)

    credential = DefaultAzureCredential()

    # Criar índice
    print("\n[1/2] Criando índice vetorial...")
    index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)
    create_index(index_client)

    # Carregar documentos
    print("\n[2/2] Carregando documentos...")
    with open(DATA_DIR / "documents.json", "r", encoding="utf-8") as f:
        documents = json.load(f)

    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=INDEX_NAME,
        credential=credential,
    )
    upload_documents(search_client, documents)

    print(f"\n✅ {len(documents)} documentos carregados no AI Search")
    print(f"   Endpoint: {SEARCH_ENDPOINT}")
    print(f"   Índice: {INDEX_NAME}")


if __name__ == "__main__":
    main()
