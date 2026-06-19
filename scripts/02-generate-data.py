"""
02-generate-data.py
Gera dataset padronizado com embeddings para o benchmark.
Usa Azure OpenAI text-embedding-3-small (1536 dims).
"""

import json
import os
import time
import numpy as np
from pathlib import Path
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

load_dotenv()

# --- Configuração ---
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
NUM_DOCUMENTS = 1000
EMBEDDING_DIMS = 1536
BATCH_SIZE = 100
DATA_DIR = Path(__file__).parent.parent / "data"

# --- Textos de exemplo (corpus diversificado para benchmark) ---
CATEGORIES = [
    "tecnologia", "saude", "financas", "educacao", "ciencia",
    "esportes", "cultura", "meio-ambiente", "politica", "negocios"
]

TEMPLATES = [
    "A importância da {topic} no contexto atual do Brasil e como ela impacta a sociedade moderna.",
    "Tendências emergentes em {topic}: análise de dados e perspectivas para os próximos anos.",
    "Como a inteligência artificial está transformando o setor de {topic} no mercado brasileiro.",
    "Estudo de caso: implementação de soluções inovadoras em {topic} usando tecnologia cloud.",
    "Desafios e oportunidades na área de {topic} para profissionais e organizações em 2026.",
    "O papel da transformação digital na evolução de {topic} e seus benefícios comprovados.",
    "Análise comparativa de abordagens tradicionais vs modernas em {topic} no cenário enterprise.",
    "Guia prático para líderes: como implementar estratégias de {topic} com resultados mensuráveis.",
    "Impacto econômico e social da {topic} na América Latina e perspectivas de crescimento.",
    "Melhores práticas de governança e compliance na área de {topic} para grandes corporações.",
]

TOPICS = [
    "computação em nuvem", "machine learning", "segurança cibernética", "big data",
    "telemedicina", "biotecnologia", "fintech", "blockchain", "educação digital",
    "energia renovável", "robótica", "internet das coisas", "realidade aumentada",
    "análise preditiva", "automação de processos", "engenharia de dados",
    "microserviços", "DevOps", "sustentabilidade corporativa", "gestão ágil",
]


def generate_documents(num_docs: int) -> list[dict]:
    """Gera documentos sintéticos com metadados."""
    documents = []
    for i in range(num_docs):
        category = CATEGORIES[i % len(CATEGORIES)]
        template = TEMPLATES[i % len(TEMPLATES)]
        topic = TOPICS[i % len(TOPICS)]
        text = template.format(topic=topic)
        # Adiciona variação ao texto
        text += f" Documento {i+1} da categoria {category}."

        doc = {
            "id": f"doc-{i+1:04d}",
            "title": f"Documento {i+1}: {topic.title()}",
            "content": text,
            "category": category,
            "metadata": {
                "author": f"autor-{(i % 50) + 1}",
                "year": 2024 + (i % 3),
                "relevance_score": round(np.random.uniform(0.5, 1.0), 3),
            },
        }
        documents.append(doc)
    return documents


def generate_embeddings(client: AzureOpenAI, texts: list[str]) -> list[list[float]]:
    """Gera embeddings em batch usando Azure OpenAI."""
    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        print(f"  Gerando embeddings batch {i//BATCH_SIZE + 1}/{(len(texts)-1)//BATCH_SIZE + 1}...")
        response = client.embeddings.create(
            input=batch,
            model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        )
        embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(embeddings)
        time.sleep(0.5)  # Rate limiting
    return all_embeddings


def generate_query_embeddings(client: AzureOpenAI) -> list[dict]:
    """Gera queries de teste com embeddings."""
    queries = [
        "Como a inteligência artificial impacta a saúde?",
        "Tendências de computação em nuvem no Brasil",
        "Segurança cibernética para empresas",
        "Transformação digital em educação",
        "Sustentabilidade e tecnologia verde",
        "Fintech e blockchain no mercado financeiro",
        "Automação de processos com machine learning",
        "Internet das coisas em ambientes industriais",
        "Governança de dados e compliance",
        "DevOps e microserviços em produção",
        "Análise preditiva para tomada de decisão",
        "Realidade aumentada na educação moderna",
        "Big data e engenharia de dados escalável",
        "Robótica aplicada à indústria brasileira",
        "Energia renovável e inovação tecnológica",
        "Biotecnologia e avanços em saúde digital",
        "Gestão ágil em grandes corporações",
        "Telemedicina no contexto pós-pandemia",
        "Impacto econômico da transformação digital",
        "Melhores práticas de segurança na nuvem",
    ]

    print("\nGerando embeddings para queries de teste...")
    embeddings = generate_embeddings(client, queries)

    query_data = []
    for q, emb in zip(queries, embeddings):
        query_data.append({"text": q, "embedding": emb})
    return query_data


def main():
    print("=" * 60)
    print(" GERAÇÃO DE DATASET PARA BENCHMARK VETORIAL")
    print("=" * 60)

    if not AZURE_OPENAI_ENDPOINT:
        print("\n⚠️  Configure as variáveis de ambiente:")
        print("   AZURE_OPENAI_ENDPOINT=https://<seu-recurso>.openai.azure.com/")
        print("   AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small")
        print("\nAutenticação: Entra ID (az login)")
        print("\nOU crie um arquivo .env na raiz do projeto.")
        return

    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential,
        "https://cognitiveservices.azure.com/.default",
    )

    client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_version="2024-06-01",
    )

    # 1. Gerar documentos
    print(f"\n[1/3] Gerando {NUM_DOCUMENTS} documentos sintéticos...")
    documents = generate_documents(NUM_DOCUMENTS)
    print(f"  ✓ {len(documents)} documentos gerados")

    # 2. Gerar embeddings para documentos
    print(f"\n[2/3] Gerando embeddings ({EMBEDDING_DIMS} dims)...")
    texts = [doc["content"] for doc in documents]
    embeddings = generate_embeddings(client, texts)

    for doc, emb in zip(documents, embeddings):
        doc["embedding"] = emb
    print(f"  ✓ {len(embeddings)} embeddings gerados")

    # 3. Gerar queries de teste
    print("\n[3/3] Gerando queries de benchmark...")
    queries = generate_query_embeddings(client)
    print(f"  ✓ {len(queries)} queries geradas")

    # Salvar dados
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    docs_file = DATA_DIR / "documents.json"
    with open(docs_file, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False)
    print(f"\n📁 Documentos salvos: {docs_file} ({os.path.getsize(docs_file) / 1024 / 1024:.1f} MB)")

    queries_file = DATA_DIR / "queries.json"
    with open(queries_file, "w", encoding="utf-8") as f:
        json.dump(queries, f, ensure_ascii=False)
    print(f"📁 Queries salvas: {queries_file}")

    print("\n✅ Dataset gerado com sucesso!")
    print(f"   Documentos: {len(documents)}")
    print(f"   Dimensões: {EMBEDDING_DIMS}")
    print(f"   Queries de teste: {len(queries)}")


if __name__ == "__main__":
    main()
