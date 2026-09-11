# -*- coding: utf-8 -*-
"""
importer.py
스마트스토어 / 11번가 / 쿠팡 / ESM(지마켓·옥션) 엑셀(csv/xlsx) 주문 파일을
공통 스키마(orders 테이블 형식)로 변환하는 모듈.

주의: 각 마켓의 다운로드 양식(컬럼명, 헤더 위치)은 마켓 측 업데이트에 따라
자주 바뀔 수 있습니다. 아래 매핑은 2024~2025년 기준 흔히 쓰이는 컬럼명을
최대한 폭넓게 커버하도록 만들었고, 부족한 부분은 수동 매칭 다이얼로그로
보완합니다.
"""
import pandas as pd
import os


def normalize_date(raw):
    """마켓마다 다른 날짜 형식(2026/07/31, 2026-07-30 17:39:29, 2026.07.30 등)을
    'YYYY-MM-DD HH:MM:SS' (시간 없으면 'YYYY-MM-DD') 형식으로 통일.
    리포트에서 날짜별 정렬/그룹핑이 마켓마다 표기가 달라 어긋나는 문제를 방지."""
    if not raw:
        return ""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return ""
    try:
        dt = pd.to_datetime(s, errors="coerce")
    except Exception:
        dt = None
    if dt is None or pd.isna(dt):
        return s  # 파싱 실패하면 원본 그대로 (데이터 손실 방지)
    has_time = ":" in s
    if has_time:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt.strftime("%Y-%m-%d")


# 표준 스키마 필드와, 각 필드에 대응될 수 있는 마켓별 실제 컬럼명 후보들
FIELD_ALIASES = {
    "order_no": ["상품주문번호", "주문번호", "구매번호", "발주번호", "오더번호"],
    "order_date": ["결제일시", "결제일", "주문일시", "주문일자", "발주확인일", "주문일"],
    "product_name": ["상품명", "상품 명", "품목명"],
    "option_name": ["옵션정보", "옵션명", "옵션", "구매옵션", "등록옵션명"],
    "qty": ["수량", "구매수량", "주문수량"],
    # 판매단가(단품 단가)를 옵션가보다 먼저 매칭 - 옵션가는 마켓에 따라
    # 수량이 곱해진 옵션 추가금 합계인 경우가 있어 단가로 쓰면 부정확할 수 있음
    "sale_price": ["판매단가", "단가", "옵션가", "상품가격", "판매가"],
    # 정산예정금액은 수수료가 이미 빠진 금액이라 total_amount(결제/주문금액)로 쓰면 안 됨
    # -> settlement_amount 전용으로만 사용
    # 스마트스토어는 "최종 상품별 총 주문금액"이 실제 매출금액이라 맨 앞에 둠
    # (옵션가가 포함된 금액이라 '상품가격'만 쓰면 매출이 실제보다 적게 잡힘)
    "total_amount": ["최종 상품별 총 주문금액", "최종상품별총주문금액",
                      "결제금액", "상품결제금액", "총 결제금액", "주문금액", "총주문금액",
                      "실결제금액", "결제액"],
    "fee_amount": ["수수료", "판매수수료", "이용료", "서비스이용료"],
    "shipping_fee": ["배송비", "배송비합계", "배송비 합계"],
    "settlement_amount": ["정산예정금액", "정산금액", "정산대금", "예상정산금액"],
    "buyer_name": ["구매자명", "구매자", "수취인명", "수령인명"],
    "status": ["주문상태", "클레임상태", "처리상태", "배송상태"],
    "receiver_name": ["수취인명", "수령인명", "수취인", "받는분", "수하인명"],
    "address": ["통합배송지", "배송지주소", "주소", "수취인주소", "수령인주소", "배송주소"],
    "phone": ["수취인연락처1", "수취인연락처", "수령인연락처", "휴대폰번호", "연락처", "전화번호"],
}

# 파일명이나 컬럼 구성으로 어떤 마켓인지 추정할 때 쓰는 힌트 키워드
CHANNEL_HINTS = {
    "스마트스토어": ["스마트스토어", "네이버", "smartstore"],
    "11번가": ["11번가", "11st", "십일번가"],
    "쿠팡": ["쿠팡", "coupang"],
    "ESM(G마켓/옥션)": ["esm", "지마켓", "gmarket", "옥션", "auction"],
}


def guess_channel_from_filename(filepath: str) -> str:
    fname = os.path.basename(filepath).lower()
    for channel, hints in CHANNEL_HINTS.items():
        for h in hints:
            if h.lower() in fname:
                return channel
    return None


