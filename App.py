import os

import numpy as np
import streamlit as st
import streamlit.components.v1 as components
import requests

# Optional deps (실제 연동 시 필요)
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:  # pragma: no cover
    firebase_admin = None
    credentials = None
    firestore = None

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except Exception:  # pragma: no cover
    spotipy = None
    SpotifyClientCredentials = None

try:
    import lyricsgenius
except Exception:  # pragma: no cover
    lyricsgenius = None

try:
    import yt_dlp
except Exception:  # pragma: no cover
    yt_dlp = None

try:
    import librosa
except Exception:  # pragma: no cover
    librosa = None


# ==========================================
# ⚙️ 0. 환경 설정 및 초기화 (API & Firebase)
# ==========================================
st.set_page_config(page_title="AI 타임라인 음악 분석기", layout="wide")

# API Keys (실제 환경에서는 st.secrets 또는 환경변수 사용 권장)
SPOTIFY_CLIENT_ID = st.secrets.get(
    "SPOTIFY_CLIENT_ID", os.getenv("SPOTIFY_CLIENT_ID", "YOUR_SPOTIFY_CLIENT_ID")
)
SPOTIFY_CLIENT_SECRET = st.secrets.get(
    "SPOTIFY_CLIENT_SECRET",
    os.getenv("SPOTIFY_CLIENT_SECRET", "YOUR_SPOTIFY_CLIENT_SECRET"),
)
GENIUS_ACCESS_TOKEN = st.secrets.get(
    "GENIUS_ACCESS_TOKEN", os.getenv("GENIUS_ACCESS_TOKEN", "YOUR_GENIUS_ACCESS_TOKEN")
)

# Firebase 초기화 (선택)
db = None
if firebase_admin is not None:
    if not firebase_admin._apps:
        # 실제 구동 시 아래 주석을 해제하고 인증 파일 경로를 연결하세요.
        # cred = credentials.Certificate("path/to/your/firebase-adminsdk.json")
        # firebase_admin.initialize_app(cred)
        pass
    # db = firestore.client()  # Firebase 연결 시 주석 해제

# Session State 초기화
if "analyzed_data" not in st.session_state:
    st.session_state.analyzed_data = None
if "current_track_id" not in st.session_state:
    st.session_state.current_track_id = None


# ==========================================
# 🎵 1단계: 스포티파이 연동 및 메타데이터 추출
# ==========================================
def get_spotify_data(query: str):
    """Spotify API를 통해 곡 메타데이터 및 Audio Features 추출

    - query: "곡명 아티스트" 같은 텍스트 또는 스포티파이 트랙 URL/URI.
    """

    pitch_classes = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

    if spotipy is None or SpotifyClientCredentials is None:
        raise RuntimeError(
            "spotipy가 설치되지 않았습니다. requirements.txt 설치 후 다시 실행하세요."
        )

    if (
        not SPOTIFY_CLIENT_ID
        or not SPOTIFY_CLIENT_SECRET
        or SPOTIFY_CLIENT_ID.startswith("YOUR_")
        or SPOTIFY_CLIENT_SECRET.startswith("YOUR_")
    ):
        raise RuntimeError(
            "Spotify API 키가 설정되지 않았습니다. .streamlit/secrets.toml을 확인하세요."
        )

    # 일부 환경(회사/학교/보안SW 등)에서는 HTTP(S)_PROXY 설정 때문에
    # accounts.spotify.com 인증 요청이 프록시로 우회되며 403이 발생할 수 있습니다.
    # requests가 환경 프록시를 자동 적용하지 않도록 차단합니다.
    session = requests.Session()
    session.trust_env = False

    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
        ),
        requests_session=session,
    )

    track = None
    try:
        if "spotify.com/track/" in query or query.startswith("spotify:track:"):
            track = sp.track(query)
        else:
            results = sp.search(q=query, limit=1, type="track")
            items = (results or {}).get("tracks", {}).get("items", [])
            track = items[0] if items else None
    except Exception as e:
        raise RuntimeError(f"Spotify 검색/조회 실패: {e}") from e

    if not track:
        raise RuntimeError("Spotify에서 곡을 찾지 못했습니다. 검색어를 바꿔보세요.")

    track_id = track.get("id") or ""
    title = track.get("name") or "Unknown"
    artists = track.get("artists") or []
    artist = artists[0].get("name") if artists else "Unknown"
    images = (track.get("album") or {}).get("images") or []
    album_art = images[0].get("url") if images else ""

    try:
        af_list = sp.audio_features([track_id]) if track_id else [None]
        af = af_list[0] if af_list else None
    except Exception:
        af = None

    tempo = float(af.get("tempo")) if af and af.get("tempo") is not None else 0.0
    key_int = int(af.get("key")) if af and af.get("key") is not None else -1
    mode_int = int(af.get("mode")) if af and af.get("mode") is not None else -1
    key_name = pitch_classes[key_int] if 0 <= key_int < 12 else "Unknown"
    mode_name = "Major" if mode_int == 1 else ("Minor" if mode_int == 0 else "")

    return {
        "id": track_id,
        "title": title,
        "artist": artist,
        "album_art": album_art,
        "bpm": round(tempo, 2),
        "key": key_name,
        "mode": mode_name,
    }


