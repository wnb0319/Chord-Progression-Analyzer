import os

import html
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import numpy as np
import requests
import streamlit as st
import streamlit.components.v1 as components

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

# ==========================================
# ✅ 공통 유틸
# ==========================================
PITCH_CLASSES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def make_requests_session_no_proxy() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def safe_text(s: str) -> str:
    return html.escape(str(s or ""))


def is_youtube_url(s: str) -> bool:
    s = (s or "").strip().lower()
    return any(host in s for host in ("youtube.com/watch", "youtu.be/"))


def extract_youtube_title(url: str) -> str | None:
    if yt_dlp is None:
        return None
    try:
        with yt_dlp.YoutubeDL(
            {
                "quiet": True,
                "skip_download": True,
                "noplaylist": True,
                "extract_flat": True,
            }
        ) as ydl:
            info = ydl.extract_info(url, download=False)
        title = (info or {}).get("title")
        return title.strip() if isinstance(title, str) and title.strip() else None
    except Exception:
        return None


def extract_youtube_id(url: str) -> str | None:
    """youtube.com/watch?v=... 또는 youtu.be/... 에서 video id 추출."""
    try:
        u = urllib.parse.urlparse(url)
    except Exception:
        return None

    host = (u.netloc or "").lower()
    path = u.path or ""
    if "youtu.be" in host:
        vid = path.strip("/").split("/")[0]
        return vid or None
    if "youtube.com" in host:
        qs = urllib.parse.parse_qs(u.query or "")
        vid = (qs.get("v") or [None])[0]
        return vid or None
    return None


def render_youtube_player(video_id: str, start_sec: int = 0):
    start_sec = max(int(start_sec or 0), 0)
    src = f"https://www.youtube.com/embed/{video_id}?start={start_sec}&autoplay=1&mute=0&controls=1&rel=0"
    components.html(
        f"""
        <div style="border-radius:16px; overflow:hidden; box-shadow: 0 12px 28px rgba(0,0,0,0.12);">
          <iframe
            width="100%"
            height="420"
            src="{src}"
            title="YouTube player"
            frameborder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowfullscreen
          ></iframe>
        </div>
        """,
        height=440,
    )


def format_mmss(sec: int) -> str:
    sec = max(int(sec), 0)
    return f"{sec//60:02d}:{sec%60:02d}"


def yt_dlp_available() -> bool:
    return yt_dlp is not None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def chordino_available() -> bool:
    # Streamlit Cloud 환경에서는 보통 Vamp/Chordino가 없어서 False가 될 가능성이 큼.
    try:
        from chord_extractor.extractors import Chordino  # type: ignore

        _ = Chordino
        return True
    except Exception:
        return False


def download_youtube_audio_wav(youtube_url: str) -> str:
    """yt-dlp로 유튜브 오디오를 WAV로 추출해 로컬 파일 경로 반환."""
    if yt_dlp is None:
        raise RuntimeError("yt-dlp가 설치되지 않았습니다.")
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg가 없어 유튜브 오디오 변환이 불가합니다.")

    tmp_dir = tempfile.mkdtemp(prefix="yt_audio_")
    outtmpl = os.path.join(tmp_dir, "audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": True,
        "noplaylist": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",
            }
        ],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
    except Exception as e:
        raise RuntimeError(f"유튜브 오디오 추출 실패: {e}") from e

    wav_path = os.path.join(tmp_dir, "audio.wav")
    if not os.path.exists(wav_path):
        # 확장자 이름이 달라졌을 가능성에 대비
        for fn in os.listdir(tmp_dir):
            if fn.lower().endswith(".wav"):
                return os.path.join(tmp_dir, fn)
        raise RuntimeError("유튜브 오디오 WAV 파일을 찾지 못했습니다.")
    return wav_path

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
    session = make_requests_session_no_proxy()

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
    preview_url = track.get("preview_url") or ""

    try:
        af_list = sp.audio_features([track_id]) if track_id else [None]
        af = af_list[0] if af_list else None
    except Exception:
        af = None

    tempo = float(af.get("tempo")) if af and af.get("tempo") is not None else 0.0
    key_int = int(af.get("key")) if af and af.get("key") is not None else -1
    mode_int = int(af.get("mode")) if af and af.get("mode") is not None else -1
    key_name = PITCH_CLASSES[key_int] if 0 <= key_int < 12 else "Unknown"
    mode_name = "Major" if mode_int == 1 else ("Minor" if mode_int == 0 else "")

    return {
        "id": track_id,
        "title": title,
        "artist": artist,
        "album_art": album_art,
        "bpm": round(tempo, 2),
        "key": key_name,
        "mode": mode_name,
        "preview_url": preview_url,
    }