def _read_raw(filepath: str, skiprows: int = 0) -> pd.DataFrame:
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".xlsx", ".xls"):
        try:
            return pd.read_excel(filepath, skiprows=skiprows, dtype=str)
        except ImportError as e:
            if ext == ".xls":
                raise ImportError(
                    "구형 엑셀(.xls) 파일을 읽으려면 'xlrd' 라이브러리가 필요합니다.\n"
                    "명령 프롬프트(cmd)에서 아래 명령을 실행한 뒤 다시 시도해주세요:\n\n"
                    "pip install xlrd\n\n"
                    "(설치 후에도 안 되면 'pip install --upgrade xlrd' 또는 "
                    "'py -m pip install xlrd'로 시도해보세요)"
                ) from e
            raise ImportError(
                "엑셀(.xlsx) 파일을 읽으려면 'openpyxl' 라이브러리가 필요합니다.\n"
                "명령 프롬프트(cmd)에서 아래 명령을 실행한 뒤 다시 시도해주세요:\n\n"
                "pip install openpyxl"
            ) from e
    elif ext == ".csv":
        # 마켓 다운로드 CSV는 종종 CP949(EUC-KR) 인코딩
        try:
            return pd.read_csv(filepath, skiprows=skiprows, dtype=str, encoding="cp949")
        except UnicodeDecodeError:
            return pd.read_csv(filepath, skiprows=skiprows, dtype=str, encoding="utf-8-sig")
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")


def _find_header_row(filepath: str, max_check_rows: int = 8):
    """엑셀 상단에 안내 문구가 몇 줄 섞여 있는 경우가 많아, 실제 헤더 행을 찾는다."""
    for skip in range(0, max_check_rows):
        try:
            df = _read_raw(filepath, skiprows=skip)
        except Exception:
            continue
        cols = [str(c) for c in df.columns]
        matched = 0
        for aliases in FIELD_ALIASES.values():
            if any(col.strip() in aliases for col in cols):
                matched += 1
        if matched >= 3:  # 최소 3개 필드 이상 인식되면 헤더로 판단
            return skip, df
    # 못 찾으면 0번째 행을 헤더로 가정
    return 0, _read_raw(filepath, skiprows=0)


# 수수료 컬럼이지만 "금액"이 아닌 것들 (비율/구분값 등) - 합산에서 제외
FEE_EXCLUDE_HINTS = ("율", "%", "구분", "여부", "코드", "방식", "유형", "명")


def find_fee_columns(columns):
    """수수료에 해당하는 컬럼을 모두 찾아서 돌려줌.

    스마트스토어 주문 파일처럼 수수료가 한 칸에 안 들어있고
    '네이버페이 주문관리 수수료'(AT)와 '매출연동 수수료'(AU)로 나뉘어 있는 경우,
    둘 다 합쳐야 실제로 떼인 수수료가 됨.
    (예전엔 앞의 한 칸만 읽어서 수수료가 실제의 40%밖에 안 잡혔음)

    · 정확히 '수수료' 같은 대표 이름의 컬럼이 있으면 그것만 사용 (기존 동작 유지)
    · 없을 때만 이름에 '수수료'가 들어간 금액 컬럼을 모두 모아 합산
    """
    cols = [str(c).strip() for c in columns]

    # 1단계: 대표 이름과 완전히 일치하는 컬럼이 있으면 그것만 (쿠팡/11번가 등)
    for alias in FIELD_ALIASES["fee_amount"]:
        if alias in cols:
            return [alias]

    # 2단계: 이름에 '수수료'가 들어간 금액 컬럼을 모두 합산 (스마트스토어 등)
    return [c for c in cols
            if "수수료" in c and not any(h in c for h in FEE_EXCLUDE_HINTS)]


def auto_map_columns(columns):
    """실제 컬럼명 리스트를 받아 표준 필드명 -> 실제 컬럼명 매핑 딕셔너리를 반환.
    1단계: 완전히 일치하는 컬럼을 최우선으로 찾음 (예: '배송비' == '배송비')
    2단계: 완전 일치가 없을 때만 부분 포함으로 찾음 (예: '결제일' in '결제일시')
    -> 이렇게 해야 '수수료'가 '수출대행수수료(%)'에, '배송비'가 '배송비결제방식'에
       잘못 매칭되는 것을 방지할 수 있음 (완전히 일치하는 '서비스이용료', '배송비'가
       있는데도 부분 포함 매칭 때문에 엉뚱한 컬럼이 먼저 잡히던 문제)"""
    columns_clean = [str(c).strip() for c in columns]
    mapping = {}
    for field, aliases in FIELD_ALIASES.items():
        found = None

        # 1단계: 완전 일치 우선
        for alias in aliases:
            if alias in columns_clean:
                found = alias
                break

        # 2단계: 완전 일치가 없을 때만 부분 포함으로 탐색
        if not found:
            for alias in aliases:
                for col in columns_clean:
                    if alias in col:
                        found = col
                        break
                if found:
                    break

        mapping[field] = found
    return mapping


