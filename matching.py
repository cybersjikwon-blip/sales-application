# -*- coding: utf-8 -*-
"""
matching.py
주문내역의 "상품명 + 옵션명"과 품목관리에 등록된 "품목명"을 비교해서
가장 비슷한 품목을 자동으로 연결(매칭)하는 모듈.

마켓 엑셀의 '상품명'은 대표상품명(예: "비닐봉투")만 있고, 실제 세부 규격은
'옵션' 컬럼(예: "14) 100*120cm")에 있는 경우가 많아서, 두 값을 합친 문자열을
기준으로 매칭합니다.
"""
import re
import difflib

import database as db

MATCH_THRESHOLD = 0.55  # 이 값 이상일 때만 자동 매칭으로 인정


def _normalize(s):
    """공백/괄호/특수문자를 없애고 소문자로 통일해서 비교 정확도를 높임"""
    if not s:
        return ""
    s = str(s).lower()
    s = re.sub(r"\s+", "", s)
    return s


def _strip_option_label(s):
    """스마트스토어 등 마켓의 옵션 텍스트에 흔히 붙는 라벨 프리픽스를 제거.
    예: '제품선택: 11) 도매 48cm80cm' -> '11) 도매 48cm80cm'
        '색상: 블랙' -> '블랙'
    라벨 패턴: 한글/영문/숫자 1~12자 + 콜론(: 또는 ：) + 공백"""
    if not s:
        return ""
    s = str(s).strip()
    s = re.sub(r"^[\w가-힣]{1,12}\s*[:：]\s*", "", s)
    return s


def _extract_numbers(s):
    """옵션 텍스트에서 숫자 스펙(구수/길이/전류 등)만 추출.
    마켓마다 옵션 표기 형식이 완전히 달라도(예: "3구접지 2.5M" vs
    "3구 개별절전(10A),길이:2.5M") 핵심 숫자만 비교하면 같은 규격임을 알 수 있음"""
    if not s:
        return set()
    return set(re.findall(r"\d+(?:\.\d+)?", str(s)))


def _extract_letters(s):
    """옵션 텍스트에서 숫자/기호를 제거한 순수 한글·영문 설명 부분만 추출.
    "3구 개별절전(10A)"와 "3구 접지(10A)"처럼 숫자 스펙은 같아도 실제로는
    전혀 다른 상품(개별절전 스위치 유무 등)인 경우를 구분하기 위해 사용"""
    if not s:
        return ""
    return re.sub(r"[\d\.\(\)\,:：\s\-/·;~]+", "", str(s)).lower()


_INDEX_PREFIX = re.compile(r"^\s*\d+(?:\s*[-.]\s*\d+)*\s*[\)\].:]\s*")


def _option_spec_numbers(s):
    """옵션에서 규격 숫자만 뽑음.
    앞에 붙는 마켓 순번('13-1)', '12)')은 규격이 아니므로 빼고 셈"""
    if not s:
        return set()
    t = _INDEX_PREFIX.sub("", str(s).strip())
    out = set()
    for n in re.findall(r"\d*\.?\d+", t):
        try:
            out.add(float(n))
        except ValueError:
            continue
    return out


def _loose(s):
    """괄호·구분기호·공백을 뺀 비교용 문자열.
    마켓마다 옵션 표기가 '70cm100cm 0.06' / '70cm100cm(0.06)' 처럼 달라서,
    이런 표기 차이 때문에 더 정확한 품목이 밀려나는 걸 막기 위함"""
    return re.sub(r"[()\[\]{}<>·,/|_\-\s]", "", str(s or "").lower())


# 구성품 이름이 아니라 '덤'을 뜻하는 표시어들 (구성품 비교에서 제외)
_COMBO_NOISE = ("사은품", "증정", "무료", "서비스", "덤")


