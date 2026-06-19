"""
07-load-azuresql.py
Carrega documentos com embeddings no Azure SQL Database (vector nativo - Preview).
"""

import json
import os
import time
import struct
from pathlib import Path
import pyodbc
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# --- Configuração ---
config_path = Path(__file__).parent.parent / "config.json"
with open(config_path) as f:
    config = json.load(f)

SQL_SERVER = f"{config['sql_server_name']}.database.windows.net"
SQL_DATABASE = config["sql_db_name"]
DATA_DIR = Path(__file__).parent.parent / "data"

CONNECTION_STRING = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={SQL_SERVER};"
    f"DATABASE={SQL_DATABASE};"
    f"Encrypt=yes;TrustServerCertificate=no;"
)

SQL_COPT_SS_ACCESS_TOKEN = 1256


def get_sql_access_token_struct() -> bytes:
    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default").token
    token_bytes = token.encode("utf-16-le")
    return struct.pack("<I", len(token_bytes)) + token_bytes


def setup_database(conn):
    """Cria tabela com coluna vector."""
    cursor = conn.cursor()
    cursor.execute("""
        IF OBJECT_ID('documents', 'U') IS NOT NULL
            DROP TABLE documents;
    """)
    cursor.execute("""
        CREATE TABLE documents (
            id NVARCHAR(50) PRIMARY KEY,
            title NVARCHAR(500),
            content NVARCHAR(MAX),
            category NVARCHAR(100),
            embedding VECTOR(1536)
        );
    """)
    conn.commit()
    print("  ✓ Tabela 'documents' criada com coluna VECTOR(1536)")


def create_index(conn):
    """Cria índice vetorial (DiskANN - Preview)."""
    previous_autocommit = conn.autocommit
    try:
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("""
            CREATE VECTOR INDEX idx_documents_embedding
            ON documents(embedding)
            WITH (metric = 'cosine', type = 'diskann');
        """)
        print("  ✓ Índice vetorial DiskANN criado")
    except pyodbc.Error as e:
        print(f"  ⚠️  Índice DiskANN não disponível (Preview): {e}")
        print("  → Queries usarão busca exata (sem índice ANN)")
    finally:
        conn.autocommit = previous_autocommit


def upload_documents(conn, documents: list[dict]):
    """Insere documentos em batch."""
    cursor = conn.cursor()
    batch_size = 50
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        for doc in batch:
            embedding_str = json.dumps(doc["embedding"])
            cursor.execute(
                """
                INSERT INTO documents (id, title, content, category, embedding)
                VALUES (?, ?, ?, ?, CAST(CONVERT(VARCHAR(MAX), ?) AS VECTOR(1536)))
                """,
                doc["id"], doc["title"], doc["content"],
                doc["category"], embedding_str,
            )
        conn.commit()
        print(f"  Batch {i//batch_size + 1}: {len(batch)} documentos inseridos")

    print(f"  ✓ Todos os {len(documents)} documentos inseridos")


def main():
    print("=" * 60)
    print(" CARREGANDO DADOS NO AZURE SQL DATABASE (Vector Preview)")
    print("=" * 60)

    token_struct = get_sql_access_token_struct()
    conn = pyodbc.connect(CONNECTION_STRING, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})

    # Setup
    print("\n[1/3] Configurando banco de dados...")
    setup_database(conn)

    # Carregar documentos
    print("\n[2/3] Carregando documentos...")
    with open(DATA_DIR / "documents.json", "r", encoding="utf-8") as f:
        documents = json.load(f)
    upload_documents(conn, documents)

    # Criar índice
    print("\n[3/3] Criando índice vetorial...")
    create_index(conn)

    conn.close()

    print(f"\n✅ {len(documents)} documentos carregados no Azure SQL")
    print(f"   Server: {SQL_SERVER}")
    print(f"   Database: {SQL_DATABASE}")


if __name__ == "__main__":
    main()
