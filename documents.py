"""
거래명세표 / 송장요청서 출력
==========================
샘플로 받은 양식(행 높이·열 너비·병합 구조)을 그대로 재현합니다.

  · 거래명세표 : 엑셀(.xlsx) 또는 그림(.png)으로 출력
                 한 장에 "공급받는자 보관용" + "공급자 보관용" 두 벌
  · 송장요청서 : 엑셀(.xlsx)로 출력 (택배사 업로드 양식 그대로)
"""

import os

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter


# 샘플 파일에서 읽어낸 규격 (32열 구성)
# 샘플 파일에서 읽어낸 실제 행 높이 (twips ÷ 20 = 포인트)
_COL_WIDTH = 2.6          # 열 하나의 너비 (32열을 합쳐 A4 가로폭에 맞춤)
_ROW_H_TITLE = 15.0       # 0~1행  제목·거래일자   (300 twips)
_ROW_H_INFO = 13.5        # 2~9행  공급자/공급받는자 (270 twips)
_ROW_H_HEAD = 15.0        # 10행   품목표 머리      (300 twips)
_ROW_H_ITEM = 19.5        # 11~19행 품목 9줄        (390 twips)
_ROW_H_TOTAL = 15.0       # 20~21행 합계            (300 twips)
_ROW_H_BANK = 13.5        # 22~23행 계좌 안내       (270 twips)
_BLOCK_ROWS = 24          # 한 벌이 차지하는 행 수

_GREEN = "008000"
_thin = Side(style="thin", color=_GREEN)
_medium = Side(style="medium", color=_GREEN)


def _merge(ws, r1, c1, r2, c2, value=None, *, bold=False, size=10,
           align="center", border=True, wrap=False, fmt=None):
    """엑셀 셀 병합 + 값·서식 지정 (행/열은 0부터, 끝은 포함하지 않음)"""
    ws.merge_cells(start_row=r1 + 1, start_column=c1 + 1,
                   end_row=r2, end_column=c2)
    cell = ws.cell(row=r1 + 1, column=c1 + 1)
    if value is not None:
        cell.value = value
    cell.font = Font(name="맑은 고딕", size=size, bold=bold)
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    if fmt:
        cell.number_format = fmt
    if border:
        for r in range(r1 + 1, r2 + 1):
            for c in range(c1 + 1, c2 + 1):
                ws.cell(row=r, column=c).border = Border(
                    left=_thin, right=_thin, top=_thin, bottom=_thin)
    return cell