def _option_tokens(s):
    """조합(세트) 옵션을 구성품 단위로 쪼갬.
    '파채기계+갈릭커터+핀셋(사은품)' -> {'파채기계', '갈릭커터', '핀셋'}

    조합상품은 구성품을 '+'로 이어 적는데, 구성품 이름이 조금씩 달라서
    ('갈릭커터' vs '갈릭커터기') 통짜 문자열 비교로는 조합상품을 못 찾고
    단품으로 잘못 잡히는 문제가 있었음."""
    if not s:
        return set()
    t = _INDEX_PREFIX.sub("", _strip_option_label(s).strip())
    t = re.sub(r"\(.*?\)", "", t)          # (사은품) 같은 괄호 표기 제외
    tokens = {_normalize(x) for x in t.split("+") if _normalize(x)}
    # 괄호 없이 '핀셋 사은품' 처럼 적힌 경우도 대비해 표시어를 떼어냄
    cleaned = set()
    for tk in tokens:
        for noise in _COMBO_NOISE:
            tk = tk.replace(noise, "")
        if tk:
            cleaned.add(tk)
    return cleaned or tokens


def _combo_score(product_option, order_option):
    """조합(세트) 옵션끼리 구성품 단위로 비교한 점수.
    '+'가 들어간 옵션에서만 동작하므로 일반 단품 매칭에는 영향이 없음.
    반환: 0.0 이면 해당 없음"""
    p_tokens = _option_tokens(product_option)
    o_tokens = _option_tokens(order_option)
    if not p_tokens or not o_tokens:
        return 0.0
    if len(p_tokens) < 2 and len(o_tokens) < 2:
        return 0.0                          # 둘 다 단품이면 기존 방식 그대로

    def _has_partner(token, others):
        return any(token in o or o in token for o in others)

    matched_p = sum(1 for t in p_tokens if _has_partner(t, o_tokens))
    matched_o = sum(1 for t in o_tokens if _has_partner(t, p_tokens))
    cov_p = matched_p / len(p_tokens)
    cov_o = matched_o / len(o_tokens)
    if not cov_p or not cov_o:
        return 0.0
    # 양쪽 구성품이 모두 채워져야 높은 점수 (구성품 수가 다르면 자연히 낮아짐)
    return 0.55 + 0.42 * (cov_p * cov_o)


def _spec_adjust(product_option, order_option):
    """규격 숫자가 정확히 맞는 품목이 확실히 이기도록 하는 미세 보정.

    '70*100cm'와 '70*100cm 0.06'처럼 두께 숫자 하나로 갈리는 경우,
    기존에는 두 후보의 점수 차가 0.001밖에 안 나서 엉뚱한 쪽이 잡히곤 했음.
    (주문 옵션에 0.06이 있는데도 0.06 없는 품목이 출고로 잡히는 문제)

    옵션이 서로 포함관계일 때만 호출되므로, 표기 형식이 아예 다른
    멀티탭 같은 품목의 기존 매칭에는 영향을 주지 않음."""
    p_spec = _option_spec_numbers(product_option)
    o_spec = _option_spec_numbers(order_option)
    if not p_spec or not o_spec:
        return 0.0
    if p_spec == o_spec:
        return 0.02                              # 규격이 정확히 일치
    if p_spec < o_spec:
        return -0.03 * len(o_spec - p_spec)      # 주문에 있는 두께 등이 품목엔 없음
    if o_spec < p_spec:
        return -0.02 * len(p_spec - o_spec)      # 품목이 주문보다 규격이 더 많음
    return 0.0


