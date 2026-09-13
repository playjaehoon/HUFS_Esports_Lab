# PythonAnywhere 배포·복구 가이드

## 확인된 정보와 한계

- 공개 사이트: [hufsesports.pythonanywhere.com](https://hufsesports.pythonanywhere.com/). 2026-09-14 로그인·가입 화면 정상 표시.
- 관리 페이지: [pythonanywhere.com/user/hufsesports](https://www.pythonanywhere.com/user/hufsesports/). 현재 점검 브라우저에서는 로그인 화면으로 이동.
- 저장소: [HUFS_Esports_Lab](https://github.com/playjaehoon/HUFS_Esports_Lab), 분석 기준 `e0681a0`.
- 원본 기본 DB 설정: `sqlite:///esportslab.db`, 일반적으로 앱의 `instance/esportslab.db`. 운영에서 다른 경로로 덮어썼는지는 미확인.

**아래 절차는 인수인계용이며 이번 작업에서 서버 설정·DB·배포를 변경하지 않았습니다.** 실제 경로를 확인하기 전 예시를 그대로 붙여 넣지 않습니다.

## 1. 서버 현황 확보

로그인한 뒤 Web 탭에서 `hufsesports.pythonanywhere.com` 앱을 선택해 다음 항목을 내부 운영 기록에 남깁니다. 비밀값은 문서화하지 않습니다.

| 항목 | 현재 값 |
| --- | --- |
| Source code / Working directory | 확인 필요 |
| Python 버전 / Virtualenv 절대 경로 | 확인 필요 |
| WSGI 파일 경로 / import 대상 | 확인 필요 |
| Static files URL·디렉터리 매핑 | 확인 필요 |
| 실제 SQLite 파일 또는 다른 DB 연결 여부 | 확인 필요 |
| Error log / Server log 경로 | 확인 필요 |
| HTTPS 강제·쿠키 설정 | 확인 필요 |
| 예약 작업·외부 연동·갱신 조건 | 확인 필요 |
| 최근 백업·복구 시험·배포 버전 | 확인 필요 |

소스 폴더에서 `git status --short`, `git rev-parse HEAD`, `git log -5 --oneline`을 확인합니다. Git 저장소가 아니라 업로드한 폴더일 수도 있습니다. 서버만의 수정이 있으면 별도 복사본으로 보존하고 GitHub와 비교한 뒤 통합합니다. 환경변수 전체나 학생 DB를 공개 로그에 출력하지 않습니다.

## 2. 실행 구조를 이해하기

기존 Flask 앱은 PythonAnywhere의 Manual configuration, 같은 Python 버전의 virtualenv, WSGI import와 연결할 수 있습니다. WSGI 연결의 개념 예시는 다음과 같습니다. [PythonAnywhere 공식 Flask 가이드](https://help.pythonanywhere.com/pages/Flask/)

```python
# 실제 Web 탭의 WSGI 파일에 해당하는 개념 예시
import sys

project_path = '/home/hufsesports/ACTUAL_APP_DIRECTORY'  # 실제 경로로 교체
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from app import app as application
```

PythonAnywhere의 Web 앱에서는 `python app.py` 개발 서버를 배포 방식으로 사용하지 않습니다. 현재 `app.run(debug=True)`는 `__main__` 조건 아래 있으므로 WSGI import만으로 debug가 켜진다고 단정할 수는 없습니다.

정적 파일은 `/static/` URL과 실제 `static` 디렉터리의 연결을 확인합니다. 새 가상환경 설치 시에는 해당 환경의 Python으로 `-m pip install -r requirements.txt`를 실행합니다. 기존 환경에서 무작정 업데이트하기 전에 현재 의존성을 기록하고 시험 환경을 사용합니다.

## 3. 보안 설정 개선 후 운영 연결

현재 앱은 키와 DB 주소를 코드에 직접 적습니다. 먼저 앱 초기화 코드에서 환경별 설정을 읽도록 개선해야 합니다. 목표 설정은 `SECRET_KEY`, `DATABASE_URL` 또는 프로젝트에서 정한 DB 설정명, `Asia/Seoul`, 운영 디버그 비활성화, HTTPS 환경의 세션 쿠키 설정입니다.

PythonAnywhere에서는 콘솔 환경과 웹 worker 환경을 함께 고려해야 하며, 환경 설정을 WSGI에서 로드한다면 앱을 import하기 전에 수행합니다. `.env`를 쓰려면 읽기 코드와 의존성·Git 제외가 함께 필요합니다. **`.env` 파일 생성만으로 현재 하드코딩된 값은 바뀌지 않습니다.** [환경변수 공식 가이드](https://help.pythonanywhere.com/pages/EnvironmentVariables/)

운영 키 교체는 기존 세션을 만료시킬 수 있으므로 이용 안내와 배포 시점을 정합니다. 기본 관리자 생성 제거·관리자 비밀번호 재설정·PIN 원문 제거는 코드 변경과 기존 DB 처리를 함께 점검합니다. 과거 백업에 원문 PIN이 남을 수 있으므로 백업 보관·접근·폐기 방식도 기관 기준으로 정합니다.

## 4. 백업과 실제 복구 검증

백업 대상은 DB, 실제 배포 버전, 의존성 목록, 설정 복구 방법입니다. 코드 백업만으로 회원·예약 데이터는 복구되지 않습니다. SQLite 실행 중 단순 파일 복사는 저널 상태를 놓칠 수 있으므로 쓰기 중지 후 복사 또는 SQLite 백업 API를 사용합니다. [SQLite 공식 백업 API 설명](https://www.sqlite.org/backup.html)

다음은 **실제 DB 경로를 확인한 뒤** Python 콘솔/스크립트에서 사용할 SQLite 백업 예시입니다. 이미 있는 백업 파일을 덮어쓰지 않습니다.

```python
from datetime import datetime, timezone
from contextlib import closing
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

백업 디렉터리는 웹 정적 경로·Git 밖에 두고 접근 권한과 보관 기한을 관리합니다. 서버 장애에 대비해 기관이 승인한 별도 보관 위치에도 백업을 유지합니다. `integrity_check`만으로 복구가 검증되지는 않습니다. 별도 시험 환경에서 해당 백업을 열어 스키마·회원/예약 건수·최근 예약 시각과 화면 동작을 확인하고 검증일을 기록합니다.

복구가 필요한 경우 서비스 쓰기를 중지하고 현재 DB도 보존합니다. 복구 시점 이후 데이터가 사라지는 범위를 확인한 뒤 담당자가 복구본·코드 버전을 선택합니다. 앱을 정지한 상태에서 DB와 필요한 파일을 일관되게 교체하고, 재시작 후 예약·관리 기능을 확인합니다. 운영 DB 삭제로 초기화하는 방식을 복구 절차로 사용하지 않습니다.

## 5. 변경 배포 순서

1. PR의 변경 기능, 테스트 결과, 이관 필요 여부, 복구 방법을 검토합니다.
2. 서버의 미커밋 작업과 실제 버전을 확인하고 보존합니다. 예정 점검을 공지합니다.
3. 쓰기가 중지되는 유지보수 상태를 마련하고 DB를 백업합니다. 현재 ‘예약 시스템 비활성화’는 가입·관리 변경까지 막는 유지보수 모드가 아닙니다.
4. 시험 환경에서 동일 스키마의 복사 DB로 마이그레이션과 복구를 검증합니다.
5. 정한 코드 버전·가상환경을 배치하고, 승인된 이관 스크립트를 한 번 실행합니다. `init_db.py`나 `create_all()`을 스키마 업데이트 수단으로 쓰지 않습니다.
6. WSGI·정적 경로를 확인하고 Web 탭에서 Reload합니다.
7. 오류 로그, 로그인, 내 예약, 정상 예약·취소, 학생의 관리 기능 거절, 운영진 체크인을 시험용 계정으로 확인합니다.
8. 상태가 정상일 때 점검을 종료하고 배포 커밋·일시·담당·백업 식별자를 기록합니다.

DB가 바뀌지 않았다면 검증된 이전 코드 버전으로 되돌리는 방식을 검토할 수 있습니다. DB가 바뀌었다면 이전 코드와의 호환성·역마이그레이션 가능 여부를 먼저 확인합니다. 코드만 되돌리면 안전하다고 가정하지 않습니다.

## 증상별 확인 순서

| 증상 | 먼저 확인할 것 |
| --- | --- |
| 500 또는 시작 실패 | Error log의 첫 오류, 가상환경, import, DB 경로·스키마 |
| 로고·CSS 누락 | `/static/` 매핑과 파일 경로·대소문자 |
| 가입 승인 대기 | 현재 원본의 정상 정책인지, 승인 제거 버전 배포 여부 |
| 새 문구가 안 보임 | 서버 커밋, 올바른 앱 Reload 여부, 정적 캐시 |
| 날짜 경계가 이상함 | 서버·브라우저의 시간대, 한국 시간 기준 통일 여부 |
| `no such column` | 적용된 DB 마이그레이션 버전, 다른 DB를 연 것은 아닌지 |
| 예약 성공했는데 학생이 못 찾음 | 현재 내 예약 미구현 여부, 개선 후 계정 FK·소유권 조회 |

검증된 Flask·SQLAlchemy 설정 설명: [SQLAlchemy 상대 SQLite 경로와 create_all의 한계](https://flask-sqlalchemy.palletsprojects.com/en/stable/quickstart/).
