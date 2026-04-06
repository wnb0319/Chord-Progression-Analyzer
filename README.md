# Chord Progression Analyzer (Streamlit)

## 실행 방법

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run App.py
```

## Omnizart(코드 인식) 로컬 실행 (macOS에서 권장: Docker)

Omnizart는 의존성이 오래되어(macOS/Apple Silicon에서 `numba/llvmlite` 빌드가 자주 실패) **로컬 파이썬 venv 설치가 잘 안 되는 경우**가 많습니다.
이럴 때는 로컬 머신 자원을 쓰면서도 의존성 충돌을 피하기 위해 **Docker로 로컬 실행**하는 게 가장 빠릅니다.

```bash
cd "/Users/jeon-wonho1/Desktop/Chord Progression Analyzer"
./run_omnizart_local.sh
```

실행 후 브라우저에서 `http://localhost:8501` 접속 → `로컬 파일(업로드)` 탭에서 Omnizart 체크 후 분석하면 됩니다.

## API 키 설정 (선택)

Streamlit의 `st.secrets` 또는 **환경변수**를 쓰도록 되어 있습니다.

`./.streamlit/secrets.toml` 파일을 만들고 아래처럼 넣으면 됩니다.

```toml
SPOTIFY_CLIENT_ID="..."
SPOTIFY_CLIENT_SECRET="..."
GENIUS_ACCESS_TOKEN="..."
```

또는 환경변수로 설정해도 됩니다(배포 시 권장).

```bash
export SPOTIFY_CLIENT_ID="..."
export SPOTIFY_CLIENT_SECRET="..."
export GENIUS_ACCESS_TOKEN="..."
```

## 참고

- 현재 코드는 **Mock 데이터 기반으로 UI/흐름이 동작**하도록 만들어져 있습니다.
- Spotify/Genius/YouTube/Firebase 실제 연동은 코드 내 주석 블록을 해제해 연결하면 됩니다.

## 배포(외부에서 접속 가능한 사이트 만들기)

이 프로젝트는 `Dockerfile`이 포함되어 있어서 Cloud Run 같은 곳에 바로 올릴 수 있습니다.

### 로컬에서 컨테이너로 실행

```bash
docker build -t chord-analyzer .
docker run -p 8080:8080 \
  -e SPOTIFY_CLIENT_ID="..." \
  -e SPOTIFY_CLIENT_SECRET="..." \
  chord-analyzer
```

### Google Cloud Run에 배포(요약)

```bash
gcloud auth login
gcloud config set project <YOUR_GCP_PROJECT_ID>
gcloud run deploy chord-analyzer \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars SPOTIFY_CLIENT_ID="...",SPOTIFY_CLIENT_SECRET="..."
```

