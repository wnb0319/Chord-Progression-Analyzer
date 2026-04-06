# 배포 가이드 (외부에서 접속 가능한 사이트)

이 프로젝트는 **2가지 경로**로 배포할 수 있습니다.

## A안) Streamlit Community Cloud (가장 쉬움)

1. GitHub에 새 저장소를 만들고 이 프로젝트를 push 합니다.
2. Streamlit Community Cloud에서 해당 repo를 선택해 배포합니다.
3. Secrets 설정에 아래 값을 등록합니다.
   - `SPOTIFY_CLIENT_ID`
   - `SPOTIFY_CLIENT_SECRET`
   - (선택) `GENIUS_ACCESS_TOKEN`

## B안) Google Cloud Run (권장: 안정적/확장성)

### 0) 사전 준비

- Docker 설치
- Google Cloud CLI(`gcloud`) 설치
- GCP 프로젝트 생성
- 결제 계정 연결(Cloud Run 사용 시 필요할 수 있음)

### 1) 로그인/프로젝트 설정

```bash
gcloud auth login
gcloud config set project <YOUR_GCP_PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

### 2) 배포 (소스에서 바로 빌드/배포)

```bash
cd "/Users/jeon-wonho1/Desktop/Chord Progression Analyzer"
gcloud run deploy chord-analyzer \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars SPOTIFY_CLIENT_ID="...",SPOTIFY_CLIENT_SECRET="..."
```

배포가 끝나면 출력되는 서비스 URL로 접속하면 됩니다.

