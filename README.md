# Philips Evnia Esports Lab

한국외국어대학교 실습실의 학생 가입, 좌석 예약, 운영진 방문 확인을 위한 Flask 웹 서비스입니다. Philips Evnia의 후원으로 개관했다는 운영자 설명을 기준으로 프로젝트 소개를 정리했습니다.

- 서비스: [hufsesports.pythonanywhere.com](https://hufsesports.pythonanywhere.com/)
- 저장소: [playjaehoon/HUFS_Esports_Lab](https://github.com/playjaehoon/HUFS_Esports_Lab)
- 최초 분석 기준: `e0681a0` (2026-03-07), 분석일: 2026-09-14

## 현재 상태

현재 코드는 **가입 승인형 예약 초안**입니다. 학생의 내 예약 조회·취소·정보 수정은 아직 없습니다. 일반 학생의 관리자 접근, PIN 원문 저장 등 개관 전 수정할 문제가 로컬에서 확인됐습니다. 이 문서 추가는 문제 해결이나 운영 배포 완료를 의미하지 않습니다.

목표 흐름은 **승인 없이 가입 → 예약 → 내 예약 확인 → 매 방문 시 학생증 대조 → 체크인 → 이용 종료**입니다. 아래 문서에서 현재 구현과 개선안을 구분합니다.

## 처음 읽을 문서

| 목적 | 문서 |
| --- | --- |
| 무엇이 있고 무엇이 문제인지 | [현황 진단](docs/01-audit.md) |
| 가입·내 예약·정보 수정·현장 확인을 어떻게 바꿀지 | [기능·데이터 설계](docs/02-product-spec.md) |
| 첫 화면·예약 화면·운영 화면을 어떻게 개선할지 | [디자인 가이드](docs/03-design-guide.md) |
| 다른 담당자가 실행하고 수정하는 방법 | [개발·인수인계 가이드](docs/04-maintainer-guide.md) |
| PythonAnywhere 설정 확인·배포·복구 | [배포 가이드](docs/05-deployment.md) |
| 오픈 전 준비와 구현 순서 | [개관 체크리스트·로드맵](docs/06-launch-plan.md) |

## 구조

```text
학생/운영진 브라우저
  ├─ Jinja HTML: templates/
  ├─ CSS·좌석 선택 JavaScript: static/
  └─ Flask 라우트·인증·예약 규칙: app.py
          └─ SQLAlchemy 모델: models.py
                  └─ SQLite: instance/esportslab.db (Git에 없음)
```

별도 React 앱, Node 빌드, 이메일·SMS 발송, 결제, PC 원격 제어는 현재 저장소에 없습니다. 웹의 방문 확인은 실제 PC의 로그인·종료를 제어하지 않습니다.

## 로컬에서 시작하기

새 로컬 복제본에서 Python 3.11 가상환경을 사용합니다. 아래 명령은 운영 서버용이 아닙니다. 초기화 스크립트는 코드에 공개된 기본 관리자 계정을 생성하므로 그대로 외부에 공개하면 안 됩니다.

```powershell
git clone https://github.com/playjaehoon/HUFS_Esports_Lab.git
cd HUFS_Esports_Lab
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe init_db.py
.\venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000
```

브라우저에서 `http://127.0.0.1:5000`을 엽니다. 승인 전 학생은 로그인할 수 없는 현재 동작을 감안해야 합니다. 운영 DB를 복사해 연습하지 말고 가상 학생만 사용하세요.

## 진단 재현

```powershell
.\venv\Scripts\python.exe tools\audit_snapshot.py
```

이 도구는 필요한 코드를 임시 폴더에 복사하고 가상 데이터로 Flask 테스트 클라이언트를 실행합니다. 서비스 주소에 요청하지 않으며 기존 DB를 사용하지 않습니다. [2026-09-14 결과](docs/audit/2026-09-14.json)는 기존 문제를 기록한 것이며, 정상 동작을 보증하는 통과 테스트가 아닙니다.
