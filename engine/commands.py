import re


def interpret(p, text):
    if not isinstance(text,str) or len(text)>500:
        raise ValueError("수정 요청은 500자 이내로 입력해 주세요.")
    compact=re.sub(r"\s+","",text)
    if re.search(r"자막.*(크게|키워|확대)",compact):
        return {"settings":{"fontSize":min(100,p["settings"]["fontSize"]+8)}},"자막 크기를 키웠습니다. 다시 출력하면 반영됩니다."
    if re.search(r"자막.*(작게|줄여|축소)",compact):
        return {"settings":{"fontSize":max(18,p["settings"]["fontSize"]-8)}},"자막 크기를 줄였습니다."
    if re.search(r"(줌|확대).*(줄여|끄|없애)",compact):
        return {"settings":{"zoom":1.0}},"줌 효과를 껐습니다."
    if re.search(r"(잘라낸|삭제|대화).*(살려|복원|되돌려)",compact):
        return {"cuts":[{**c,"enabled":False} for c in p["cuts"]]},"삭제 구간을 모두 복원했습니다."
    if re.search(r"(빠르게|침묵.*(더|제거)|무음.*(더|제거))",compact):
        return {"style":"fast","settings":{"zoom":1.08}},"빠른 편집 모드로 바꿨습니다. ‘분석·편집점 생성’을 다시 누르면 침묵 기준을 새로 적용합니다. 수동 변경은 재분석 시 초기화됩니다."
    raise ValueError("지원하는 요청: ‘편집을 더 빠르게’, ‘잘라낸 대화를 살려줘’, ‘자막을 크게/작게’, ‘줌 효과를 줄여줘’. 자유로운 문장 해석은 아직 지원하지 않습니다.")
