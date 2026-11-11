import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_report as yr  # noqa: E402


def make_video(**kw):
    base = dict(id="abc", title="Betta", published_at="2026-01-01T00:00:00Z",
                duration_seconds=600, views=1000, likes=80, comments=20)
    base.update(kw)
    return yr.Video(**base)


def test_parse_iso_duration():
    assert yr.parse_iso_duration("PT45S") == 45
    assert yr.parse_iso_duration("PT1H2M30S") == 3750
    assert yr.parse_iso_duration("P1DT1S") == 86401
    assert yr.parse_iso_duration("invalido") == 0


def test_engagement_rate_and_zero_views():
    assert make_video().engagement_rate == 10.0
    assert make_video(views=0).engagement_rate == 0.0


def test_short_detection():
    assert make_video(duration_seconds=59).is_short
    assert not make_video(duration_seconds=600).is_short


def test_parse_video_missing_stats():
    item = {
        "id": "x1",
        "snippet": {"title": "Aquário plantado", "publishedAt": "2026-02-02T10:00:00Z"},
        "contentDetails": {"duration": "PT8M"},
        "statistics": {"viewCount": "500"},  # likes/comentários ocultos
    }
    v = yr.parse_video(item)
    assert (v.views, v.likes, v.comments, v.duration_seconds) == (500, 0, 0, 480)


def test_fetch_channel_hidden_subscribers(monkeypatch):
    def fake_get(endpoint, params, api_key):
        assert params["forHandle"] == "@aquario"
        return {"items": [{
            "id": "UC123",
            "snippet": {"title": "Aquário"},
            "statistics": {"hiddenSubscriberCount": True, "viewCount": "10", "videoCount": "2"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
        }]}
    monkeypatch.setattr(yr, "api_get", fake_get)
    ch = yr.fetch_channel("aquario", "k")
    assert ch.subscribers is None and ch.uploads_playlist == "UU123"


def test_outputs(tmp_path):
    channel = yr.Channel("UC1", "Canal <Teste>", 100, 5000, 2, "UU1")
    videos = [make_video(), make_video(id="s1", title="Short", duration_seconds=30, views=3000)]
    yr.write_csv(videos, tmp_path / "videos.csv")
    with (tmp_path / "videos.csv").open(encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 2
    page = yr.render_html(channel, videos)
    assert "Canal &lt;Teste&gt;" in page  # título escapado
    assert yr.summarize(videos)["top"][0].id == "s1"
