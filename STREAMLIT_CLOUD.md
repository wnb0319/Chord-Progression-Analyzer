## Streamlit Community Cloud 배포 절차 (A안)

### 1) GitHub에 올리기

이 폴더(`/Users/jeon-wonho1/Desktop/Chord Progression Analyzer`)를 GitHub 저장소로 push 해야 합니다.

현재 PC에 GitHub CLI(`gh`)가 없어서 자동으로 repo 생성/로그인을 진행할 수 없습니다.
아래 중 하나로 진행하세요.

#### 방법 A: GitHub 웹에서 repo 생성 후, 터미널로 push

1. GitHub에서 새 repo 생성 (Public/Private 아무거나)
2. 생성된 repo의 URL을 복사 (예: `https://github.com/<USER>/<REPO>.git`)
3. 아래 명령 실행

```bash
cd "/Users/jeon-wonho1/Desktop/Chord Progression Analyzer"
git add .
git commit -m "Initial commit: Streamlit app"
git branch -M main
git remote add origin <REPO_URL>
git push -u origin main
```

#### 방법 B: GitHub Desktop 사용

- GitHub Desktop에서 “Add Existing Repository” → Publish Repository

#### 방법 C: SSH 키로 push (권장)

이 PC에서 SSH 키를 새로 만들었다면, GitHub에 공개키를 등록해야 push가 됩니다.

1. GitHub → Settings → SSH and GPG keys → New SSH key
2. 아래 공개키를 그대로 등록

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIOxozHx1bLxXrQ00AudJuO3fDmtaL3CPWEP8iVO6BlD wnb0319@github
```

3. 그 다음 터미널에서 push

```bash
cd "/Users/jeon-wonho1/Desktop/Chord Progression Analyzer"
git remote set-url origin git@github.com:wnb0319/Chord-Progression-Analyzer.git
git push -u origin main
```

### 2) Streamlit Cloud에서 배포

1. Streamlit Community Cloud 접속 후 “New app”
2. GitHub repo 선택
3. Main file path는 `App.py`로 설정
4. Deploy 클릭

### 3) Secrets 설정 (매우 중요)

배포된 앱의 Settings → Secrets에 아래를 추가합니다.

```toml
SPOTIFY_CLIENT_ID="..."
SPOTIFY_CLIENT_SECRET="..."
GENIUS_ACCESS_TOKEN="..." # 선택
```

