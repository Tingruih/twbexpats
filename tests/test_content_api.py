from site_builder.api.content import extract_play_videos

CONTENT_FIXTURE = {
    "highlights": {"highlights": {"items": [
        {   # 單一 play 精華：guid == play_id
            "guid": "a00d2214-3658-347f-98fc-24c89abb9d0e",
            "title": "Machado's 21st homer",
            "playbacks": [
                {"name": "hlsCloud", "url": "https://x/master.m3u8"},
                {"name": "mp4Avc", "url": "https://mlb-cuts-diamond.mlb.com/x.mp4"},
            ],
        },
        {   # 合輯類：guid 為 null → 略過
            "guid": None,
            "title": "Recap",
            "playbacks": [{"name": "mp4Avc", "url": "https://x/recap.mp4"}],
        },
        {   # 有 guid 但無 mp4 → 略過
            "guid": "ffffffff-0000-0000-0000-000000000000",
            "title": "HLS only",
            "playbacks": [{"name": "hlsCloud", "url": "https://x/only.m3u8"}],
        },
    ]}}
}


def test_extract_play_videos():
    videos = extract_play_videos(CONTENT_FIXTURE)
    assert videos == [{
        "play_id": "a00d2214-3658-347f-98fc-24c89abb9d0e",
        "title": "Machado's 21st homer",
        "mp4_url": "https://mlb-cuts-diamond.mlb.com/x.mp4",
    }]


def test_extract_play_videos_empty():
    assert extract_play_videos({}) == []
    assert extract_play_videos({"highlights": None}) == []