def _draw_statement_block(ws, top, info, items, total, copy_label):
    """거래명세표 한 벌을 그림 (공급받는자용 / 공급자용 각각 호출)"""
    seller = info["seller"]
    buyer = info["buyer"]

    # ── 제목 줄 (거래일자 2줄 + 제목) ──
    _merge(ws, top, 0, top + 1, 6, "거 래 일 자", size=9)
    _merge(ws, top + 1, 0, top + 2, 6, info["date"], size=10)
    _merge(ws, top, 6, top + 1, 26, "거 래 명 세 표", bold=True, size=22, border=False)
    _merge(ws, top + 1, 26, top + 2, 32, copy_label, size=9, border=False)

    r = top + 2   # 정보 영역 시작

    # ── 공급자 / 공급받는자 ──
    _merge(ws, r, 0, r + 8, 1, "공\n급\n자", size=10, wrap=True)
    _merge(ws, r, 16, r + 8, 17, "공급받는자", size=9, wrap=True)

    _merge(ws, r, 1, r + 2, 4, "등록번호", size=9)
    _merge(ws, r, 4, r + 2, 16, seller["biznum"], bold=True, size=11)
    _merge(ws, r, 17, r + 2, 20, "등록번호", size=9)
    _merge(ws, r, 20, r + 2, 32, buyer["biznum"], bold=True, size=11)

    r += 2
    _merge(ws, r, 1, r + 2, 4, "상     호\n(법인명)", size=9, wrap=True)
    _merge(ws, r, 4, r + 2, 11, seller["name"], size=10)
    _merge(ws, r, 11, r + 2, 12, "성명", size=9)
    _merge(ws, r, 12, r + 2, 16, seller["ceo"], size=10)
    _merge(ws, r, 17, r + 2, 20, "상     호\n(법인명)", size=9, wrap=True)
    _merge(ws, r, 20, r + 2, 27, buyer["name"], size=10)
    _merge(ws, r, 27, r + 2, 28, "성명", size=9)
    _merge(ws, r, 28, r + 2, 32, buyer["ceo"], size=10)

    r += 2
    _merge(ws, r, 1, r + 2, 4, "사 업 장\n주     소", size=9, wrap=True)
    _merge(ws, r, 4, r + 2, 16, seller["address"], size=9, align="left")
    _merge(ws, r, 17, r + 2, 20, "사 업 장\n주     소", size=9, wrap=True)
    _merge(ws, r, 20, r + 2, 32, buyer["address"], size=9, align="left")

    r += 2
    _merge(ws, r, 1, r + 2, 4, "업     태", size=9)
    _merge(ws, r, 4, r + 2, 10, seller["business_type"], size=9)
    _merge(ws, r, 10, r + 2, 11, "종\n목", size=8, wrap=True)
    _merge(ws, r, 11, r + 2, 16, seller["business_item"], size=8, wrap=True)
    _merge(ws, r, 17, r + 2, 20, "업     태", size=9)
    _merge(ws, r, 20, r + 2, 26, buyer["business_type"], size=9)
    _merge(ws, r, 26, r + 2, 27, "종\n목", size=8, wrap=True)
    _merge(ws, r, 27, r + 2, 32, buyer["business_item"], size=8, wrap=True)

    # ── 품목 표 머리 ──
    r += 2
    header_fill = PatternFill("solid", fgColor="FFFFFF")
    for c1, c2, label in [(0, 1, "월"), (1, 2, "일"), (2, 8, "품          목"),
                           (8, 12, "규격"), (12, 14, "수량"), (14, 19, "단      가"),
                           (19, 25, "금  액(VAT포함)"), (25, 32, "비  고")]:
        cell = _merge(ws, r, c1, r + 1, c2, label, bold=True, size=9)
        cell.fill = header_fill

    # ── 품목 줄 (샘플과 같이 9줄 확보) ──
    r += 1
    for i in range(9):
        row = r + i
        it = items[i] if i < len(items) else None
        _merge(ws, row, 0, row + 1, 1, it["month"] if it else None, size=9)
        _merge(ws, row, 1, row + 1, 2, it["day"] if it else None, size=9)
        _merge(ws, row, 2, row + 1, 8, it["name"] if it else None, size=9, align="left")
        _merge(ws, row, 8, row + 1, 12, it["spec"] if it else None, size=9)
        _merge(ws, row, 12, row + 1, 14, it["qty"] if it else None, size=9, fmt="#,##0")
        _merge(ws, row, 14, row + 1, 19, it["price"] if it else None, size=9, fmt="#,##0")
        _merge(ws, row, 19, row + 1, 25, it["amount"] if it else None, size=9, fmt="#,##0")
        _merge(ws, row, 25, row + 1, 32, it.get("memo") if it else None, size=9)

    # ── 합계 줄 ──
    r += 9
    _merge(ws, r, 0, r + 2, 9, "합계\n금액(VAT포함)", bold=True, size=9, wrap=True)
    _merge(ws, r, 9, r + 2, 20, total, bold=True, size=12, fmt='"₩"#,##0')
    _merge(ws, r, 20, r + 2, 22, "미수금", size=9)
    _merge(ws, r, 22, r + 2, 26, info.get("unpaid"), size=9, fmt="#,##0")
    _merge(ws, r, 26, r + 2, 28, "인수자", size=9)
    _merge(ws, r, 28, r + 2, 32, None, size=9)

    # ── 계좌 안내 ──
    r += 2
    _merge(ws, r, 0, r + 1, 32, info.get("bank_info", ""), bold=True, size=10, border=False)
    return r + 1


def export_statement_excel(path, info, items, total):
    """거래명세표를 엑셀로 저장 (한 장에 두 벌: 공급받는자용 + 공급자용)"""
    wb = Workbook()
    ws = wb.active
    ws.title = "거래명세표"

    for c in range(1, 33):
        ws.column_dimensions[get_column_letter(c)].width = _COL_WIDTH

    _draw_statement_block(ws, 0, info, items, total, "(공급받는자 보관용)")
    _draw_statement_block(ws, _BLOCK_ROWS + 1, info, items, total, "(공급자 보관용)")

    # 샘플 파일과 똑같은 행 높이를 두 벌 모두에 적용
    heights = ([_ROW_H_TITLE] * 2 + [_ROW_H_INFO] * 8 + [_ROW_H_HEAD] +
               [_ROW_H_ITEM] * 9 + [_ROW_H_TOTAL] * 2 + [_ROW_H_BANK] * 2)
    for block_start in (0, _BLOCK_ROWS + 1):
        for i, h in enumerate(heights):
            ws.row_dimensions[block_start + i + 1].height = h
    ws.row_dimensions[_BLOCK_ROWS + 1].height = 12   # 두 벌 사이 여백

    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    try:
        wb.save(path)
    finally:
        wb.close()   # 닫지 않으면 엑셀이 파일을 계속 잡고 있어 다른 파일이 안 열림
    return path