# ==========================================
# 🎤 2단계: 유튜브 추출 및 가사 동기화
# ==========================================
def fetch_lyrics(artist: str, title: str):
    """Genius API를 통해 가사 가져오기 (현재는 Mock)."""
    # genius = lyricsgenius.Genius(GENIUS_ACCESS_TOKEN)
    # song = genius.search_song(title, artist)
    # return song.lyrics if song else "가사 정보를 불러올 수 없습니다."
    return (
        "[Verse 1]\n(1,2,3,4) Baby, got me looking so crazy\n빠져버리는 daydream\n"
        "[Chorus]\nCause I know what you like boy"
    )


def extract_audio(youtube_url: str):
    """yt-dlp로 오디오 추출 (현재는 mock 파일명만 반환)."""
    output_filename = "temp_audio.mp3"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_filename,
        "quiet": True,
    }
    # 실제 다운로드 로직:
    # with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    #     ydl.download([youtube_url])
    return output_filename


# ==========================================
# 🎹 3단계: 타임라인 코드 분석
# ==========================================
def analyze_chords_and_timeline(audio_file: str, lyrics: str):
    """librosa 기반 코드 분석 및 가사 매칭 (현재는 Mock 타임라인)."""
    timeline = []
    lines = [ln for ln in (lyrics or "").split("\n") if ln.strip()]
    if not lines:
        lines = [""]

    for i in range(20):
        time_str = f"{i//60:02d}:{i%60:02d}"
        chord = str(np.random.choice(["Cmaj7", "Dm7", "G7", "Am7"]))
        lyric_snippet = lines[i % len(lines)]
        section = "Chorus" if 10 <= i <= 15 else "Verse"
        timeline.append(
            {"time": time_str, "chord": chord, "lyric": lyric_snippet, "section": section}
        )
    return timeline


# ==========================================
# 💾 4단계: Firebase 캐싱 로직
# ==========================================
def check_firestore_cache(track_id: str):
    """Firestore에 분석 데이터가 있는지 확인 (비용 절감)."""
    if db is None:
        return None
    # doc = db.collection('analyzed_tracks').document(track_id).get()
    # if doc.exists: return doc.to_dict()
    return None


def save_to_firestore(track_data, timeline_data):
    """분석 완료된 데이터를 Firestore에 저장."""
    if db is None:
        return
    # doc_ref = db.collection('analyzed_tracks').document(track_data['id'])
    # doc_ref.set({"meta": track_data, "timeline": timeline_data})


def get_recent_tracks():
    """사이드바용 최근 분석 인기 곡 리스트 불러오기."""
    # docs = db.collection('analyzed_tracks').order_by('analyzed_at', direction=firestore.Query.DESCENDING).limit(5).stream()
    return ["Ditto - NewJeans", "Supernova - aespa", "Seven - Jung Kook"]


