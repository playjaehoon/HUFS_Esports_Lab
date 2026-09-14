# Philips Evnia Esports Lab

학생 가입, 좌석 예약, 운영진 방문 확인을 위한 Philips Evnia Esports Lab Flask 웹 서비스입니다.

- 서비스: [hufsesports.pythonanywhere.com](https://hufsesports.pythonanywhere.com/)
- 저장소: [playjaehoon/HUFS_Esports_Lab](https://github.com/playjaehoon/HUFS_Esports_Lab)
- 최초 진단 기준: `e0681a0`. 초기 문제의 기록은 [현황 진단](docs/01-audit.md)에 보존합니다.

## 현재 상태

**로컬 개선판**에는 승인 없는 가입, 내 예약 목록·상세·취소, 회원정보·비밀번호 수정, 학생증 확인을 전제로 한 운영진 체크인·이용 종료가 구현되어 있습니다. 역할·예약 소유권 검사, CSRF 방어, 로그인 시도 제한, 비밀번호 해시 저장, 중복 예약을 막는 DB 제약도 추가했습니다.

**운영 사이트는 `f05a5c2`까지 반영됐습니다.** 현재 작업 폴더의 로고·예약 화면·공지 설정 개선은 로컬 검수 중이며 아직 배포하지 않았습니다. 로컬 검증과 남은 작업은 [진행표](docs/07-progress.md), 변경 내역은 [CHANGELOG](CHANGELOG.md)를 기준으로 확인하세요.

이용 흐름: **가입 → 로그인 후 좌석 예약 → 내 예약 확인 → 방문 시 학생증 대조 → 체크인 → 이용 종료**. 로그인 직후에는 좌석 예약 화면을 열고, 내 예약은 상단 메뉴에서 언제든 확인합니다. 웹의 방문 확인은 실제 PC의 로그인·종료를 제어하지 않습니다.

## 인수인계 문서 안내

| 읽는 사람·목적 | 문서 |
| --- | --- |
| 인수인계를 처음 받았을 때 | [여기부터 읽기](docs/00-start-here.md) |
| 지금 어디까지 했는지 먼저 확인 | [현재 진행표](docs/07-progress.md) |
| 후임 개발자가 처음 실행하고 수정 | [개발·인수인계 가이드](docs/04-maintainer-guide.md) |
| 커밋 시점·브랜치·검토·배포 구분 | [Git 작업 규칙](docs/08-git-workflow.md) |
| PythonAnywhere 배포·기존 DB 이관·복구 | [배포 가이드](docs/05-deployment.md) |
| 현재 기술을 유지한 이유와 한계 | [기술 선택 검토](docs/09-technical-decisions.md) |
| 가입·예약·현장 운영의 상세 기준 | [기능·데이터 설계](docs/02-product-spec.md) |
| 화면·브랜드 개선 방향 | [디자인 가이드](docs/03-design-guide.md) |
| 운영 정책·개관 준비 | [개관 체크리스트](docs/06-launch-plan.md) |
| 최초 문제와 재현 근거 | [초기 진단](docs/01-audit.md) |

## 구조

```text
app.py                   PythonAnywhere 호환 진입점
application.py           create_app(), 환경 설정·세션·CSRF·오류 처리
routes.py                학생·관리 HTTP 요청 처리
auth_helpers.py          역할 검사·DB 기반 로그인 시도 제한
booking.py               한국 시간·운영 규칙·예약 트랜잭션
models.py                회원·예약·점유 시간·운영 기록 모델
commands.py              관리자 계정 생성/교체·기존 DB 이관 명령
legacy_import.py         기존 DB를 읽어 별도 새 DB로 이관
migrations/              Alembic 스키마 이력
templates/, static/      Jinja HTML·CSS·좌석 선택 JavaScript
tests/                   가상 계정·격리 DB를 사용하는 회귀 테스트
```

Flask/Jinja + SQLAlchemy + SQLite 구조입니다. 별도 Node 빌드, React 앱, 이메일·SMS 발송, 결제, PC 원격 제어는 없습니다.

## 새 개발 환경에서 시작하기

아래는 **새 로컬 복제본·빈 DB 전용**입니다. 기존 DB가 있다면 [이관 절차](docs/05-deployment.md)를 먼저 읽으세요. 이미 작업 중인 폴더를 다시 clone하거나 덮어쓰지 않습니다.

```powershell
git clone https://github.com/playjaehoon/HUFS_Esports_Lab.git
cd HUFS_Esports_Lab
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

다음 명령은 새 `.env`에 개발 설정과 무작위 키를 기록합니다. 키를 화면에 출력하지 않으며 기존 파일을 덮어쓰지 않습니다. `.env`는 Git 제외 대상입니다.

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; import secrets; p=Path('.env'); f=p.open('x', encoding='utf-8'); f.write('APP_ENV=development\nSECRET_KEY='+secrets.token_urlsafe(48)+'\n'); f.close()"
.\.venv\Scripts\python.exe -m flask --app app db upgrade
.\.venv\Scripts\python.exe -m flask --app app admin-account
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000
```

브라우저에서 `http://127.0.0.1:5000`을 엽니다. 관리자 이름과 12~128자 비밀번호는 명령 프롬프트에서 직접 정합니다. 공개된 기본 관리자 계정을 자동 생성하지 않습니다. 학생은 숫자 6자리 비밀번호로 바로 가입하며, 테스트에는 가상 학번·이름만 사용합니다.

`.env`를 자동으로 읽습니다. `SECRET_KEY`는 32자 이상이어야 하며 누락되면 실행을 거절합니다. 기본 DB는 `instance/esportslab.db`입니다. 운영은 `APP_ENV=production`과 HTTPS를 사용하고, 테스트용 `.env`를 서버에 복사하지 않습니다.

## 작업을 넘기기 전

관련 테스트 → 화면 확인 → `git diff --check` → 변경 파일 검토 → 목적별 커밋 → 진행표 갱신 순서로 마무리합니다. 문서 묶음에는 README·CHANGELOG·`docs/`를 넣고 DB·키·백업을 넣지 않습니다. 커밋, GitHub push, 운영 배포는 각각 별도 단계입니다.

검증된 변경을 커밋한 뒤 다음 명령으로 인수인계 ZIP을 다시 만들 수 있습니다. `--require-clean`은 미커밋 변경이 있으면 생성을 거절합니다.

```powershell
.\.venv\Scripts\python.exe tools\build_handover.py --require-clean
```

출력은 `artifacts/hufs-esports-handover-<commit12>-<contenthash12>.zip`입니다. 압축을 풀고 `index.html`을 열면 안내·통합 가이드·Markdown 원문을 볼 수 있습니다. `manifest.json`에 기준 커밋과 파일 해시가 기록되며 생성 ZIP은 Git에서 제외합니다.

`tools/audit_snapshot.py`와 `docs/audit/2026-09-14.json`은 초기 진단 자료입니다. 변경된 앱의 통과 여부는 `pytest`로 확인하며 초기 진단 도구를 운영 서버에서 실행하지 않습니다.