def export_statement_image(path, info, items, total):
    """거래명세표를 그림(PNG)으로 저장 - 샘플 이미지와 같은 초록 테두리 양식"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib import font_manager

    # 한글이 나오는 글꼴 찾기
    font_name = None
    for candidate in ("Malgun Gothic", "AppleGothic", "NanumGothic",
                       "Noto Sans CJK KR", "Noto Sans KR", "DejaVu Sans"):
        try:
            font_manager.findfont(candidate, fallback_to_default=False)
            font_name = candidate
            break
        except Exception:
            continue
    if font_name:
        matplotlib.rcParams["font.family"] = font_name
    matplotlib.rcParams["axes.unicode_minus"] = False

    G = "#008000"
    fig, ax = plt.subplots(figsize=(9.6, 6.6), dpi=130)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 70)
    ax.axis("off")

    def box(x, y, w, h, lw=0.8):
        ax.add_patch(Rectangle((x, y), w, h, fill=False, edgecolor=G, linewidth=lw))

    def text(x, y, s, size=8, weight="normal", ha="center"):
        ax.text(x, y, "" if s is None else str(s), fontsize=size,
                fontweight=weight, ha=ha, va="center", color="black")

    box(2, 2, 96, 66, 1.6)                      # 바깥 테두리

    # 제목
    box(4, 60, 22, 6); text(15, 63, "거 래 일 자", 8)
    box(4, 56, 22, 4); text(15, 58, info["date"], 8)
    text(50, 61, "거 래 명 세 표", 20, "bold")
    text(90, 57.5, info.get("copy_label", "(공급받는자 보관용)"), 7)

    # 공급자 / 공급받는자
    top, h = 54, 4
    box(4, top - h * 4, 4, h * 4); text(6, top - h * 2, "공\n급\n자", 8)
    box(52, top - h * 4, 4, h * 4); text(54, top - h * 2, "공\n급\n받\n는\n자", 6.5)

    rows = [
        ("등록번호", info["seller"]["biznum"], "등록번호", info["buyer"]["biznum"], True),
        ("상 호\n(법인명)", info["seller"]["name"], "상 호\n(법인명)", info["buyer"]["name"], False),
        ("사 업 장\n주 소", info["seller"]["address"], "사 업 장\n주 소", info["buyer"]["address"], False),
        ("업 태", info["seller"]["business_type"], "업 태", info["buyer"]["business_type"], False),
    ]
    for i, (l1, v1, l2, v2, bold) in enumerate(rows):
        y = top - h * (i + 1)
        if i == 3:
            # 업태 행: 업태(좌) + 종목(우)을 나란히 표시
            # (예전엔 업태만 있고 종목이 빠져 있었음)
            box(8, y, 10, h);  text(13, y + h / 2, l1, 7)
            box(18, y, 16, h); text(26, y + h / 2, v1, 7.5, "normal")
            box(34, y, 6, h);  text(37, y + h / 2, "종 목", 7)
            box(40, y, 12, h); text(46, y + h / 2,
                                    info["seller"].get("business_item", "") or "", 7, "normal")
            box(56, y, 10, h); text(61, y + h / 2, l2, 7)
            box(66, y, 14, h); text(73, y + h / 2, v2, 7.5, "normal")
            box(80, y, 6, h);  text(83, y + h / 2, "종 목", 7)
            box(86, y, 10, h); text(91, y + h / 2,
                                    info["buyer"].get("business_item", "") or "", 7, "normal")
        elif i == 1:
            # 상호 행: 상호(좌)+성명(우) 분리
            box(8, y, 10, h);  text(13, y + h / 2, l1, 7)
            box(18, y, 20, h); text(28, y + h / 2, v1, 7.5, "normal")
            box(38, y, 6, h);  text(41, y + h / 2, "성 명", 7)
            box(44, y, 8, h);  text(48, y + h / 2, info["seller"]["ceo"] or "", 7.5)
            box(56, y, 10, h); text(61, y + h / 2, l2, 7)
            box(66, y, 18, h); text(75, y + h / 2, v2, 7.5, "normal")
            box(84, y, 6, h);  text(87, y + h / 2, "성 명", 7)
            box(90, y, 6, h);  text(93, y + h / 2, info["buyer"]["ceo"] or "", 7.5)
        else:
            box(8, y, 10, h);  text(13, y + h / 2, l1, 7)
            box(18, y, 34, h); text(35, y + h / 2, v1, 8 if bold else 7.5,
                                     "bold" if bold else "normal")
            box(56, y, 10, h); text(61, y + h / 2, l2, 7)
            box(66, y, 30, h); text(81, y + h / 2, v2, 8 if bold else 7.5,
                                     "bold" if bold else "normal")

    # 품목 표
    cols = [(4, 6, "월"), (10, 6, "일"), (16, 22, "품          목"),
            (38, 14, "규격"), (52, 10, "수량"), (62, 12, "단      가"),
            (74, 14, "금 액(VAT포함)"), (88, 8, "비 고")]
    hy = 34
    for x, w, label in cols:
        box(x, hy, w, 4); text(x + w / 2, hy + 2, label, 7.5, "bold")

    for i in range(6):
        y = hy - 3.6 * (i + 1)
        it = items[i] if i < len(items) else None
        vals = [it["month"] if it else "", it["day"] if it else "",
                it["name"] if it else "", it["spec"] if it else "",
                f"{it['qty']:,}" if it else "", f"{it['price']:,.0f}" if it else "",
                f"{it['amount']:,.0f}" if it else "", ""]
        for (x, w, _), v in zip(cols, vals):
            box(x, y, w, 3.6)
            text(x + w / 2, y + 1.8, v, 7.5)

    # 합계
    fy = hy - 3.6 * 6 - 5
    box(4, fy, 30, 4.5); text(19, fy + 2.25, "합계금액(VAT포함)", 8, "bold")
    box(34, fy, 28, 4.5); text(48, fy + 2.25, f"₩{total:,.0f}", 11, "bold")
    box(62, fy, 14, 4.5); text(69, fy + 2.25, "미수금", 8)
    box(76, fy, 20, 4.5); text(86, fy + 2.25,
                                f"{info['unpaid']:,.0f}" if info.get("unpaid") else "", 8)

    text(50, fy - 3, info.get("bank_info", ""), 8.5, "bold")

    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# 송장요청서 - 택배사 업로드 양식 그대로
INVOICE_HEADERS = [
    "받는분성명", "받는분전화번호", "받는분기타연락처", "받는분주소(전체, 분할)",
    "품목명", "내품명", "내품수량", "박스수량", "박스타입", "운임구분",
    "배송메세지", "운송장번호",
]


def export_invoice_request(path, rows):
    """송장요청서를 엑셀로 저장 (샘플 양식과 동일한 컬럼 구성)"""
    wb = Workbook()
    ws = wb.active
    ws.title = "송장요청서"

    widths = [14, 16, 16, 44, 22, 14, 10, 10, 10, 10, 20, 16]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    thin = Side(style="thin", color="999999")
    for c, name in enumerate(INVOICE_HEADERS, start=1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.font = Font(name="맑은 고딕", size=10, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.fill = PatternFill("solid", fgColor="FFEB3B")
        cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws.row_dimensions[1].height = 24

    for r, row in enumerate(rows, start=2):
        values = [
            row.get("receiver", ""), row.get("phone", ""), row.get("phone2", ""),
            row.get("address", ""), row.get("product", ""), row.get("inner_name", ""),
            row.get("qty", ""), row.get("box_qty", 1), row.get("box_type", ""),
            row.get("fare_type", "신용"), row.get("message", ""), row.get("invoice_no", ""),
        ]
        for c, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(name="맑은 고딕", size=10)
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            cell.alignment = Alignment(
                horizontal="center" if c in (1, 2, 3, 7, 8, 9, 10) else "left",
                vertical="center")
        ws.row_dimensions[r].height = 20

    ws.freeze_panes = "A2"
    try:
        wb.save(path)
    finally:
        wb.close()
    return path