def parse_order_file(filepath: str, channel_name: str = None, manual_mapping: dict = None):
    """
    파일을 읽어 표준 주문 리스트(list[dict])로 변환.
    channel_name: 사용자가 직접 지정한 채널명 (없으면 파일명으로 추정)
    manual_mapping: {표준필드: 실제컬럼명} - 자동 인식이 부족할 때 수동 지정용
    반환값: (rows: list[dict], detected_mapping: dict, unmatched_fields: list, raw_columns: list)
    """
    skiprows, df = _find_header_row(filepath)
    df = df.dropna(how="all")  # 완전히 빈 행 제거
    columns = list(df.columns)

    mapping = auto_map_columns(columns)
    if manual_mapping:
        mapping.update({k: v for k, v in manual_mapping.items() if v})

    unmatched = [f for f, v in mapping.items() if v is None]

    # 수수료 컬럼은 여러 개로 쪼개져 있을 수 있어서 따로 찾아 합산함
    # (스마트스토어: '네이버페이 주문관리 수수료' + '매출연동 수수료')
    if manual_mapping and manual_mapping.get("fee_amount"):
        fee_columns = [manual_mapping["fee_amount"]]   # 사용자가 직접 고른 게 있으면 그것만
    else:
        fee_columns = find_fee_columns(columns)
    if fee_columns:
        mapping["fee_amount"] = fee_columns[0]
        if "fee_amount" in unmatched:
            unmatched.remove("fee_amount")

    rows = []
    for _, r in df.iterrows():
        def get_val(field):
            col = mapping.get(field)
            if col is None or col not in r:
                return None
            val = r[col]
            if pd.isna(val):
                return None
            return val

        def get_num(field):
            val = get_val(field)
            if val is None:
                return 0
            try:
                # "12,345원" 같은 문자열에서 숫자만 추출
                cleaned = "".join(ch for ch in str(val) if ch.isdigit() or ch == "-")
                return int(cleaned) if cleaned not in ("", "-") else 0
            except Exception:
                return 0

        def get_fee_amount():
            """수수료 컬럼이 여러 개면 모두 더해서 하나의 수수료 금액으로 만듦.
            마켓 파일은 수수료를 차감 항목이라 음수로 적는 경우가 많은데,
            장부에서는 '떼인 금액(양수)'으로 다루므로 절대값으로 바꿔 저장함."""
            if not fee_columns:
                return 0
            total = 0
            for col in fee_columns:
                if col not in r.index:
                    continue
                val = r[col]
                if pd.isna(val):
                    continue
                cleaned = "".join(ch for ch in str(val)
                                  if ch.isdigit() or ch in ("-", "."))
                if cleaned in ("", "-", "."):
                    continue
                try:
                    total += float(cleaned)
                except ValueError:
                    continue
            return int(round(abs(total)))

        order_no = get_val("order_no")
        if not order_no:
            continue  # 주문번호 없는 행(합계행 등)은 건너뜀

        def get_order_date():
            """결제일이 비어있는 주문(결제대기 등)도 날짜를 갖도록,
            매핑된 컬럼이 비면 다른 날짜 컬럼에서 순서대로 찾아 씀.
            (예전엔 결제일이 비면 날짜가 빈 값이 되어, 저장은 되지만
             날짜 조회필터에 걸리지 않아 목록에서 안 보이는 문제가 있었음)"""
            val = get_val("order_date")
            if val is not None and str(val).strip():
                return val
            for alias in FIELD_ALIASES["order_date"]:
                for col in r.index:
                    if str(col).strip() == alias:
                        v = r[col]
                        if not pd.isna(v) and str(v).strip():
                            return v
            return None

        row = {
            "channel_id": None,  # main.py에서 채널 id로 채워 넣음
            "order_no": str(order_no),
            "order_date": normalize_date(get_order_date()),
            "product_name": str(get_val("product_name") or ""),
            "option_name": str(get_val("option_name") or ""),
            "qty": get_num("qty") or 1,
            "sale_price": get_num("sale_price"),
            "total_amount": get_num("total_amount"),
            "fee_amount": get_fee_amount(),
            "shipping_fee": get_num("shipping_fee"),
            "settlement_amount": get_num("settlement_amount") or get_num("total_amount"),
            "buyer_name": str(get_val("buyer_name") or ""),
            "status": str(get_val("status") or ""),
            "receiver_name": str(get_val("receiver_name") or ""),
            "address": str(get_val("address") or ""),
            "phone": str(get_val("phone") or ""),
            "memo": "",
        }
        rows.append(row)

    # 파일명 기반 감지를 우선 사용 (main.py에서 사용자가 선택한 채널과 비교해
    # 다르면 확인창을 띄우는 용도). 파일명으로 감지가 안 되면 전달받은 channel_name으로 대체.
    detected_channel = guess_channel_from_filename(filepath) or channel_name
    # 파일 전체 정산금액 합계 계산 (검증용)
    settle_col = mapping.get("settle_amount")
    file_total = 0
    if settle_col and settle_col in df.columns:
        import pandas as _pd
        file_total = int(_pd.to_numeric(df[settle_col], errors="coerce").fillna(0).sum())

    return rows, mapping, unmatched, columns, file_total, detected_channel