def find_best_match(order_product_name, order_option_name, products):
    """
    products: [{"id":.., "name":..}, ...] 형태(또는 sqlite3.Row 리스트)
    반환: (product_id or None, score)
    """
    cleaned_option = _strip_option_label(order_option_name)
    option_norm = _normalize(cleaned_option)
    combined = f"{order_product_name or ''} {cleaned_option}".strip()
    combined_norm = _normalize(combined)
    order_name_norm = _normalize(order_product_name)

    if not combined_norm:
        return None, 0.0

    best_id = None
    best_score = 0.0

    for p in products:
        # 품목의 "상품명(대분류) + 옵션(소분류)" 조합을 매칭 기준으로 사용
        # 미리 계산해둔 값이 있으면 그대로 사용 (없으면 그때 계산)
        if isinstance(p, dict) and "_full_norm" in p:
            product_option = p["option_name"]
            product_name_norm = p["_name_norm"]
            product_option_norm = p["_option_norm"]
            pname_norm = p["_full_norm"]
        else:
            product_option = ""
            try:
                product_option = p["option_name"] or ""
            except (IndexError, KeyError):
                pass
            product_name_norm = _normalize(p["name"])
            product_option_norm = _normalize(product_option)
            pname_norm = _normalize(f"{p['name']} {product_option}".strip())
        if not pname_norm:
            continue

        # 완전 일치 우선순위: 1) 옵션(라벨 제거 후) 단독 일치, 2) 상품명+옵션 조합, 3) 상품명 단독
        if pname_norm == option_norm or pname_norm == combined_norm or pname_norm == order_name_norm:
            return p["id"], 1.0

        score = difflib.SequenceMatcher(None, pname_norm, combined_norm).ratio()

        # 조합(세트) 상품은 구성품 단위로 먼저 비교
        combo = _combo_score(product_option, cleaned_option)
        if combo:
            score = max(score, combo)

        if product_option_norm:
            # 품목에 옵션(소분류)이 있는 경우: 마켓의 "상품명" 필드는 보통 긴 마케팅용
            # 문구라서 "품목명+옵션"이 통짜로 그 안에 들어있지 않은 경우가 흔함
            # (예: "비닐봉투 김장 대형 이삿짐..." 안에 "비닐봉투100cm150cm"가
            # 연속된 문자열로 존재하지 않음 - 옵션은 별도 필드에 있기 때문).
            # 그래서 "품목의 옵션"과 "품목의 상품명"을 각각 따로 비교함.
            # 괄호/구분기호를 뺀 형태로 비교 ('70cm100cm(0.06)' == '70cm100cm 0.06')
            opt_loose = _loose(cleaned_option)
            p_opt_loose = _loose(product_option)
            # 주문 옵션이 비어있으면 포함관계를 따질 수 없음.
            # (빈 문자열은 모든 문자열의 부분이라, 예전엔 모든 품목이 똑같이 0.7점을 받아
            #  엉뚱한 품목이 먼저 걸리는 문제가 있었음)
            option_contains = bool(opt_loose) and bool(p_opt_loose) and (
                p_opt_loose in opt_loose or opt_loose in p_opt_loose)
            name_contains = product_name_norm in order_name_norm or order_name_norm in product_name_norm
            if option_contains and name_contains:
                # 옵션끼리의 유사도로 점수를 세분화 (예: "70cm100cm"이 "70cm100cm 0.06"의
                # 부분집합이라 둘 다 포함관계가 걸릴 때, 더 완전히 일치하는 쪽이 이기도록)
                option_ratio = difflib.SequenceMatcher(None, p_opt_loose, opt_loose).ratio()
                score = max(score, 0.8 + 0.19 * option_ratio)
                # 규격 숫자(두께 0.06 등)까지 정확히 맞는 품목이 확실히 이기도록 미세 보정
                score = min(1.0, score + _spec_adjust(product_option, cleaned_option))
            elif option_contains:
                # 옵션은 맞는데 상품명 쪽이 다른 경우(마켓 상품명이 마케팅 문구라 흔함).
                # 대분류가 다른 물건일 수도 있으니 낮은 신뢰도로만 인정하되,
                # 예전처럼 0.7 고정이면 '70cm100cm'와 '70cm100cm 0.06'이 동점이 되어
                # 먼저 걸린 쪽이 잡히므로, 옵션 유사도와 규격으로 우열을 가림
                option_ratio = difflib.SequenceMatcher(None, p_opt_loose, opt_loose).ratio()
                score = max(score, 0.62 + 0.13 * option_ratio)
                score = min(1.0, score + _spec_adjust(product_option, cleaned_option))
            else:
                # 옵션 표기 형식 자체가 완전히 다른 경우(예: "3구접지 2.5M" vs
                # "3구 개별절전(10A),길이:2.5M") - 핵심 숫자 스펙을 비교하되,
                # 반드시 설명 단어(개별절전/접지 등)도 겹쳐야만 인정함
                # (숫자만 같고 종류가 다른 상품을 혼동하는 걸 방지)
                product_numbers = _extract_numbers(product_option)
                order_numbers = _extract_numbers(option_norm)
                product_letters = _extract_letters(product_option)
                order_letters = _extract_letters(cleaned_option)
                letters_ratio = (
                    difflib.SequenceMatcher(None, product_letters, order_letters).ratio()
                    if product_letters and order_letters else 0.0
                )
                if (product_numbers and order_numbers
                        and product_numbers.issubset(order_numbers) and name_contains
                        and letters_ratio >= 0.6):
                    score = max(score, 0.75)

        # 기존 포함관계 체크도 유지 (하위호환 - 옵션 없이 상품명만 있는 품목 등)
        if pname_norm in combined_norm or combined_norm in pname_norm or pname_norm in option_norm:
            score = max(score, 0.85)

        if score > best_score:
            best_score = score
            best_id = p["id"]

    if best_score >= MATCH_THRESHOLD:
        return best_id, best_score
    return None, best_score