# ==========================================
# 🎨 UI 컴포넌트 렌더링
# ==========================================
def render_header(data):
    """SwiftUI 카드 스타일 헤더 컴포넌트."""
    st.markdown(
        """
        <style>
        .swiftui-card {
            background-color: #ffffff;
            border-radius: 20px;
            padding: 20px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 20px;
        }
        .swiftui-stats {
            background-color: #f0f2f6;
            border-radius: 15px;
            padding: 15px 25px;
            text-align: center;
        }
        </style>
    """,
        unsafe_allow_html=True,
    )

    html = f"""
    <div class="swiftui-card">
        <img src="{data['album_art']}" width="120" style="border-radius: 15px;">
        <div style="flex-grow: 1;">
            <h2 style="margin:0; color:#1f1f1f;">{data['title']}</h2>
            <p style="margin:0; color:#888; font-size:18px;">{data['artist']}</p>
        </div>
        <div class="swiftui-stats">
            <h4 style="margin:0; color:#888;">BPM</h4>
            <h2 style="margin:0; color:#1f1f1f;">{data['bpm']}</h2>
        </div>
        <div class="swiftui-stats">
            <h4 style="margin:0; color:#888;">Key</h4>
            <h2 style="margin:0; color:#1f1f1f;">{data['key']} {data['mode']}</h2>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_timeline(timeline):
    """타임라인 리스트 출력 및 HTML 애드센스 삽입."""
    st.subheader("⏱️ 타임라인 및 코드 분석")

    st.markdown(
        """
        <style>
        .timeline-row {
            display: flex;
            padding: 15px;
            border-bottom: 1px solid #eee;
            align-items: center;
        }
        .time-badge { font-family: monospace; color: #555; width: 60px; }
        .chord-badge { background: #007AFF; color: white; padding: 5px 12px; border-radius: 10px; font-weight: bold; width: 80px; text-align: center;}
        .lyrics-text { margin-left: 20px; flex-grow: 1; color: #333; }
        .section-tag { background: #FF3B30; color: white; padding: 3px 8px; border-radius: 5px; font-size: 12px; }
        </style>
    """,
        unsafe_allow_html=True,
    )

    for idx, row in enumerate(timeline):
        if idx > 0 and idx % 10 == 0:
            st.markdown(
                "<div style='text-align:center; padding: 10px; background:#f9f9f9; border-radius:10px; margin: 10px 0;'>광고 슬롯 (AdSense)</div>",
                unsafe_allow_html=True,
            )
            # 실제 애드센스 코드 삽입 시 아래 사용 (반응형 CSS 적용)
            # components.html("<style>.ad-container { width: 100%; height: auto; }</style><div class='ad-container'>광고 스크립트</div>", height=100)

        section_html = (
            f"<span class='section-tag'>{row['section']}</span>"
            if row["section"] == "Chorus"
            else ""
        )

        row_html = f"""
        <div class="timeline-row">
            <div class="time-badge">{row['time']}</div>
            <div class="chord-badge">{row['chord']}</div>
            <div class="lyrics-text">{row['lyric']} {section_html}</div>
        </div>
        """
        st.markdown(row_html, unsafe_allow_html=True)


# ==========================================
# 🚀 메인 애플리케이션 실행
# ==========================================
def main():
    main_col, right_sidebar = st.columns([3, 1])

    with main_col:
        st.title("🎶 AI 타임라인 음악 분석기")
        search_query = st.text_input(
            "유튜브 링크 또는 곡명/아티스트를 입력하세요",
            placeholder="예: NewJeans Hype Boy",
        )

        if st.button("분석 시작", type="primary") and search_query:
            try:
                track_data = get_spotify_data(search_query)
            except Exception as e:
                st.error(str(e))
                return
            st.session_state.current_track_id = track_data["id"]

            cached_data = check_firestore_cache(track_data["id"])
            if cached_data:
                st.success("✨ 캐시된 데이터를 불러옵니다. (분석 시간 단축!)")
                st.session_state.analyzed_data = cached_data
            else:
                with st.spinner("오디오 추출 및 AI 분석 진행 중..."):
                    lyrics = fetch_lyrics(track_data["artist"], track_data["title"])
                    audio_path = extract_audio("mock_youtube_url")
                    timeline_data = analyze_chords_and_timeline(audio_path, lyrics)

                    if os.path.exists(audio_path):
                        os.remove(audio_path)

                    final_data = {"meta": track_data, "timeline": timeline_data}
                    save_to_firestore(track_data, timeline_data)
                    st.session_state.analyzed_data = final_data

        if st.session_state.analyzed_data:
            render_header(st.session_state.analyzed_data["meta"])
            render_timeline(st.session_state.analyzed_data["timeline"])

    with right_sidebar:
        st.markdown("### 📌 최근 분석된 인기 곡")
        for track in get_recent_tracks():
            st.markdown(f"- {track}")

        st.divider()
        st.markdown("### 💰 Sponsor")
        ad_html = """
        <div style="background-color:#eaeaea; height:250px; border-radius:10px; display:flex; align-items:center; justify-content:center; color:#888;">
            구글 애드센스 반응형 광고 영역
        </div>
        """
        st.markdown(ad_html, unsafe_allow_html=True)
        # 실제 적용 시 components.html(ad_script, height=250)


if __name__ == "__main__":
    main()

