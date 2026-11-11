# Relatório de Canal do YouTube

Script em Python que usa a **YouTube Data API v3** para gerar um relatório de um canal: inscritos, views, desempenho de cada vídeo e comparação entre Shorts e vídeos longos.

Feito para acompanhar o crescimento de um canal de aquarismo, mas funciona com qualquer canal público.

## O que ele gera

| Arquivo | Conteúdo |
|---|---|
| `output/videos.csv` | Uma linha por vídeo: views, likes, comentários, duração, taxa de engajamento, se é Short |
| `output/relatorio.html` | Resumo do canal, gráfico de views × engajamento e rankings Top 5 (abre no navegador) |

**Taxa de engajamento** = (likes + comentários) ÷ views × 100.

## Tecnologias e conceitos

- Python 3.10+ usando **só a biblioteca padrão** (`urllib`, `csv`, `dataclasses`, `argparse`)
- Consumo de API REST com **paginação** e **requisições em lote** (até 50 IDs por chamada)
- Conversão de duração no formato ISO 8601 (`PT1H2M30S` → segundos)
- Relatório HTML com Chart.js e tema claro/escuro
- Testes automatizados com `pytest` e *mock* da API

## Como usar

### 1. Criar a chave da API (grátis)

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/) e crie um projeto.
2. Em **APIs e serviços → Biblioteca**, ative a **YouTube Data API v3**.
3. Em **Credenciais → Criar credenciais → Chave de API**, copie a chave.
4. (Recomendado) Restrinja a chave para usar apenas a YouTube Data API v3.

> Nunca coloque a chave no código nem faça commit dela. Ela fica só na variável de ambiente.

### 2. Rodar

```bash
# Linux / macOS
export YOUTUBE_API_KEY="sua-chave"

# Windows (PowerShell)
$env:YOUTUBE_API_KEY="sua-chave"

python youtube_report.py --channel @seucanal --max-videos 50
```

`--channel` aceita o `@handle` ou o ID do canal (`UC...`).

### 3. Testes

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Limitações conhecidas

- Usa só **dados públicos**. Retenção, CTR e origem do tráfego exigem a *YouTube Analytics API* com login OAuth (próximo passo).
- Vídeos de até 3 minutos são classificados como Short. É uma aproximação, porque a API não informa se um vídeo é Short.
- Se o canal oculta o número de inscritos, o relatório mostra "oculto".
- A cota gratuita é de 10.000 unidades por dia. Uma execução com 50 vídeos gasta cerca de 3 unidades.

## Próximos passos

- [ ] Rodar todo dia com GitHub Actions e salvar um histórico para gerar gráficos de crescimento
- [ ] Integrar a YouTube Analytics API (OAuth) para ver retenção e CTR
- [ ] Descobrir o melhor dia e horário de publicação
