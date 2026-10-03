"""Global Campus admission units and departments with enrolled students."""

DEPARTMENT_GROUPS = (
    ('단과대학·계열 통합모집', (
        '인문대학[통합모집]', '국가전략언어계열', '경상대학[통합모집]',
        '자연과학대학[통합모집]', '공과계열',
        'Culture & Technology융합대학[통합모집]', 'AI융합대학[통합모집]')),
    ('인문대학', ('철학과', '사학과', '언어인지과학과', '지식콘텐츠학부')),
    ('통번역대학', ('영어통번역학부', '독일어통번역학과', '스페인어통번역학과',
                '이탈리아어통번역학과', '중국어통번역학과', '일본어통번역학과',
                '아랍어통번역학과', '말레이·인도네시아어통번역학과', '태국어통번역학과')),
    ('국가전략언어대학·국제지역대학', (
        '폴란드학과', '루마니아학과', '체코·슬로바키아학과', '헝가리학과',
        '세르비아·크로아티아학과', '그리스·불가리아학과', '중앙아시아학과',
        '아프리카학부', '우크라이나학과', '한국학과', '프랑스학과', '브라질학과',
        '인도학과', '러시아학과')),
    ('경상대학', ('Global Business & Technology학부', '국제금융학과')),
    ('자연과학대학', ('수학과', '통계학과', '전자물리학과', '환경학과', '생명공학과', '화학과')),
    ('공과대학', ('컴퓨터공학부', '정보통신공학과', '반도체전자공학부',
               '반도체전자공학부(반도체공학전공)', '반도체전자공학부(전자공학전공)',
               '산업경영공학과')),
    ('융합인재대학', ('융합인재학부',)),
    ('Culture & Technology융합대학', ('디지털콘텐츠학부', '투어리즘 & 웰니스학부',
                                  '글로벌스포츠산업학부')),
    ('AI융합대학', ('AI데이터융합학부', 'Finance & AI융합학부')),
    ('독립학부', ('바이오메디컬공학부', '기후변화융합학부')),
    ('자유전공학부', ('자유전공학부(글로벌)',)),
)

OTHER_CHOICES = ('목록에 없는 학과', '서울캠퍼스 학과')
DEPARTMENTS = frozenset(name for _, names in DEPARTMENT_GROUPS for name in names)


def selected_department(value, other=None):
    from booking import RuleError

    if value in DEPARTMENTS:
        return value
    if value in OTHER_CHOICES:
        name = (other or '').strip()
        result = f'{value}: {name}'
        if not name or len(result) > 100 or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise RuleError('학과명을 100자 이내로 직접 입력해 주세요.')
        return result
    raise RuleError('학과를 목록에서 선택해 주세요.')


def department_form_value(stored):
    """Return select value and free-text field for an existing profile."""
    if stored in DEPARTMENTS:
        return stored, ''
    for choice in OTHER_CHOICES:
        prefix = f'{choice}: '
        if stored and stored.startswith(prefix):
            return choice, stored[len(prefix):]
    # Legacy/non-catalog values remain editable rather than vanishing from the form.
    return ('목록에 없는 학과', stored) if stored else ('', '')