# ---------------------------------------------------------------------------
# 정산내역 파일 파싱 (마켓에서 다운받은 정산 리포트 -> 주문과 매칭용)
# ---------------------------------------------------------------------------
SETTLEMENT_FIELD_ALIASES = {
    "order_no": ["상품주문번호", "주문번호", "구매번호", "발주번호", "오더번호"],
    "buyer_name": ["구매자명", "구매자", "수취인명", "수령인명"],
    "product_name": ["상품명", "상품 명", "품목명"],
    "settle_amount": ["정산금액", "정산예정금액", "지급액", "정산대금", "실지급액"],
    "settle_date": ["정산일", "정산일자", "지급일", "정산완료일"],
    # 스마트스토어 정산파일은 '구분' 칸에 상품주문 / 배송비 가 따로 적힘
    "kind": ["구분", "정산구분", "항목구분"],
    # 배송비 줄은 '상품주문번호'가 주문과 달라서, 묶어줄 '주문번호'가 따로 필요함
    "parent_order_no": ["주문번호", "구매번호"],
    # 쿠팡은 '구분' 칸이 없고 옵션 자리에 <기본배송료>/<추가배송료> 라고 적힘
    "option_label": ["옵션 ID", "옵션ID", "옵션명", "옵션정보", "옵션"],
}

# 배송비 줄임을 알려주는 표시들 (마켓마다 적는 위치가 달라 옵션칸까지 함께 봄)
SHIPPING_MARKERS = ("배송비", "배송료", "기본배송", "추가배송")

# 정산금액 컬럼이 따로 없고 '기준금액 + 수수료들'로 계산해야 하는 파일 대비
# (스마트스토어: 정산기준금액(A) + Npay 수수료(B) + 매출연동 수수료 합계(C) + 무이자할부 수수료(D))
SETTLE_BASE_ALIASES = ["정산기준금액", "정산대상금액", "기준금액"]
SETTLE_FEE_HINTS = ["수수료"]
SETTLE_FEE_EXCLUDE = ["율", "%", "구분", "여부", "코드"]


def detect_settlement_style(columns):
    """정산파일이 '전액 지급형'인지 '부분 지급형'인지 판단.

    full    : 파일에 적힌 정산금액이 곧 입금액 (스마트스토어 등)
              -> 배송비까지 이미 들어있으므로 그대로 쓰면 됨
    partial : 지급비율·공제금액이 따로 적용됨 (쿠팡 주정산 70% + 광고비 공제)
              -> 실제 입금액을 확인받아야 함
    """
    cols = " ".join(str(c) for c in columns)
    if "정산기준금액" in cols:          # 스마트스토어
        return "full"
    if "판매수수료" in cols and "정산금액" in cols:   # 쿠팡
        return "partial"
    return "full"


def _is_shipping_row(kind, option_label):
    """이 줄이 '배송비 정산' 줄인지 판단.
    · 스마트스토어: 구분 칸에 '배송비'
    · 쿠팡: 옵션 ID 칸에 '<기본배송료>' / '<추가배송료>'
    """
    for val in (kind, option_label):
        text = str(val or "")
        if any(m in text for m in SHIPPING_MARKERS):
            return True
    return False