def _prepare_products(products):
    """품목의 정규화 문자열을 미리 한 번만 계산해둠.
    (주문마다 전체 품목을 다시 정규화하면 건수가 많을 때 매우 느려짐)"""
    prepared = []
    for p in products:
        option = ""
        try:
            option = p["option_name"] or ""
        except (IndexError, KeyError):
            pass
        prepared.append({
            "id": p["id"],
            "name": p["name"],
            "option_name": option,
            "_name_norm": _normalize(p["name"]),
            "_option_norm": _normalize(option),
            "_full_norm": _normalize(f"{p['name']} {option}".strip()),
            "_option_letters": _extract_letters(option),
            "_option_numbers": _extract_numbers(option),
        })
    return prepared


def rematch_all_orders():
    """
    모든 주문에 대해 현재 등록된 품목들과 다시 매칭을 수행하고 DB에 반영.
    품목을 새로 등록/수정한 뒤 이 함수를 호출하면 매칭이 갱신됩니다.
    매칭 후에는 각 주문의 재고 반영 상태도 함께 동기화됨(자동 재고차감).
    반환: (matched_count, unmatched_count)
    """
    products = _prepare_products(db.get_products())
    orders = db.get_orders_for_matching()
    match_cache = {}   # (상품명, 옵션명) -> 매칭된 품목 id (같은 조합 반복 계산 방지)
    updates = {}
    matched_count = 0
    unmatched_count = 0

    for o in orders:
        cache_key = (o["product_name"] or "", o["option_name"] or "")
        if cache_key in match_cache:
            product_id = match_cache[cache_key]
        else:
            product_id = (find_best_match(o["product_name"], o["option_name"], products)[0]
                          if products else None)
            match_cache[cache_key] = product_id
        if product_id != o["matched_product_id"]:
            updates[o["id"]] = product_id
        if product_id:
            matched_count += 1
        else:
            unmatched_count += 1

    if updates:
        db.bulk_update_matches(updates)

    # 매칭 결과(및 수량 변경)를 반영해서 재고를 일괄 동기화 (자동 재고차감)
    # 주문마다 따로 처리하면 건수가 많을 때 매우 느려서 한 번에 처리함
    db.sync_stock_for_all_orders()

    return matched_count, unmatched_count
