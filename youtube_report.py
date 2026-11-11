"""Relatório de estatísticas de um canal do YouTube.

Usa a YouTube Data API v3 (somente dados públicos, com chave de API)
para buscar as estatísticas do canal e dos vídeos mais recentes, e gera:

  - output/videos.csv       -> uma linha por vídeo
  - output/relatorio.html   -> resumo + gráficos (abre no navegador)

Uso:
    export YOUTUBE_API_KEY="sua-chave"
    python youtube_report.py --channel @seucanal --max-videos 50
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://www.googleapis.com/youtube/v3"


# --------------------------------------------------------------------------
# Modelos de dados
# --------------------------------------------------------------------------
@dataclass
class Channel:
    id: str
    title: str
    subscribers: int | None  # None quando o canal oculta o número
    total_views: int
    video_count: int
    uploads_playlist: str


@dataclass
class Video:
    id: str
    title: str
    published_at: str
    duration_seconds: int
    views: int
    likes: int
    comments: int

    @property
    def engagement_rate(self) -> float:
        """(likes + comentários) / views, em %."""
        if self.views == 0:
            return 0.0
        return round((self.likes + self.comments) / self.views * 100, 2)

    @property
    def is_short(self) -> bool:
        # Aproximação: vídeos de até 3 min costumam ser Shorts.
        return self.duration_seconds <= 180

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"


# --------------------------------------------------------------------------
# Cliente da API
# --------------------------------------------------------------------------
class YouTubeAPIError(RuntimeError):
    pass


def api_get(endpoint: str, params: dict, api_key: str) -> dict:
    query = urllib.parse.urlencode({**params, "key": api_key})
    url = f"{API_BASE}/{endpoint}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise YouTubeAPIError(f"Erro {err.code} em {endpoint}: {detail}") from err


def fetch_channel(channel: str, api_key: str) -> Channel:
    """Aceita um @handle (ex.: @meucanal) ou um ID de canal (UC...)."""
    params = {"part": "snippet,statistics,contentDetails"}
    if channel.startswith("UC") and len(channel) == 24:
        params["id"] = channel
    else:
        params["forHandle"] = channel if channel.startswith("@") else f"@{channel}"

    data = api_get("channels", params, api_key)
    items = data.get("items") or []
    if not items:
        raise YouTubeAPIError(f"Canal não encontrado: {channel}")

    item = items[0]
    stats = item["statistics"]
    return Channel(
        id=item["id"],
        title=item["snippet"]["title"],
        subscribers=None
        if stats.get("hiddenSubscriberCount")
        else int(stats.get("subscriberCount", 0)),
        total_views=int(stats.get("viewCount", 0)),
        video_count=int(stats.get("videoCount", 0)),
        uploads_playlist=item["contentDetails"]["relatedPlaylists"]["uploads"],
    )


def fetch_video_ids(playlist_id: str, max_videos: int, api_key: str) -> list[str]:
    ids: list[str] = []
    page_token = None
    while len(ids) < max_videos:
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, max_videos - len(ids)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = api_get("playlistItems", params, api_key)
        ids.extend(i["contentDetails"]["videoId"] for i in data.get("items", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return ids[:max_videos]


def fetch_videos(video_ids: list[str], api_key: str) -> list[Video]:
    videos: list[Video] = []
    # A API aceita no máximo 50 IDs por chamada.
    for start in range(0, len(video_ids), 50):
        batch = video_ids[start : start + 50]
        data = api_get(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)},
            api_key,
        )
        videos.extend(parse_video(item) for item in data.get("items", []))
    return videos


def parse_video(item: dict) -> Video:
    stats = item.get("statistics", {})
    return Video(
        id=item["id"],
        title=item["snippet"]["title"],
        published_at=item["snippet"]["publishedAt"],
        duration_seconds=parse_iso_duration(item["contentDetails"]["duration"]),
        views=int(stats.get("viewCount", 0)),
        likes=int(stats.get("likeCount", 0)),  # pode estar oculto
        comments=int(stats.get("commentCount", 0)),  # pode estar desativado
    )


def parse_iso_duration(value: str) -> int:
    """Converte duração ISO 8601 (ex.: PT1H2M30S) em segundos."""
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if not match:
        return 0
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


# --------------------------------------------------------------------------
# Saídas: CSV e HTML
# --------------------------------------------------------------------------
def write_csv(videos: list[Video], path: Path) -> None:
    fields = [
        "id", "title", "published_at", "duration_seconds",
        "views", "likes", "comments", "engagement_rate", "is_short", "url",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for v in videos:
            row = asdict(v)
            row.update(engagement_rate=v.engagement_rate, is_short=v.is_short, url=v.url)
            writer.writerow(row)


def summarize(videos: list[Video]) -> dict:
    def avg(values: list[int]) -> int:
        return round(sum(values) / len(values)) if values else 0

    shorts = [v for v in videos if v.is_short]
    longs = [v for v in videos if not v.is_short]
    return {
        "analyzed": len(videos),
        "avg_views": avg([v.views for v in videos]),
        "avg_views_shorts": avg([v.views for v in shorts]),
        "avg_views_longs": avg([v.views for v in longs]),
        "shorts_count": len(shorts),
        "longs_count": len(longs),
        "top": sorted(videos, key=lambda v: v.views, reverse=True)[:5],
        "best_engagement": sorted(videos, key=lambda v: v.engagement_rate, reverse=True)[:5],
    }


def fmt(n: int | None) -> str:
    return "oculto" if n is None else f"{n:,}".replace(",", ".")


def render_html(channel: Channel, videos: list[Video]) -> str:
    s = summarize(videos)
    chrono = sorted(videos, key=lambda v: v.published_at)
    chart_data = json.dumps(
        {
            "labels": [v.published_at[:10] for v in chrono],
            "titles": [v.title for v in chrono],
            "views": [v.views for v in chrono],
            "engagement": [v.engagement_rate for v in chrono],
        }
    )

    def rows(items: list[Video]) -> str:
        return "".join(
            f'<tr><td><a href="{v.url}" target="_blank" rel="noopener">{html.escape(v.title)}</a></td>'
            f"<td>{'Short' if v.is_short else 'Longo'}</td>"
            f"<td>{fmt(v.views)}</td><td>{v.engagement_rate}%</td></tr>"
            for v in items
        )

    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório · {html.escape(channel.title)}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {{ --bg:#f6f8f7; --card:#fff; --text:#1d2b27; --muted:#5f716b; --accent:#0f7c6c; --line:#dfe6e3; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#101716; --card:#18211f; --text:#e6efec; --muted:#9db0aa; --accent:#3cc2ab; --line:#2a3633; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:system-ui,sans-serif; background:var(--bg); color:var(--text); }}
  main {{ max-width:1000px; margin:0 auto; padding:24px 16px 48px; }}
  h1 {{ margin:0 0 4px; }} .muted {{ color:var(--muted); }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin:24px 0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
  .card b {{ display:block; font-size:1.6rem; color:var(--accent); }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-top:16px; overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; }}
  th,td {{ text-align:left; padding:8px; border-bottom:1px solid var(--line); }}
  a {{ color:var(--accent); }}
</style>
</head>
<body><main>
  <h1>{html.escape(channel.title)}</h1>
  <p class="muted">Gerado em {generated} · {s['analyzed']} vídeos mais recentes analisados</p>

  <div class="cards">
    <div class="card"><b>{fmt(channel.subscribers)}</b>inscritos</div>
    <div class="card"><b>{fmt(channel.total_views)}</b>views totais</div>
    <div class="card"><b>{fmt(channel.video_count)}</b>vídeos no canal</div>
    <div class="card"><b>{fmt(s['avg_views_shorts'])}</b>média por Short ({s['shorts_count']})</div>
    <div class="card"><b>{fmt(s['avg_views_longs'])}</b>média por vídeo longo ({s['longs_count']})</div>
  </div>

  <section><h2>Views por vídeo (ordem de publicação)</h2><canvas id="views"></canvas></section>
  <section><h2>Top 5 em views</h2>
    <table><tr><th>Vídeo</th><th>Tipo</th><th>Views</th><th>Engajamento</th></tr>{rows(s['top'])}</table>
  </section>
  <section><h2>Top 5 em engajamento</h2>
    <p class="muted">Engajamento = (likes + comentários) ÷ views</p>
    <table><tr><th>Vídeo</th><th>Tipo</th><th>Views</th><th>Engajamento</th></tr>{rows(s['best_engagement'])}</table>
  </section>
</main>
<script>
  const d = {chart_data};
  new Chart(document.getElementById('views'), {{
    data: {{
      labels: d.labels,
      datasets: [
        {{ type:'bar', label:'Views', data:d.views, backgroundColor:'#0f7c6c', yAxisID:'y' }},
        {{ type:'line', label:'Engajamento (%)', data:d.engagement, borderColor:'#e0913a', yAxisID:'y1' }}
      ]
    }},
    options: {{
      plugins: {{ tooltip: {{ callbacks: {{ title: (items) => d.titles[items[0].dataIndex] }} }} }},
      scales: {{ y: {{ beginAtZero:true }}, y1: {{ beginAtZero:true, position:'right', grid:{{ drawOnChartArea:false }} }} }}
    }}
  }});
</script>
</body></html>
"""


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Relatório de um canal do YouTube")
    parser.add_argument("--channel", required=True, help="@handle ou ID do canal (UC...)")
    parser.add_argument("--max-videos", type=int, default=50, help="Quantos vídeos recentes analisar")
    parser.add_argument("--out", default="output", help="Pasta de saída")
    args = parser.parse_args(argv)

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("Defina a variável de ambiente YOUTUBE_API_KEY (veja o README).", file=sys.stderr)
        return 1

    try:
        channel = fetch_channel(args.channel, api_key)
        ids = fetch_video_ids(channel.uploads_playlist, args.max_videos, api_key)
        videos = fetch_videos(ids, api_key)
    except YouTubeAPIError as err:
        print(err, file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(videos, out / "videos.csv")
    (out / "relatorio.html").write_text(render_html(channel, videos), encoding="utf-8")

    print(f"Canal: {channel.title} | inscritos: {fmt(channel.subscribers)}")
    print(f"{len(videos)} vídeos analisados -> {out / 'videos.csv'} e {out / 'relatorio.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