def find_settle_amount_columns(columns):
    """정산금액을 만들어낼 컬럼들을 찾음.
    반환: (기준금액 컬럼, [수수료 컬럼들])  - 없으면 (None, [])"""
    cols = [str(c).strip() for c in columns]
    base = None
    for alias in SETTLE_BASE_ALIASES:
        for c in cols:
            if alias in c:
                base = c
                break
        if base:
            break
    if not base:
        return None, []
    fees = [c for c in cols
            if any(h in c for h in SETTLE_FEE_HINTS)
            and not any(x in c for x in SETTLE_FEE_EXCLUDE)]
    return base, fees


def parse_settlement_file(filepath: str, manual_mapping: dict = None):
    """마켓 정산내역 파일을 읽어 표준화된 행 리스트로 변환.
    반환: (rows: list[dict], mapping: dict, unmatched: list, columns: list)
    각 row: {"order_no":.., "buyer_name":.., "product_name":.., "settle_amount":.., "settle_date":..}
    """
    skiprows, df = _find_header_row(filepath)
    df = df.dropna(how="all")
    columns = list(df.columns)

    columns_clean = [str(c).strip() for c in columns]
    mapping = {}
    for field, aliases in SETTLEMENT_FIELD_ALIASES.items():
        found = None
        for alias in aliases:
            if alias in columns_clean:
                found = alias
                break
        if not found:
            for alias in aliases:
                for col in columns_clean:
                    if alias in col:
                        found = col
                        break
                if found:
                    break
        mapping[field] = found

    if manual_mapping:
        mapping.update({k: v for k, v in manual_mapping.items() if v})

    # 정산금액 컬럼이 따로 없으면 '기준금액 + 수수료들'로 직접 계산
    base_col, fee_cols = (None, [])
    if not mapping.get("settle_amount"):
        base_col, fee_cols = find_settle_amount_columns(columns_clean)

    unmatched = [f for f, v in mapping.items()
                 if v is None and f not in ("kind", "parent_order_no")]
    if base_col and "settle_amount" in unmatched:
        unmatched.remove("settle_amount")

    def _num(val):
        if val is None or pd.isna(val):
            return 0
        cleaned = "".join(ch for ch in str(val) if ch.isdigit() or ch in ("-", "."))
        if cleaned in ("", "-", "."):
            return 0
        try:
            return int(round(float(cleaned)))
        except ValueError:
            return 0

    rows = []
    for _, r in df.iterrows():
        def get_val(field):
            col = mapping.get(field)
            if col is None or col not in r:
                return None
            val = r[col]
            if pd.isna(val):
                return None
            return val

        order_no = get_val("order_no")
        buyer_name = get_val("buyer_name")
        if not order_no and not buyer_name:
            continue

        amount_raw = get_val("settle_amount")
        if amount_raw is not None:
            amount = _num(amount_raw)
        elif base_col:
            # 정산기준금액에 수수료를 반영해 실제 정산액을 구함
            # (수수료는 파일에 음수로 적혀 있으므로 그대로 더하면 됨)
            amount = _num(r.get(base_col))
            for fc in fee_cols:
                amount += _num(r.get(fc))
        else:
            amount = 0

        kind = str(get_val("kind") or "").strip()
        parent_no = get_val("parent_order_no")

        rows.append({
            "order_no": str(order_no) if order_no else "",
            "buyer_name": str(buyer_name) if buyer_name else "",
            "product_name": str(get_val("product_name") or ""),
            "settle_amount": amount,
            "settle_date": normalize_date(get_val("settle_date")),
            "kind": kind,
            # 배송비 줄은 상품주문번호가 주문과 달라서, 주문번호로도 찾을 수 있게 보관
            "parent_order_no": str(parent_no) if parent_no else "",
            "is_shipping": _is_shipping_row(kind, get_val("option_label")),
        })

    # 파일 전체 정산금액 합계 (검증용)
    settle_col = mapping.get("settle_amount")
    file_total = 0
    if settle_col and settle_col in df.columns:
        import pandas as _pd
        file_total = int(_pd.to_numeric(df[settle_col], errors="coerce").fillna(0).sum())
    else:
        # 계산해서 만든 정산금액의 합계 (배송비 줄 포함)
        file_total = sum(r["settle_amount"] for r in rows)

    return (rows, mapping, unmatched, columns, file_total,
            detect_settlement_style(columns_clean))