# ==========================================
# 🎤 2단계: 유튜브 추출 및 가사 동기화
# ==========================================
def fetch_lyrics(artist: str, title: str):
    """Genius API를 통해 가사 가져오기.

    - 토큰이 없으면 None 반환 (UI에서 붙여넣기 입력으로 대체 가능)
    """
    if (
        lyricsgenius is None
        or not GENIUS_ACCESS_TOKEN
        or GENIUS_ACCESS_TOKEN.startswith("YOUR_")
    ):
        return None
    try:
        genius = lyricsgenius.Genius(
            GENIUS_ACCESS_TOKEN,
            timeout=15,
            retries=1,
            remove_section_headers=False,
            verbose=False,
        )
        song = genius.search_song(title, artist)
        text = song.lyrics if song else None
        return text if isinstance(text, str) and text.strip() else None
    except Exception:
        return None


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
def _download_preview_mp3(preview_url: str, out_path: str) -> str:
    if not preview_url:
        raise RuntimeError("Spotify preview_url이 없습니다. (일부 곡은 미제공)")
    session = make_requests_session_no_proxy()
    r = session.get(preview_url, timeout=30)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path


def estimate_key_from_chroma(chroma: np.ndarray):
    """단순 key 추정(대략)."""
    maj = np.array(
        [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    )
    min_ = np.array(
        [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    )
    v = chroma.mean(axis=1)
    v = v / (np.linalg.norm(v) + 1e-9)
    maj = maj / np.linalg.norm(maj)
    min_ = min_ / np.linalg.norm(min_)

    best = ("Unknown", "")
    best_score = -1e9
    for k in range(12):
        s_maj = float(np.dot(v, np.roll(maj, k)))
        s_min = float(np.dot(v, np.roll(min_, k)))
        if s_maj > best_score:
            best_score = s_maj
            best = (PITCH_CLASSES[k], "Major")
        if s_min > best_score:
            best_score = s_min
            best = (PITCH_CLASSES[k], "Minor")
    return best


def chord_from_chroma_vec(v: np.ndarray) -> str:
    v = v / (np.linalg.norm(v) + 1e-9)
    best_label = "N"
    best_score = -1e9
    for root in range(12):
        maj = np.zeros(12)
        maj[root] = 1
        maj[(root + 4) % 12] = 1
        maj[(root + 7) % 12] = 1
        maj = maj / np.linalg.norm(maj)
        smaj = float(np.dot(v, maj))

        min_ = np.zeros(12)
        min_[root] = 1
        min_[(root + 3) % 12] = 1
        min_[(root + 7) % 12] = 1
        min_ = min_ / np.linalg.norm(min_)
        smin = float(np.dot(v, min_))

        if smaj > best_score:
            best_score = smaj
            best_label = f"{PITCH_CLASSES[root]}"
        if smin > best_score:
            best_score = smin
            best_label = f"{PITCH_CLASSES[root]}m"

    return best_label if best_score >= 0.45 else "N"


def analyze_chords_and_timeline_from_audio(audio_path: str, lyrics: str | None):
    """Spotify preview(약 30초) 오디오 기반 분석."""
    if librosa is None:
        raise RuntimeError("librosa가 설치되지 않았습니다.")

    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    if y.size == 0:
        raise RuntimeError("오디오를 불러오지 못했습니다.")

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key_name, mode_name = estimate_key_from_chroma(chroma)

    hop_length = 512
    frame_times = librosa.frames_to_time(
        np.arange(chroma.shape[1]), sr=sr, hop_length=hop_length
    )

    timeline = []
    max_sec = int(np.ceil(frame_times[-1])) if frame_times.size else 0
    for sec in range(0, min(max_sec + 1, 120)):
        mask = (frame_times >= sec) & (frame_times < sec + 1)
        if not np.any(mask):
            continue
        v = chroma[:, mask].mean(axis=1)
        chord = chord_from_chroma_vec(v)
        timeline.append(
            {"sec": sec, "time": format_mmss(sec), "chord": chord, "lyric": "", "section": ""}
        )

    if lyrics:
        lines = [ln.strip() for ln in lyrics.split("\n") if ln.strip()]
        if lines:
            for i, row in enumerate(timeline):
                row["lyric"] = lines[i % len(lines)]

    return {
        "tempo": float(tempo),
        "key": key_name,
        "mode": mode_name,
        "timeline": timeline,
    }


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
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;800&display=swap');
        html, body, [class*="css"]  { font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Malgun Gothic', 'Segoe UI', sans-serif; }
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

    title = safe_text(data.get("title", ""))
    artist = safe_text(data.get("artist", ""))
    album_art = safe_text(data.get("album_art", ""))
    bpm = safe_text(data.get("bpm", ""))
    key = safe_text(data.get("key", ""))
    mode = safe_text(data.get("mode", ""))

    html = f"""
    <div class="swiftui-card">
        <img src="{album_art}" width="120" style="border-radius: 15px;">
        <div style="flex-grow: 1;">
            <h2 style="margin:0; color:#1f1f1f;">{title}</h2>
            <p style="margin:0; color:#888; font-size:18px;">{artist}</p>
        </div>
        <div class="swiftui-stats">
            <h4 style="margin:0; color:#888;">BPM</h4>
            <h2 style="margin:0; color:#1f1f1f;">{bpm}</h2>
        </div>
        <div class="swiftui-stats">
            <h4 style="margin:0; color:#888;">Key</h4>
            <h2 style="margin:0; color:#1f1f1f;">{key} {mode}</h2>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_timeline(timeline):
    """타임라인 리스트 출력 (클릭 시 플레이어 구간 이동)."""
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

        sec = int(row.get("sec") or 0)
        time_label = row.get("time") or format_mmss(sec)
        chord = row.get("chord") or "N"
        lyric = row.get("lyric") or ""
        section = row.get("section") or ""

        c1, c2, c3 = st.columns([1, 1, 6], vertical_alignment="center")
        with c1:
            if st.button(time_label, key=f"seek_{idx}_{sec}", use_container_width=True):
                st.session_state.yt_start_sec = sec
                st.rerun()
        with c2:
            st.markdown(
                f"<div class='chord-badge' style='width:100%; text-align:center;'>{safe_text(chord)}</div>",
                unsafe_allow_html=True,
            )
        with c3:
            section_html = (
                f" <span class='section-tag'>{safe_text(section)}</span>" if section else ""
            )
            st.markdown(
                f"<div class='lyrics-text'>{safe_text(lyric)}{section_html}</div>",
                unsafe_allow_html=True,
            )


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
        manual_lyrics = st.text_area(
            "가사(선택): Genius 토큰이 없으면 여기에 붙여넣기",
            height=120,
            placeholder="가사를 붙여넣으면 타임라인에 함께 표시됩니다.",
        )

        if st.button("분석 시작", type="primary") and search_query:
            st.session_state.yt_url = search_query if is_youtube_url(search_query) else None
            resolved_query = search_query
            if is_youtube_url(search_query):
                yt_title = extract_youtube_title(search_query)
                if yt_title:
                    resolved_query = yt_title
                    st.caption(f"유튜브 제목으로 Spotify 검색: {yt_title}")
                else:
                    st.warning(
                        "유튜브 제목 추출에 실패했습니다. 곡명/아티스트로 입력하면 더 정확합니다."
                    )

            try:
                track_data = get_spotify_data(resolved_query)
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
                    lyrics = (
                        fetch_lyrics(track_data["artist"], track_data["title"])
                        or (manual_lyrics.strip() if manual_lyrics.strip() else None)
                    )

                    analysis = None

                    # 1) (가능하면) 유튜브에서 오디오를 뽑아서 분석(가장 “제대로”)
                    if st.session_state.get("yt_url"):
                        try:
                            wav_path = download_youtube_audio_wav(st.session_state["yt_url"])
                            analysis = analyze_chords_and_timeline_from_audio(wav_path, lyrics)
                        except Exception as e:
                            st.warning(f"유튜브 오디오 분석 실패 → Spotify preview로 폴백합니다. ({e})")
                        finally:
                            # temp 폴더째로 정리
                            if "wav_path" in locals():
                                try:
                                    shutil.rmtree(os.path.dirname(wav_path), ignore_errors=True)
                                except Exception:
                                    pass

                    # 2) 유튜브가 안 되면 Spotify preview(30초)로 폴백
                    if analysis is None:
                        tmp_path = f"preview_{track_data['id'] or 'track'}.mp3"
                        try:
                            _download_preview_mp3(track_data.get("preview_url", ""), tmp_path)
                            analysis = analyze_chords_and_timeline_from_audio(tmp_path, lyrics)
                        except Exception as e:
                            # 캡처2 에러 방지: preview_url이 없으면 여기로 떨어짐
                            st.error(
                                "오디오 분석을 진행할 수 없습니다. (Spotify preview 미제공 + 유튜브 오디오 추출 불가)\n"
                                f"- 원인: {e}\n"
                                "- 해결: Streamlit Cloud에서는 ffmpeg가 없을 수 있어요. Cloud Run(Docker) 배포를 쓰면 해결됩니다."
                            )
                            return
                        finally:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)

                    # Spotify Audio Features가 0/Unknown인 경우에만 오디오 기반 추정값으로 보정
                    if float(track_data.get("bpm") or 0.0) <= 0:
                        track_data["bpm"] = round(float(analysis["tempo"]), 2)
                    if (track_data.get("key") or "Unknown") == "Unknown":
                        track_data["key"] = analysis["key"]
                        track_data["mode"] = analysis["mode"]

                    timeline_data = analysis["timeline"]
                    final_data = {"meta": track_data, "timeline": timeline_data}
                    save_to_firestore(track_data, timeline_data)
                    st.session_state.analyzed_data = final_data

        if st.session_state.analyzed_data:
            # 유튜브 플레이어(가능한 경우)
            yt_url = st.session_state.get("yt_url")
            yt_id = extract_youtube_id(yt_url) if yt_url else None
            if yt_id:
                if "yt_start_sec" not in st.session_state:
                    st.session_state.yt_start_sec = 0
                render_youtube_player(yt_id, int(st.session_state.yt_start_sec or 0))

            render_header(st.session_state.analyzed_data["meta"])
            render_timeline(st.session_state.analyzed_data["timeline"])

    with right_sidebar:
        st.markdown("### 📌 최근 분석된 인기 곡")
        for track in get_recent_tracks():
            st.markdown(f"- {track}")

        st.divider()
        st.markdown("### 🧪 진단")
        with st.expander("분석 환경 점검(yt-dlp/ffmpeg/chordino)", expanded=False):
            st.write(
                {
                    "yt-dlp": "OK" if yt_dlp_available() else "NOT FOUND",
                    "ffmpeg": "OK" if ffmpeg_available() else "NOT FOUND",
                    "librosa": "OK" if librosa is not None else "NOT FOUND",
                    "chordino": "OK" if chordino_available() else "NOT FOUND",
                }
            )
            st.caption(
                "주의: Streamlit Community Cloud는 기본적으로 ffmpeg/Vamp(Chordino)가 없어서 "
                "유튜브 오디오 추출/Chordino 분석이 실패할 수 있습니다. 이 경우 Cloud Run(Docker) 배포가 현실적인 해결책입니다."
            )

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

