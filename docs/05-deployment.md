# PythonAnywhere 배포·이관·복구 가이드

이 문서는 **로컬 개선판을 앞으로 배포하는 절차**입니다. 이번 작업에서는 운영 서버·DB·설정을 변경하지 않았습니다. 실제 서버에 로그인해 경로와 스키마를 확인하기 전에는 아래 예시를 그대로 실행하지 않습니다.

## 먼저 확보할 운영 정보

- 공개 사이트: [hufsesports.pythonanywhere.com](https://hufsesports.pythonanywhere.com/)
- 관리 페이지: [PythonAnywhere hufsesports](https://www.pythonanywhere.com/user/hufsesports/). 현재 점검 환경에서는 로그인 필요.
- 초기 진단 소스: `e0681a0`. 실제 운영 버전과 일치하는지는 미확인.

| 내부 운영 기록에 남길 항목 | 현재 상태 |
| --- | --- |
| 소스·Working directory·실제 배포 커밋 | 확인 필요 |
| Python 버전·virtualenv 절대 경로 | 확인 필요 |
| WSGI 파일·import 대상·정적 파일 매핑 | 확인 필요 |
| 실제 DB 경로·스키마·원본 시각의 시간대 | 확인 필요 |
| 로그 경로·HTTPS·예약 작업·외부 서비스 | 확인 필요 |
| 백업 위치·보관 주기·복구 검증일·담당자 | 확인 필요 |

서버 소스 폴더의 `git status --short`, `git rev-parse HEAD`, `git log -5 --oneline`을 확인합니다. Git 저장소가 아닌 업로드 폴더일 수도 있습니다. 서버에서만 바꾼 파일과 Antigravity 미업로드 자료는 별도 보존한 뒤 비교합니다. 환경변수 전체와 학생 데이터는 로그·문서에 출력하지 않습니다.

## 운영 설정과 WSGI

새 코드의 `application.py`는 프로젝트 `.env`를 읽고 `SECRET_KEY`, `DATABASE_URL`, `APP_ENV`를 사용합니다. 운영용 무작위 키는 별도로 생성해 비공개 설정에 저장하며 **32자 미만 또는 누락 시 앱이 시작되지 않습니다.** 키 변경 시 기존 로그인 세션이 만료됩니다.

| 설정 | 운영 기준 |
| --- | --- |
| `APP_ENV` | `production` (생략해도 보안 쿠키 기본 활성화) |
| `SECRET_KEY` | 비공개 무작위 키. Git·화면·로그에 출력하지 않음 |
| `DATABASE_URL` | 확인한 SQLite 절대 경로. 다른 DB 엔진은 현재 거절 |
| 개발 설정 | `APP_ENV=development`는 로컬 HTTP 연습에만 사용 |

운영 의존성은 별도 virtualenv에 `python -m pip install -r requirements.txt`로 설치합니다. Python 버전은 로컬 검증 환경과 서버 지원 범위를 함께 확인합니다. PythonAnywhere는 virtualenv·WSGI 연결 방식으로 Flask를 실행합니다. [공식 Flask 배포 안내](https://help.pythonanywhere.com/pages/Flask/)

```python
# 실제 Web 탭의 WSGI 파일에 맞춰 경로를 교체하는 예시
import sys

project_path = '/home/hufsesports/ACTUAL_APP_DIRECTORY'
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from app import app as application
```

`app.py` 호환 진입점은 유지했습니다. `.env`는 `create_app()`에서 읽습니다. 이미 설정된 환경변수는 `.env`보다 우선하므로 콘솔과 웹 worker의 설정을 비교할 때 **값을 노출하지 않고** 설정 출처·DB 대상이 같은지 확인합니다. `/static/`과 실제 `static` 폴더 연결도 확인합니다. [PythonAnywhere 환경변수 안내](https://help.pythonanywhere.com/pages/EnvironmentVariables/)

`python app.py`나 `flask run` 개발 서버로 운영하지 않습니다. Flask의 개발 서버는 운영용 안정성·보안을 목적으로 제공되지 않습니다. [Flask 운영 배포 안내](https://flask.palletsprojects.com/en/stable/deploying/)

## 새 DB와 기존 DB의 경로 구분

| DB 상태 | 사용할 절차 |
| --- | --- |
| 새 시험 환경의 빈 DB | `python -m flask --app app db upgrade` 후 `admin-account` |
| 초기 승인형 스키마의 기존 DB | 아래 `import-legacy`로 **별도 새 파일** 생성 |
| 이미 새 스키마로 이관한 DB | 현재 revision 확인 후, 검토된 이후 Alembic 변경만 적용 |
| 서버가 수정한 알 수 없는 스키마 | 중지하고 테이블·컬럼·데이터 규칙을 먼저 대조 |

초기 Alembic revision `0001`은 **빈 DB 전용**이며 기존 테이블이 있으면 거절합니다. 운영 DB에 `create_all()`, `init_db.py`, `flask db stamp head`를 실행해 변환을 생략하지 않습니다. `0001`의 downgrade는 테이블을 제거하므로 운영 복구 명령으로 사용하지 않습니다.

### 기존 초기 DB를 옮기는 순서

1. 쓰기를 멈출 점검 시간을 정하고, 실제 DB를 일관된 백업으로 보존합니다. 예약 접수 끄기는 가입·정보 수정·관리 변경을 막지 않으므로 전체 쓰기 중지 대책이 따로 필요합니다.
2. 별도 시험 환경에 **백업 복사본**을 준비합니다. 원본 서버에서 `blocked_until`의 기준 시간대가 한국 시간인지 UTC인지 확인합니다. 임의로 추측하지 않습니다.
3. 새 코드·의존성·비공개 `.env`를 준비하고, 출력 DB의 부모 폴더를 먼저 만듭니다. 출력 파일은 기존 파일을 지정하면 안 됩니다.
4. 아래 이관 명령을 실행합니다. 예시는 원본 시간대가 한국 시간임을 확인한 경우입니다.

```bash
python -m flask --app app import-legacy \
  --source /PRIVATE_BACKUP_DIRECTORY/legacy-snapshot.db \
  --output /PRIVATE_TEST_DIRECTORY/esportslab-upgraded.db \
  --legacy-timezone Asia/Seoul
```

5. 이관된 회원·관리자·예약 건수, 예약 소유자, 활성 예약의 좌석/일일 제약, 제한 만료 시각, 운영 설정을 확인합니다. `integrity_check`·외래키 검증에 더해 화면 기능과 최근 예약을 확인합니다.
6. 새 DB를 사용하는 시험 앱에서 기존 학생이 로그인 후 숫자 6자리 비밀번호 변경으로 안내되는지 확인합니다. 원문 PIN은 새 스키마에 없습니다. 기존 해시만 옮기며 공개 초기 관리자 비밀번호는 로그인을 거절합니다.
7. `python -m flask --app app admin-account`의 비공개 프롬프트로 운영진별 계정을 만들거나 기존 비밀번호를 바꿉니다. 계정 교체 시 기존 관리자 세션은 무효화됩니다.
8. 운영 쓰기를 중지한 상태에서 최종 백업으로 이관을 다시 검증하고, 확정한 새 DB의 절대 경로를 `DATABASE_URL`로 연결합니다. WSGI Reload 후 아래 점검을 수행합니다.

이관기는 원본을 읽기 전용으로 열고, 원문 PIN을 조회·복사하지 않습니다. 알 수 없는 스키마, 주인 없는 예약, 중복 학번, 겹치는 활성 예약, 잘못된 운영 설정은 자동 정리하지 않고 실패합니다. 실패 사유에 따라 원본 백업을 보존한 채 별도 정리 절차를 검토합니다. 출력은 검증 후 새 파일로만 생성되므로 운영 원본을 덮어쓰지 않습니다.

원본 DB와 과거 백업에는 **기존 원문 PIN이 여전히 남을 수 있습니다.** 원본을 읽기 전용으로 보존하는 것과 비밀정보 삭제는 다른 작업입니다. 백업은 웹·Git 밖에서 접근·보관 기한을 관리하고, 기관의 보관 정책에 따라 폐기합니다. 새 DB에는 현재 학번의 소유권을 기록하며 이후 학번 변경 시 과거 번호도 같은 회원에 귀속합니다.

## 백업과 복구 연습

코드만 백업하면 회원·예약 데이터는 복구되지 않습니다. DB·배포 커밋·의존성·설정 복구 방법을 함께 관리합니다. SQLite 실행 중 파일 단순 복사는 저널 상태를 놓칠 수 있어, 쓰기 중지 후 복사 또는 SQLite 백업 API를 사용합니다. [SQLite 백업 API](https://www.sqlite.org/backup.html)

다음 예시의 경로는 실제 확인 후 교체합니다. 이미 있는 백업 파일은 덮어쓰지 않습니다.

```python
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

source = Path('/home/hufsesports/ACTUAL_APP_DIRECTORY/instance/esportslab.db')
backup_dir = Path('/home/hufsesports/PRIVATE_BACKUP_DIRECTORY')
if not source.is_file():
    raise FileNotFoundError(source)
backup_dir.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
destination = backup_dir / f'esportslab-{stamp}.db'
with destination.open('xb'):
    pass
with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
    with closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
        assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
```

백업은 웹 정적 경로·Git 밖에서 보관하고 기관이 승인한 별도 위치에도 유지합니다. 별도 시험 환경에서 DB를 열어 스키마·건수·예약 화면·로그인까지 검증하고 복구 시험일을 남깁니다.

복구 시에는 쓰기를 중지하고 현재 DB도 보존합니다. 복구 시점 이후 사라질 데이터 범위를 확인한 뒤 이전 코드와 호환되는 DB를 함께 선택합니다. 초기 이관의 복구는 보존한 원본 DB·이전 코드·설정으로 되돌리는 방식이며, 새 스키마 DB에 이전 코드만 연결하지 않습니다.

## 배포 완료 확인과 기록

1. 검토한 커밋·테스트·마이그레이션·복구 계획을 확인하고 점검을 공지합니다.
2. 서버만의 변경을 보존하고 전체 쓰기 중지·DB 백업·시험 이관을 완료합니다.
3. 검증된 코드·가상환경·DB·설정을 연결한 뒤 Web 탭에서 Reload합니다.
4. 오류 로그, HTTPS 로그인, 승인 없는 가입, 내 예약·상세·취소·정보 수정, 학생의 관리자 접근 거절, 운영진 체크인·종료를 시험 계정으로 확인합니다.
5. 정상일 때 점검을 종료하고 배포 커밋·일시·담당·스키마 revision·백업 식별자·점검 결과를 비공개 운영 기록과 [진행표](07-progress.md)에 남깁니다.

| 증상 | 먼저 확인할 것 |
| --- | --- |
| 앱 시작 실패 | `SECRET_KEY` 설정·가상환경·import·DB 경로·revision |
| 로그인 직후 로그아웃됨 | 로컬 HTTP에 운영 보안 쿠키를 켰는지, 운영 HTTPS 상태 |
| 400·유효 시간 안내 | 화면 새로고침·CSRF 토큰·세션 키 변경 여부 |
| 429 | 15분 로그인 시도 제한. proxy IP 설정은 검증 없이 바꾸지 않음 |
| 503·DB 잠금 | 마이그레이션 누락·실제 DB 경로·동시 쓰기·긴 트랜잭션 |
| 화면이 예전 그대로 | 실제 배포 커밋·올바른 Web 앱 Reload·정적 파일 매핑 |
| 예약 목록에 없음 | 로그인 계정·예약 소유권·이관 건수·배포 버전 |
