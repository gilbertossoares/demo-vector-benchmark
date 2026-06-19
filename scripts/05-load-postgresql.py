"""
05-load-postgresql.py
Carrega documentos com embeddings no Azure Database for PostgreSQL (pgvector).
"""

import json
import os
import time
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# --- Configuração ---
config_path = Path(__file__).parent.parent / "config.json"
with open(config_path) as f:
    config = json.load(f)

PG_HOST = f"{config['pg_name']}.postgres.database.azure.com"
PG_USER = os.getenv("AZURE_PG_ENTRA_USER", "")
PG_DATABASE = "postgres"
DATA_DIR = Path(__file__).parent.parent / "data"


def get_pg_access_token() -> str:
    credential = DefaultAzureCredential()
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
    return token.token


def setup_database(conn):
    """Cria extensão pgvector e tabela."""
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("DROP TABLE IF EXISTS documents;")
        cur.execute("""
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                title TEXT,
                content TEXT,
                category TEXT,
                embedding vector(1536)
            );
        """)
        conn.commit()
    print("  ✓ Extensão pgvector habilitada e tabela criada")


def create_index(conn):
    """Cria índice HNSW para busca vetorial."""
    with conn.cursor() as cur:
        print("  Criando índice HNSW (pode levar alguns segundos)...")
        cur.execute("""
            CREATE INDEX ON documents
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """)
        conn.commit()
    print("  ✓ Índice HNSW criado")


def upload_documents(conn, documents: list[dict]):
    """Insere documentos em batch."""
    with conn.cursor() as cur:
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            values = [
                (doc["id"], doc["title"], doc["content"],
                 doc["category"], str(doc["embedding"]))
                for doc in batch
            ]
            execute_values(
                cur,
                "INSERT INTO documents (id, title, content, category, embedding) VALUES %s",
                values,
            )
            conn.commit()
            print(f"  Batch {i//batch_size + 1}: {len(batch)} documentos inseridos")
    print("  ✓ Todos os documentos inseridos")


def main():
    print("=" * 60)
    print(" CARREGANDO DADOS NO POSTGRESQL (pgvector)")
    print("=" * 60)

    if not PG_USER:
        raise ValueError("Defina AZURE_PG_ENTRA_USER no .env para autenticação Entra ID do PostgreSQL.")

    pg_token = get_pg_access_token()

    conn = psycopg2.connect(
        host=PG_HOST,
        database=PG_DATABASE,
        user=PG_USER,
        password=pg_token,
        sslmode="require",
    )

    # Setup
    print("\n[1/3] Configurando banco de dados...")
    setup_database(conn)

    # Carregar documentos
    print("\n[2/3] Carregando documentos...")
    with open(DATA_DIR / "documents.json", "r", encoding="utf-8") as f:
        documents = json.load(f)
    upload_documents(conn, documents)

    # Criar índice
    print("\n[3/3] Criando índice vetorial HNSW...")
    create_index(conn)

    conn.close()

    print(f"\n✅ {len(documents)} documentos carregados no PostgreSQL")
    print(f"   Host: {PG_HOST}")
    print(f"   Database: {PG_DATABASE}")
    print(f"   Índice: HNSW (m=16, ef_construction=64)")


if __name__ == "__main__":
    main()
