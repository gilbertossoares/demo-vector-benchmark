"""
12-compare-all-platforms.py
Consolida resultados de benchmark de todas as plataformas (Azure, Databricks, Fabric)
e gera relatório comparativo com visualizações.

Lê todos os arquivos JSON em results/ e cria um sumário consolidado.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from tabulate import tabulate

RESULTS_DIR = Path(__file__).parent.parent / "results"


def load_all_benchmarks() -> Dict[str, Dict]:
    """Carrega todos os arquivos de benchmark encontrados."""
    all_results = {}
    
    if not RESULTS_DIR.exists():
        print(f"❌ Diretório de resultados não encontrado: {RESULTS_DIR}")
        return all_results

    json_files = sorted(RESULTS_DIR.glob("benchmark_*.json"))
    
    if not json_files:
        print(f"⚠️  Nenhum arquivo de benchmark encontrado em {RESULTS_DIR}")
        return all_results

    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Extrair identificador da plataforma do nome do arquivo
                filename = json_file.stem  # benchmark_20260619_123456
                
                # Determinar plataforma baseado no conteúdo
                platform = data.get('platform', 'Azure')
                
                # Usar timestamp como identificador único
                timestamp = data.get('timestamp', filename)
                
                key = f"{platform}_{timestamp}"
                all_results[key] = data
        except json.JSONDecodeError as e:
            print(f"⚠️  Erro ao ler {json_file.name}: {e}")
        except Exception as e:
            print(f"⚠️  Erro processando {json_file.name}: {e}")
    
    return all_results


def consolidate_results(all_results: Dict[str, Dict]) -> pd.DataFrame:
    """
    Consolida resultados em DataFrame para análise.
    
    Returns:
        DataFrame com colunas: Platform, Service, Mean_ms, Median_ms, P95_ms, P99_ms, Min_ms, Max_ms, StdDev_ms
    """
    rows = []
    
    for key, data in all_results.items():
        platform = data.get('platform', 'Azure')
        timestamp = data.get('timestamp', '')
        results = data.get('results', {})
        
        for service_name, stats in results.items():
            if isinstance(stats, dict) and 'error' not in stats:
                rows.append({
                    'Platform': platform,
                    'Timestamp': timestamp,
                    'Service': service_name,
                    'Mean_ms': stats.get('mean_ms', 0),
                    'Median_ms': stats.get('median_ms', 0),
                    'P95_ms': stats.get('p95_ms', 0),
                    'P99_ms': stats.get('p99_ms', 0),
                    'Min_ms': stats.get('min_ms', 0),
                    'Max_ms': stats.get('max_ms', 0),
                    'StdDev_ms': stats.get('std_ms', 0),
                    'Count': stats.get('count', 0),
                })
    
    return pd.DataFrame(rows)


def print_ranking_by_platform(df: pd.DataFrame):
    """Mostra ranking de latência por plataforma."""
    print("\n" + "=" * 80)
    print(" RANKING CONSOLIDADO — POR PLATAFORMA")
    print("=" * 80)
    
    for platform in sorted(df['Platform'].unique()):
        platform_df = df[df['Platform'] == platform].sort_values('Mean_ms')
        
        print(f"\n🔷 {platform.upper()}")
        print("─" * 80)
        
        for idx, (_, row) in enumerate(platform_df.iterrows(), 1):
            bar = "█" * max(1, int(row['Mean_ms'] / 5))
            stability = "✓ Muito Estável" if row['StdDev_ms'] < 5 else "⚠ Variável" if row['StdDev_ms'] > 50 else "✓ Estável"
            
            print(f"  {idx}º {row['Service']:<40} {row['Mean_ms']:>8.2f}ms  {bar}  {stability}")


def print_best_method_by_platform(df: pd.DataFrame):
    """Mostra o melhor método (menor média) por plataforma."""
    print("\n" + "=" * 80)
    print(" MELHOR MÉTODO POR PLATAFORMA")
    print("=" * 80)

    best_rows = []
    for platform in sorted(df['Platform'].unique()):
        platform_df = df[df['Platform'] == platform]
        if platform_df.empty:
            continue
        best = platform_df.nsmallest(1, 'Mean_ms').iloc[0]
        best_rows.append([
            platform,
            best['Service'],
            f"{best['Mean_ms']:.2f}",
            f"{best['P95_ms']:.2f}",
            f"{best['StdDev_ms']:.2f}",
            str(best.get('Timestamp', ''))[:19],
        ])

    headers = ["Platform", "Melhor Serviço", "Média (ms)", "P95 (ms)", "StdDev (ms)", "Timestamp"]
    print("\n" + tabulate(best_rows, headers=headers, tablefmt="grid"))


def print_latest_run_summary(all_results: Dict[str, Dict]):
    """Mostra o último benchmark disponível por plataforma."""
    print("\n" + "=" * 80)
    print(" ÚLTIMA EXECUÇÃO POR PLATAFORMA")
    print("=" * 80)

    latest_by_platform = {}
    for _, data in all_results.items():
        platform = data.get('platform', 'Azure')
        ts = data.get('timestamp', '')
        if platform not in latest_by_platform or ts > latest_by_platform[platform].get('timestamp', ''):
            latest_by_platform[platform] = data

    rows = []
    for platform in sorted(latest_by_platform.keys()):
        item = latest_by_platform[platform]
        rows.append([
            platform,
            item.get('timestamp', ''),
            len(item.get('results', {})),
            item.get('config', {}).get('top_k', '-'),
            item.get('config', {}).get('num_iterations', '-'),
            item.get('config', {}).get('warmup_queries', '-'),
        ])

    headers = ["Platform", "Timestamp", "Serviços", "Top-K", "Iterações", "Warmup"]
    print("\n" + tabulate(rows, headers=headers, tablefmt="grid"))


def print_top_performers(df: pd.DataFrame, top_n: int = 5):
    """Mostra top N serviços mais rápidos (geral)."""
    print("\n" + "=" * 80)
    print(f" TOP {top_n} SERVIÇOS MAIS RÁPIDOS (Global)")
    print("=" * 80)
    
    top_df = df.nsmallest(top_n, 'Mean_ms')[['Platform', 'Service', 'Mean_ms', 'P95_ms', 'StdDev_ms']]
    
    for idx, (_, row) in enumerate(top_df.iterrows(), 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉"
        print(f"\n  {medal} #{idx} {row['Service']}")
        print(f"      Plataforma: {row['Platform']}")
        print(f"      Média: {row['Mean_ms']:.2f}ms | P95: {row['P95_ms']:.2f}ms | StdDev: {row['StdDev_ms']:.2f}ms")


def print_comparison_table(df: pd.DataFrame):
    """Tabela detalhada com todos os serviços."""
    print("\n" + "=" * 120)
    print(" COMPARAÇÃO DETALHADA — TODOS OS SERVIÇOS")
    print("=" * 120)
    
    # Preparar dados para tabela
    table_data = []
    for _, row in df.sort_values(['Mean_ms']).iterrows():
        stability = "✓" if row['StdDev_ms'] < 5 else "⚠" if row['StdDev_ms'] > 50 else "✓"
        table_data.append([
            row['Platform'],
            row['Service'],
            f"{row['Mean_ms']:.2f}",
            f"{row['Median_ms']:.2f}",
            f"{row['P95_ms']:.2f}",
            f"{row['P99_ms']:.2f}",
            f"{row['Min_ms']:.2f}",
            f"{row['Max_ms']:.2f}",
            f"{row['StdDev_ms']:.2f}",
            stability,
        ])
    
    headers = ["Platform", "Service", "Mean", "Median", "P95", "P99", "Min", "Max", "StdDev", "Stability"]
    print("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))


def print_platform_summary(df: pd.DataFrame):
    """Sumário de performance por plataforma."""
    print("\n" + "=" * 80)
    print(" SUMÁRIO POR PLATAFORMA")
    print("=" * 80)
    
    summary = df.groupby('Platform').agg({
        'Mean_ms': ['min', 'mean', 'max'],
        'StdDev_ms': ['mean'],
        'Service': 'count',
    }).round(2)
    
    summary.columns = ['Melhor_ms', 'Média_ms', 'Pior_ms', 'Estabilidade_Avg', 'Num_Serviços']
    
    print("\n" + summary.to_string())


def print_stability_analysis(df: pd.DataFrame):
    """Análise de estabilidade (desvio padrão)."""
    print("\n" + "=" * 80)
    print(" ANÁLISE DE ESTABILIDADE (Desvio Padrão)")
    print("=" * 80)
    print("\nMenor desvio = mais previsível | Maior desvio = mais variável")
    
    stability_df = df[['Platform', 'Service', 'StdDev_ms']].sort_values('StdDev_ms')
    
    print("\n🔹 MAIS ESTÁVEIS (Top 10):")
    for idx, (_, row) in enumerate(stability_df.head(10).iterrows(), 1):
        bar = "▓" * min(20, int(row['StdDev_ms'] * 2))
        print(f"  {idx:2d}º {row['Service']:<40} {row['StdDev_ms']:>7.2f}ms  {bar}")
    
    print("\n🔴 MAIS VARIÁVEIS (Bottom 5):")
    for idx, (_, row) in enumerate(stability_df.tail(5).iterrows(), 1):
        bar = "▓" * min(20, int(row['StdDev_ms'] * 2))
        print(f"      {row['Service']:<40} {row['StdDev_ms']:>7.2f}ms  {bar}")


def generate_markdown_report(df: pd.DataFrame, all_results: Dict[str, Dict]) -> str:
    """Gera relatório em Markdown."""
    report = "# 📊 Relatório Consolidado — Benchmark Vector Search\n\n"
    report += f"**Data de Geração:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    report += "## 📋 Resumo Executivo\n\n"
    
    # Top performer
    top = df.nsmallest(1, 'Mean_ms').iloc[0]
    report += f"**🥇 Melhor Performance:** {top['Service']} ({top['Platform']}) — **{top['Mean_ms']:.2f}ms**\n\n"
    
    # Plataformas
    report += "## 🎯 Performance por Plataforma\n\n"
    for platform in sorted(df['Platform'].unique()):
        platform_df = df[df['Platform'] == platform]
        best = platform_df.nsmallest(1, 'Mean_ms').iloc[0]
        avg = platform_df['Mean_ms'].mean()
        worst = platform_df.nlargest(1, 'Mean_ms').iloc[0]
        
        report += f"### {platform}\n"
        report += f"- **Melhor:** {best['Service']} — {best['Mean_ms']:.2f}ms\n"
        report += f"- **Pior:** {worst['Service']} — {worst['Mean_ms']:.2f}ms\n"
        report += f"- **Média:** {avg:.2f}ms\n"
        report += f"- **Serviços testados:** {len(platform_df)}\n\n"
    
    # Tabela consolidada
    report += "## 📊 Tabela Consolidada\n\n"
    report += "| Plataforma | Serviço | Média (ms) | P95 (ms) | P99 (ms) | StdDev (ms) |\n"
    report += "|------------|---------|-----------|---------|---------|-------------|\n"
    
    for _, row in df.sort_values('Mean_ms').iterrows():
        report += f"| {row['Platform']} | {row['Service']} | {row['Mean_ms']:.2f} | {row['P95_ms']:.2f} | {row['P99_ms']:.2f} | {row['StdDev_ms']:.2f} |\n"
    
    report += "\n## ✨ Insights Principais\n\n"
    
    # Análises
    stability_df = df.sort_values('StdDev_ms')
    best_stable = stability_df.iloc[0]
    
    report += f"- **Mais estável:** {best_stable['Service']} ({best_stable['Platform']}) — StdDev: {best_stable['StdDev_ms']:.2f}ms\n"
    
    # Platform comparison
    platform_means = df.groupby('Platform')['Mean_ms'].mean().sort_values()
    best_platform = platform_means.idxmin()
    report += f"- **Plataforma mais rápida (em média):** {best_platform} — {platform_means[best_platform]:.2f}ms\n"
    
    report += "\n---\n"
    report += f"*Gerado automaticamente em {datetime.now().isoformat()}*\n"
    
    return report


def main():
    print("=" * 80)
    print(" CONSOLIDAÇÃO DE RESULTADOS — BENCHMARK VECTOR SEARCH")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Carregar resultados
    all_results = load_all_benchmarks()
    
    if not all_results:
        print("\n❌ Nenhum resultado de benchmark encontrado!")
        print("   Execute os scripts de benchmark primeiro:")
        print("   - python scripts/08-run-benchmark.py")
        print("   - python scripts/10-run-benchmark-databricks.py")
        print("   - python scripts/11-run-benchmark-fabric.py")
        return
    
    print(f"\n✓ {len(all_results)} benchmark(s) carregado(s)")
    
    # Consolidar
    df = consolidate_results(all_results)
    
    if df.empty:
        print("\n⚠️  Nenhum dado válido encontrado nos benchmarks")
        return
    
    print(f"✓ {len(df)} serviço(s) analisado(s)")
    
    # Gerar outputs
    print_latest_run_summary(all_results)
    print_best_method_by_platform(df)
    print_ranking_by_platform(df)
    print_top_performers(df, top_n=5)
    print_platform_summary(df)
    print_stability_analysis(df)
    print_comparison_table(df)
    
    # Gerar Markdown report
    markdown_report = generate_markdown_report(df, all_results)
    report_file = RESULTS_DIR / f"REPORT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(markdown_report)
    
    # Salvar CSV para análise posterior
    csv_file = RESULTS_DIR / f"consolidated_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(csv_file, index=False)
    
    print("\n" + "=" * 80)
    print(" 📁 ARQUIVOS GERADOS")
    print("=" * 80)
    print(f"\n📄 Relatório Markdown: {report_file.name}")
    print(f"📊 Dados CSV: {csv_file.name}")
    print("\n✅ Consolidação concluída!")
    
    # Dicas para próximos passos
    print("\n" + "=" * 80)
    print(" 💡 PRÓXIMOS PASSOS")
    print("=" * 80)
    print("\n1. Abra o relatório Markdown para detalhes:")
    print(f"   cat {report_file.name}")
    print("\n2. Importe o CSV para Excel/Power BI para visualizações:")
    print(f"   {csv_file.name}")
    print("\n3. Compartilhe o relatório com stakeholders")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
