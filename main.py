# -*- coding: utf-8 -*-
"""
온라인 판매 장부 프로그램 (스마트스토어 / 11번가 / 쿠팡 / ESM 전용)
main.py - 실행 진입점
"""
import sys
import os
import shutil
from datetime import date, datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QTableWidget, QTableWidgetItem, QLabel, QFileDialog, QComboBox,
    QLineEdit, QFormLayout, QMessageBox, QDateEdit, QGroupBox, QGridLayout,
    QHeaderView, QDialog, QDialogButtonBox, QMenu, QAbstractItemView, QInputDialog,
    QStackedWidget, QSpinBox, QStyledItemDelegate, QCheckBox, QFrame,
    QListWidget, QListWidgetItem, QToolButton, QCalendarWidget, QSizePolicy
)
from PySide6.QtCore import Qt, QDate, QPoint, QSettings, QEvent, QTimer, QRect, QElapsedTimer
from PySide6.QtGui import QCursor, QColor, QFont
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsBlurEffect

import database as db
import importer
import matching
import charts


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------
def fmt_won(n):
    try:
        return f"{int(n):,}원"
    except (TypeError, ValueError):
        return "0원"


YELLOW_HEADER_STYLE = "QHeaderView::section { background-color: #FFEB3B; font-weight: bold; padding: 4px; }"


STORE_NAME = "에누리하우스"   # 상호명 (거래원장 제목 등에 사용)
APP_VERSION = "R5.0"          # 대시보드 우측 하단에 표시되는 버전

# 설정 > 편의 기능에서 켜고 끌 수 있는 항목들 (key, 화면에 보일 설명, 기본값)
CONVENIENCE_OPTIONS = [
    ("low_stock_color", "품목 목록에서 재고가 적은 품목을 색으로 표시 (30개↓ 초록 / 5개↓ 빨강)", True),
    ("auto_fee", "프로그램을 켤 때 등록된 채널 수수료율을 주문에 자동 적용", True),
    ("auto_backup", "하루에 한 번 데이터 파일 자동 백업", True),
    ("confirm_exit", "종료할 때 확인창 띄우기", True),
    ("recent_first", "상품 선택창에서 최근·매출 많은 품목을 위에 표시", True),
    ("row_numbers_big", "리포트 표의 행 번호를 크게 표시", True),
    ("save_toast", "항목 입력 후 자동 저장 확인 메시지 표시 (1초 후 사라짐)", True),
]


def conv_on(key, default=True):
    """편의 기능이 켜져 있는지 확인"""
    return _qsettings.value(f"conv/{key}", "true" if default else "false") == "true"


def to_int(s, default=0):
    """'1,234' 같은 입력을 정수로 변환"""
    s = (s or "").strip().replace(",", "")
    try:
        return int(float(s))
    except ValueError:
        return default


def to_float(s, default=0.0):
    """'17,600.5' 같은 입력을 숫자로 변환 (단가에 소수점 한 자리까지 허용)"""
    s = (s or "").strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return default


def format_phone(digits_or_text):
    """숫자만 입력해도 보기 좋게 하이픈을 넣어줌 (01076717573 -> 010-7671-7573)"""
    d = "".join(ch for ch in (digits_or_text or "") if ch.isdigit())
    if not d:
        return ""
    # 자리수가 적으면(뒷자리 검색 등) 하이픈을 넣지 않고 그대로 둠
    if len(d) < 9:
        return d
    if d.startswith("02"):                       # 서울 지역번호
        if len(d) <= 2:
            return d
        if len(d) <= 5:
            return f"{d[:2]}-{d[2:]}"
        if len(d) <= 9:
            return f"{d[:2]}-{d[2:5]}-{d[5:]}"
        return f"{d[:2]}-{d[2:6]}-{d[6:10]}"
    if len(d) <= 3:
        return d
    if len(d) <= 7:
        return f"{d[:3]}-{d[3:]}"
    if len(d) <= 11:
        return f"{d[:3]}-{d[3:-4]}-{d[-4:]}"
    return f"{d[:3]}-{d[3:7]}-{d[7:11]}"


def fmt_price(v):
    """단가 표시용 - 소수점이 있으면 한 자리까지, 없으면 정수로 표시"""
    v = v or 0
    if isinstance(v, float) and abs(v - round(v)) > 1e-9:
        return f"{v:,.1f}원"
    return f"{int(round(v)):,}원"


def _bold_column(table, col, color=None):
    """표의 특정 컬럼 글씨를 굵게 (금액처럼 눈에 띄어야 하는 칸용)"""
    try:
        for r in range(table.rowCount()):
            item = table.item(r, col)
            if item is None:
                continue
            f = item.font()
            f.setBold(True)
            item.setFont(f)
            if color:
                item.setForeground(QColor(color))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 파일 열기/저장 창이 지난번 폴더에서 열리도록 기억해두는 도우미
# ---------------------------------------------------------------------------
def _last_dir(key="default"):
    """지난번에 파일을 열거나 저장했던 폴더"""
    return str(_qsettings.value(f"lastdir/{key}", "") or "")


def _remember_dir(key, filepath):
    """방금 쓴 파일의 폴더를 기억해둠"""
    try:
        if filepath:
            _qsettings.setValue(f"lastdir/{key}", os.path.dirname(filepath))
    except Exception:
        pass


def ask_open_file(parent, caption, filter_str, key="default"):
    """파일 열기 창 - 지난번에 열었던 폴더에서 시작함"""
    path, _ = QFileDialog.getOpenFileName(parent, caption, _last_dir(key), filter_str)
    _remember_dir(key, path)
    return path


def ask_save_file(parent, caption, default_name, filter_str, key="default"):
    """파일 저장 창 - 지난번에 저장했던 폴더에서 시작함"""
    start = os.path.join(_last_dir(key), default_name) if _last_dir(key) else default_name
    path, _ = QFileDialog.getSaveFileName(parent, caption, start, filter_str)
    _remember_dir(key, path)
    return path


def ask_directory(parent, caption, key="default"):
    """폴더 선택 창 - 지난번에 골랐던 폴더에서 시작함"""
    path = QFileDialog.getExistingDirectory(parent, caption, _last_dir(key))
    if path:
        _qsettings.setValue(f"lastdir/{key}", path)
    return path


def looks_numeric(text: str) -> bool:
    """'12,345원', '35.0%', '10건', '1,234' 처럼 숫자/금액/퍼센트로 보이는 문자열이면 True"""
    if not text:
        return False
    t = text.strip()
    t = t.rstrip("원%건개")
    t = t.replace(",", "").replace("-", "").replace(".", "")
    return t.isdigit()


# ---------------------------------------------------------------------------
# 삭제 확인 (모든 삭제 기능은 반드시 이 함수를 통해 확인을 받습니다)
# ---------------------------------------------------------------------------
def confirm_delete(parent, target, detail="", extra_warning="", double_check=False,
                   title="⚠️ 삭제 확인"):
    """삭제 전에 강력한 경고와 함께 확인을 받는 공통 함수.

    target        : 무엇을 지우는지 (예: "'ABC' 카드", "주문 12건")
    detail        : 지운 뒤 어떻게 되는지 부가 설명 (선택)
    extra_warning : 특별히 더 강조할 위험 문구 (선택)
    double_check  : True면 한 번 더 물어봄 (금액/대량 데이터처럼 위험이 큰 경우)

    · 기본 버튼이 '아니오'라서 엔터를 잘못 눌러도 지워지지 않습니다.
    · 경고 아이콘과 '되돌릴 수 없습니다' 문구가 항상 표시됩니다.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(f"<b style='font-size:15px; color:#C0392B;'>{target}</b><br>정말 삭제하시겠습니까?")

    body = ["⚠️ 이 작업은 <b>되돌릴 수 없습니다.</b> 삭제된 자료는 복구할 수 없어요."]
    if extra_warning:
        body.append(f"<span style='color:#C0392B;'><b>{extra_warning}</b></span>")
    if detail:
        body.append(detail)
    body.append("걱정되면 먼저 <b>설정 &gt; 데이터 백업하기</b>로 백업해두세요.")
    box.setInformativeText("<br><br>".join(body))

    yes_btn = box.addButton("삭제합니다", QMessageBox.DestructiveRole)
    no_btn = box.addButton("취소", QMessageBox.RejectRole)
    box.setDefaultButton(no_btn)      # 실수로 엔터를 눌러도 취소가 되도록
    box.setEscapeButton(no_btn)
    box.exec()
    if box.clickedButton() is not yes_btn:
        return False

    if double_check:
        box2 = QMessageBox(parent)
        box2.setIcon(QMessageBox.Critical)
        box2.setWindowTitle("🛑 마지막 확인")
        box2.setText("<b style='font-size:15px; color:#C0392B;'>마지막 확인입니다.</b>")
        box2.setInformativeText(
            f"{target}<br><br>"
            "지금 삭제하면 <b>절대 되돌릴 수 없습니다.</b><br>"
            "그래도 진행할까요?")
        yes2 = box2.addButton("네, 삭제합니다", QMessageBox.DestructiveRole)
        no2 = box2.addButton("아니오", QMessageBox.RejectRole)
        box2.setDefaultButton(no2)
        box2.setEscapeButton(no2)
        box2.exec()
        if box2.clickedButton() is not yes2:
            return False
    return True


class YearJumpCalendarWidget(QCalendarWidget):
    """기본 달력의 월 이동 화살표(◀ ▶) 양쪽에 연도 이동 화살표(◀◀ ▶▶)를
    추가한 달력. 날짜를 고를 때 월 단위로만 넘기면 연도가 다른 날짜를
    고를 때 너무 많이 눌러야 해서, 한 번에 1년씩 건너뛸 수 있게 함"""

    def __init__(self, parent=None):
        super().__init__(parent)
        nav_bar = self.findChild(QWidget, "qt_calendar_navigationbar")
        if nav_bar is not None and nav_bar.layout() is not None:
            layout = nav_bar.layout()
            prev_year_btn = QToolButton(nav_bar)
            prev_year_btn.setText("◀◀")
            prev_year_btn.setToolTip("1년 전으로")
            prev_year_btn.clicked.connect(self.showPreviousYear)
            layout.insertWidget(0, prev_year_btn)

            next_year_btn = QToolButton(nav_bar)
            next_year_btn.setText("▶▶")
            next_year_btn.setToolTip("1년 후로")
            next_year_btn.clicked.connect(self.showNextYear)
            layout.addWidget(next_year_btn)


def make_date_edit():
    """연도 이동 화살표가 포함된 달력 팝업을 가진 QDateEdit 생성
    (앱 전체의 날짜 입력란에서 공통으로 사용)"""
    de = QDateEdit(calendarPopup=True)
    de.setCalendarWidget(YearJumpCalendarWidget())
    return de


def _sort_key_for_value(val):
    """표시된 셀 값을 정렬용 키로 변환. 숫자처럼 보이면 숫자로, 아니면 문자열로 비교
    (통화기호/콤마/단위 등을 떼어내고 숫자 여부를 판단함)"""
    if val is None:
        return (0, 0.0)
    s = str(val)
    cleaned = s.replace(",", "").replace("원", "").replace("개", "").replace("건", "").strip()
    try:
        return (0, float(cleaned))
    except ValueError:
        return (1, s.lower())


def apply_table_sort(rows, id_list, sort_state):
    """rows: 화면표시용 튜플 리스트, id_list: 같은 순서의 id 리스트(또는 None).
    sort_state에 지정된 컬럼/방향으로 정렬한 뒤 (rows, id_list)를 함께 재정렬해서
    반환함 (짝이 어긋나지 않도록 항상 같이 움직임)"""
    col = sort_state.get("column")
    if col is None:
        return rows, id_list
    ascending = sort_state.get("ascending", True)
    if id_list is not None:
        paired = list(zip(rows, id_list))
        paired.sort(key=lambda pair: _sort_key_for_value(pair[0][col]) if col < len(pair[0]) else (0, 0.0),
                    reverse=not ascending)
        new_rows = [p[0] for p in paired]
        new_ids = [p[1] for p in paired]
        return new_rows, new_ids
    else:
        new_rows = sorted(rows, key=lambda r: _sort_key_for_value(r[col]) if col < len(r) else (0, 0.0),
                           reverse=not ascending)
        return new_rows, None


def enable_header_click_sort(table, sort_state, refresh_callback, exclude_columns=()):
    """표 헤더를 클릭하면 오름차순/내림차순으로 토글하며 refresh_callback을
    호출하도록 연결. exclude_columns에 넣은 컬럼(예: 체크박스 컬럼 0번)은
    정렬 대상에서 제외됨."""
    header = table.horizontalHeader()
    header.setSortIndicatorShown(True)
    header.setSectionsClickable(True)

    def on_section_clicked(col):
        if col in exclude_columns:
            return
        if sort_state.get("column") == col:
            sort_state["ascending"] = not sort_state.get("ascending", True)
        else:
            sort_state["column"] = col
            sort_state["ascending"] = True
        header.setSortIndicator(col, Qt.AscendingOrder if sort_state["ascending"] else Qt.DescendingOrder)
        refresh_callback()

    header.sectionClicked.connect(on_section_clicked)


def enlarge_row_numbers(table, size=12):
    """표 왼쪽의 행 번호(세로 헤더) 글자 크기를 키움 - 리포트 화면에서
    번호가 너무 작아 잘 안 보인다는 요청으로 추가"""
    table.verticalHeader().setStyleSheet(f"QHeaderView::section {{ font-size: {size}px; }}")


def fill_table(table: QTableWidget, headers, rows, persist_key=None, sort_state=None, id_list=None):
    """id_list를 함께 넘기면, sort_state에 따라 rows를 정렬할 때 id_list도
    같은 순서로 재정렬해서 반환함 (호출한 쪽에서 self._ids = 반환값으로 갱신).
    id_list를 넘기지 않으면 그냥 None을 반환함."""
    if sort_state is not None:
        rows, id_list = apply_table_sort(list(rows), list(id_list) if id_list is not None else None, sort_state)

    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            text = str(val) if val is not None else ""
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if looks_numeric(text):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(r, c, item)

    header = table.horizontalHeader()
    if persist_key:
        header.blockSignals(True)  # resizeColumnsToContents가 저장된 폭을 덮어쓰지 않도록
    table.resizeColumnsToContents()
    # 내용에 딱 맞추면 글자가 답답해 보여서 컬럼마다 약간의 여유를 더함
    for c in range(table.columnCount()):
        table.setColumnWidth(c, table.columnWidth(c) + 18)
    if persist_key:
        header.blockSignals(False)

    # 요청하신 대로 표 헤더(컬럼) 배경을 노란색으로
    table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)
    # 사용자가 컬럼 경계를 드래그해서 폭을 직접 조정할 수 있게 함
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    # 마지막 컬럼이 남는 공간 전체로 늘어나면 메모칸만 과하게 넓어져서 해제
    table.horizontalHeader().setStretchLastSection(False)
    if persist_key:
        restore_column_widths(table, persist_key)

    if sort_state is not None:
        header.setSortIndicatorShown(True)
        header.setSortIndicator(sort_state.get("column", -1) or -1,
                                 Qt.AscendingOrder if sort_state.get("ascending", True) else Qt.DescendingOrder)

    return id_list


# ---------------------------------------------------------------------------
# 수동 컬럼 매칭 다이얼로그 (자동 인식이 부족할 때)
# ---------------------------------------------------------------------------
def export_ledger_to_excel(parent, channel_name, date_from, date_to, entries):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    if not entries:
        QMessageBox.information(parent, "알림", "해당 기간에 거래 내역이 없습니다.")
        return

    filepath, _ = QFileDialog.getSaveFileName(
        parent, "거래원장 엑셀로 저장",
        os.path.join(_last_dir("ledger"), f"{channel_name}_거래원장_{date_from}_{date_to}.xlsx"),
        "Excel 파일 (*.xlsx)"
    )
    if not filepath:
        return

    headers = ["일자", "거래처명", "구매자", "거래형식", "품목", "수량", "단가",
               "합계금액", "미수금액", "정산여부", "적요"]
    wb = Workbook()
    ws = wb.active
    ws.title = "거래원장"

    # A4 가로 + 여백/맞춤 설정
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "3:3"  # 페이지마다 헤더 반복

    last_col = get_column_letter(len(headers))

    # 1행: 큰 글씨 제목 "상호 거래원장"
    ws.merge_cells(f"A1:{last_col}1")
    title_cell = ws["A1"]
    title_cell.value = f"{STORE_NAME}  거래원장"
    title_cell.font = Font(size=22, bold=True)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 34

    # 2행: 거래처명 + 조회 기간
    ws.merge_cells(f"A2:{last_col}2")
    sub_cell = ws["A2"]
    sub_cell.value = f"거래처 : {channel_name}          기간 : {date_from} ~ {date_to}"
    sub_cell.font = Font(size=12)
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22

    # 3행: 표 헤더
    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="FFEB3B")
    for c, name in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=c, value=name)
        cell.font = Font(bold=True, size=11)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border
    ws.row_dimensions[3].height = 22

    # 4행부터 데이터
    row_idx = 4
    for e in entries:
        values = [
            e["date"], channel_name, e.get("buyer", ""), e.get("kind", "매출"),
            e["product"], e["qty"], e["unit_price"], e["amount"], e.get("balance", 0),
            e.get("settled", ""), "",
        ]
        for c, val in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=c, value=val)
            cell.border = border
            cell.font = Font(size=10)
            if c in (5, 6, 7, 8):
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
            elif c in (1, 3):
                cell.alignment = Alignment(horizontal="center")
        row_idx += 1

    # 마지막 합계 행
    sales_total = sum(e["amount"] for e in entries if e.get("kind") != "입금")
    received_total = -sum(e["amount"] for e in entries if e.get("kind") == "입금")
    balance = sales_total - received_total
    total_fill = PatternFill("solid", fgColor="F0F0F0")
    total_values = ["", "", "", "합 계", "", f"매출 {sales_total:,} / 입금 {received_total:,}",
                    sales_total, balance, "", ""]
    for c, val in enumerate(total_values, start=1):
        cell = ws.cell(row=row_idx, column=c, value=val)
        cell.font = Font(bold=True, size=11)
        cell.fill = total_fill
        cell.border = border
        if c in (7, 8):
            cell.number_format = "#,##0"
            cell.alignment = Alignment(horizontal="right")
        elif c == 4:
            cell.alignment = Alignment(horizontal="center")

    # 컬럼 폭을 내용 길이에 맞게 조정 (한글은 폭을 넓게 계산)
    def display_len(v):
        s = "" if v is None else str(v)
        return sum(2 if ord(ch) > 127 else 1 for ch in s)

    for c, name in enumerate(headers, start=1):
        longest = display_len(name)
        for r in range(4, row_idx + 1):
            v = ws.cell(row=r, column=c).value
            if isinstance(v, (int, float)):
                v = f"{v:,}"
            longest = max(longest, display_len(v))
        ws.column_dimensions[get_column_letter(c)].width = min(max(longest + 4, 9), 42)

    ws.freeze_panes = "A4"
    try:
        wb.save(filepath)
    finally:
        wb.close()   # 파일 잠금이 남지 않도록 반드시 닫음
    _remember_dir("ledger", filepath)
    QMessageBox.information(parent, "완료", "거래원장을 엑셀로 저장했습니다. (A4 가로 규격)")


def export_ledger_to_pdf(parent, channel_name, date_from, date_to, entries):
    if not entries:
        QMessageBox.information(parent, "알림", "해당 기간에 거래 내역이 없습니다.")
        return
    filepath, _ = QFileDialog.getSaveFileName(
        parent, "거래원장 PDF로 저장",
        os.path.join(_last_dir("ledger"), f"{channel_name}_거래원장_{date_from}_{date_to}.pdf"),
        "PDF 파일 (*.pdf)"
    )
    if not filepath:
        return
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm

        font_name = "HYSMyeongJo-Medium"
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))

        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        title_style.fontName = font_name

        doc = SimpleDocTemplate(filepath, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm)
        elements = [
            Paragraph(f"{channel_name} 거래 원장 ({date_from} ~ {date_to})", title_style),
            Spacer(1, 8),
        ]

        table_data = [["일자", "구매자", "거래형식", "품목", "수량", "단가", "합계금액", "미수금액", "적요"]]
        total = 0
        for e in entries:
            table_data.append([
                e["date"], (e.get("buyer") or channel_name), e.get("kind", "매출"), e["product"],
                f"{e['qty']:,}", f"{e['unit_price']:,}", f"{e['amount']:,}",
                f"{e.get('balance', 0):,}", e.get("settled", ""), "",
            ])
            total += e["amount"]
        table_data.append(["", "", "", "", "", "Total", f"₩{total:,}", "", ""])

        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFEB3B")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f0f0")),
            ("ALIGN", (4, 1), (6, -1), "RIGHT"),
        ]))
        elements.append(table)
        doc.build(elements)
        _remember_dir("ledger", filepath)
        QMessageBox.information(parent, "완료", "거래원장을 PDF로 저장했습니다.")
    except Exception as e:
        QMessageBox.critical(parent, "오류", f"PDF 생성 중 오류가 발생했습니다:\n{e}")


class ColumnMappingDialog(QDialog):
    FIELD_LABELS = {
        "order_no": "주문번호 *",
        "order_date": "주문일자",
        "product_name": "상품명 *",
        "option_name": "옵션명",
        "qty": "수량",
        "sale_price": "판매단가",
        "total_amount": "결제금액 *",
        "fee_amount": "수수료",
        "shipping_fee": "배송비",
        "settlement_amount": "정산금액",
        "buyer_name": "구매자명",
        "status": "주문상태",
    }

    def __init__(self, columns, current_mapping, parent=None):
        super().__init__(parent)
        self.setWindowTitle("컬럼 매칭 확인 / 수정")
        self.resize(420, 500)
        self.combo_boxes = {}

        layout = QVBoxLayout(self)
        info = QLabel("자동 인식이 안 된 항목이 있어요. 실제 파일의 컬럼을 선택해 주세요.\n(* 표시는 필수 항목)")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        for field, label in self.FIELD_LABELS.items():
            combo = QComboBox()
            combo.addItem("(선택 안 함)", None)
            for col in columns:
                combo.addItem(str(col), str(col))
            current_val = current_mapping.get(field)
            if current_val:
                idx = combo.findData(current_val)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            form.addRow(label, combo)
            self.combo_boxes[field] = combo
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_mapping(self):
        return {field: combo.currentData() for field, combo in self.combo_boxes.items()}


# ---------------------------------------------------------------------------
# 채널 상세보기 다이얼로그 (대시보드에서 더블클릭)
# ---------------------------------------------------------------------------
class ChannelDetailDialog(QDialog):
    def __init__(self, channel_id, channel_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{channel_name} - 상세보기")
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        title = QLabel(f"📊 {channel_name} 상세 현황")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # 요약
        summary_rows = [r for r in db.get_channel_summary() if r["channel_id"] == channel_id]
        if summary_rows:
            s = summary_rows[0]
            summary_text = (
                f"주문건수: {s['order_count']}건   |   매출: {fmt_won(s['total_sales'])}   |   "
                f"수수료: {fmt_won(s['total_fee'])}   |   정산금액: {fmt_won(s['total_settlement'])}"
            )
            summary_label = QLabel(summary_text)
            summary_label.setStyleSheet("padding: 6px; background: #f0f0f0;")
            layout.addWidget(summary_label)

        layout.addWidget(QLabel("상품별 판매 집계"))
        product_table = QTableWidget()
        product_rows = db.get_product_sales_by_channel(channel_id)
        fill_table(
            product_table,
            ["상품명", "판매수량", "매출", "정산금액", "주문건수"],
            [(r["product_name"], r["total_qty"], fmt_won(r["total_sales"]),
              fmt_won(r["total_settlement"]), r["order_count"]) for r in product_rows]
        )
        layout.addWidget(product_table)

        layout.addWidget(QLabel("주문 내역 (최근순)"))
        order_table = QTableWidget()
        order_rows = db.get_orders(channel_id=channel_id)
        fill_table(
            order_table,
            ["주문번호", "주문일", "상품명", "옵션", "수량", "결제금액", "정산금액", "상태"],
            [(o["order_no"], o["order_date"], o["product_name"], o["option_name"],
              o["qty"], fmt_won(o["total_amount"]), fmt_won(o["settlement_amount"]), o["status"])
             for o in order_rows]
        )
        layout.addWidget(order_table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# ---------------------------------------------------------------------------
# 대시보드 탭
# ---------------------------------------------------------------------------
class DashboardSettingsDialog(QDialog):
    """대시보드 상호명/글꼴/크기/디자인 설정"""

    FONTS = ["맑은 고딕", "나눔고딕", "나눔스퀘어", "돋움", "굴림", "바탕", "Arial", "Segoe UI"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("대시보드 설정")
        self.resize(420, 320)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.store_input = QLineEdit(_qsettings.value("dashboard/store_name", STORE_NAME))
        form.addRow("상호명", self.store_input)

        self.subtitle_input = QLineEdit(
            _qsettings.value("dashboard/subtitle", "온라인 판매 통합 장부"))
        form.addRow("부제목", self.subtitle_input)

        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.addItems(self.FONTS)
        saved_font = _qsettings.value("dashboard/font", "")
        if saved_font:
            self.font_combo.setCurrentText(saved_font)
        else:
            self.font_combo.setCurrentIndex(0)
        form.addRow("글꼴", self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(20, 90)
        self.size_spin.setValue(int(_qsettings.value("dashboard/font_size", 48) or 48))
        self.size_spin.setSuffix(" px")
        form.addRow("상호 글자 크기", self.size_spin)

        # 상호 글자색 / 대시보드 바탕색 직접 선택
        self.text_color = _qsettings.value("dashboard/text_color", "") or ""
        self.text_color_btn = QPushButton("색 선택")
        self.text_color_btn.clicked.connect(lambda: self._pick_color("text"))
        text_color_row = QWidget()
        tcl = QHBoxLayout(text_color_row); tcl.setContentsMargins(0,0,0,0)
        self.text_color_preview = QLabel("  ")
        self.text_color_preview.setFixedSize(28, 22)
        tcl.addWidget(self.text_color_preview); tcl.addWidget(self.text_color_btn)
        clear_t = QPushButton("기본값")
        clear_t.clicked.connect(lambda: self._clear_color("text"))
        tcl.addWidget(clear_t); tcl.addStretch()
        form.addRow("상호 글자색", text_color_row)

        self.bg_color = _qsettings.value("dashboard/bg_color", "") or ""
        self.bg_color_btn = QPushButton("색 선택")
        self.bg_color_btn.clicked.connect(lambda: self._pick_color("bg"))
        bg_color_row = QWidget()
        bcl = QHBoxLayout(bg_color_row); bcl.setContentsMargins(0,0,0,0)
        self.bg_color_preview = QLabel("  ")
        self.bg_color_preview.setFixedSize(28, 22)
        bcl.addWidget(self.bg_color_preview); bcl.addWidget(self.bg_color_btn)
        clear_b = QPushButton("기본값")
        clear_b.clicked.connect(lambda: self._clear_color("bg"))
        bcl.addWidget(clear_b); bcl.addStretch()
        form.addRow("대시보드 바탕색", bg_color_row)
        self.insight_cb = QCheckBox("판매 인사이트 패널 표시")
        self.insight_cb.setChecked(_qsettings.value("dashboard/insight_on", "true") == "true")
        form.addRow("판매 인사이트", self.insight_cb)

        self.design_combo = QComboBox()
        for key, label in DashboardTab.DESIGN_NAMES.items():
            self.design_combo.addItem(label, key)
        cur_design = int(_qsettings.value("dashboard/design", 1) or 1)
        idx = self.design_combo.findData(cur_design)
        if idx >= 0:
            self.design_combo.setCurrentIndex(idx)
        form.addRow("디자인", self.design_combo)

        layout.addLayout(form)

        self.preview = QLabel("")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#F4F6F7; border-radius:8px; padding:16px;")
        layout.addWidget(self.preview)
        for wdg, sig in ((self.store_input, "textChanged"), (self.size_spin, "valueChanged")):
            getattr(wdg, sig).connect(self._update_preview)
        self.font_combo.currentTextChanged.connect(self._update_preview)
        self._update_preview()

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _pick_color(self, which):
        from PySide6.QtWidgets import QColorDialog
        current = self.text_color if which == "text" else self.bg_color
        color = QColorDialog.getColor(QColor(current) if current else QColor("#2C3E50"), self)
        if color.isValid():
            if which == "text":
                self.text_color = color.name()
            else:
                self.bg_color = color.name()
            self._update_preview()

    def _clear_color(self, which):
        if which == "text":
            self.text_color = ""
        else:
            self.bg_color = ""
        self._update_preview()

    def _update_preview(self):
        self.preview.setText(self.store_input.text() or STORE_NAME)
        bg = self.bg_color or "#F4F6F7"
        fg = self.text_color or "#2C3E50"
        self.preview.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:8px; padding:16px;"
            f"font-family:'{self.font_combo.currentText()}';"
            f"font-size:{min(self.size_spin.value(), 40)}px; font-weight:800;")
        self.text_color_preview.setStyleSheet(
            f"background:{fg}; border:1px solid #999; border-radius:3px;")
        self.bg_color_preview.setStyleSheet(
            f"background:{bg}; border:1px solid #999; border-radius:3px;")

    def save(self):
        _qsettings.setValue("dashboard/store_name", self.store_input.text().strip() or STORE_NAME)
        _qsettings.setValue("dashboard/subtitle", self.subtitle_input.text().strip())
        _qsettings.setValue("dashboard/font", self.font_combo.currentText().strip())
        _qsettings.setValue("dashboard/font_size", self.size_spin.value())
        _qsettings.setValue("dashboard/design", self.design_combo.currentData())
        _qsettings.setValue("dashboard/text_color", self.text_color)
        _qsettings.setValue("dashboard/bg_color", self.bg_color)
        _qsettings.setValue("dashboard/insight_on", "true" if self.insight_cb.isChecked() else "false")
        self.accept()


class DashboardTab(QWidget):
    """단순한 홈 화면 - 상호명과 연결된 판매채널을 예쁘게 보여줌.
    2026년 디자인 트렌드(그라데이션/글래스모피즘/미니멀) 중 하나를 골라 쓸 수 있음"""

    # 상호명은 위쪽 전역 상수(STORE_NAME)를 사용

    # 채널명에 어울리는 아이콘/색상 (실제 로고 대신 이모지+브랜드 느낌 색상 사용)
    CHANNEL_STYLE = {
        "스마트스토어": ("🛍️", "#03C75A", "#1DE9B6"),   # 네이버 그린 계열
        "11번가": ("🏬", "#FF0038", "#FF6B6B"),          # 11번가 레드 계열
        "쿠팡": ("🚀", "#4A90D9", "#7C4DFF"),            # 쿠팡 블루 계열
        "ESM(G마켓/옥션)": ("🏪", "#FFB300", "#FF7043"),  # 옥션/지마켓 옐로우 계열
        "기타": ("🏷️", "#9E9E9E", "#B0BEC5"),
        "일반매출": ("🤝", "#8E44AD", "#BB8FCE"),   # 온라인 채널 외 일반거래처 매출 합계
    }
    DEFAULT_STYLE = ("🛒", "#7E57C2", "#B388FF")

    DESIGN_NAMES = {1: "🌈 그라데이션", 2: "🌙 다크(매출표시)", 3: "◽ 미니멀", 4: "📡 실시간 주문(API)"}

    def __init__(self):
        super().__init__()
        self._design = int(_qsettings.value("dashboard/design", 1) or 1)

        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(40, 30, 40, 30)

        # 디자인 선택 버튼 (오른쪽 위, 작게)
        design_row = QHBoxLayout()
        design_row.addStretch()
        design_label = QLabel("디자인:")
        design_label.setStyleSheet("color: #999; font-size: 12px;")
        design_row.addWidget(design_label)
        self._design_buttons = {}
        for key, label in self.DESIGN_NAMES.items():
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked, k=key: self.set_design(k))
            design_row.addWidget(btn)
            self._design_buttons[key] = btn
        settings_btn = QPushButton("⚙️")
        settings_btn.setToolTip("대시보드 설정 (상호명·글씨체·크기·디자인)")
        settings_btn.setFixedSize(28, 26)
        settings_btn.clicked.connect(self.open_settings)
        design_row.addWidget(settings_btn)
        self.outer.addLayout(design_row)

        self.outer.addStretch(1)

        self.store_label = QLabel(STORE_NAME)
        self.store_label.setAlignment(Qt.AlignCenter)
        self.outer.addWidget(self.store_label)

        self.subtitle_label = QLabel("온라인 판매 통합 장부")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.outer.addWidget(self.subtitle_label)

        self.outer.addSpacing(30)

        self.card_row = QHBoxLayout()
        self.card_row.setSpacing(24)
        self.outer.addLayout(self.card_row)

        self.outer.addStretch(2)

        # 판매 인사이트 패널 (켜져있을 때만)
        self.insight_box = QGroupBox("📊 판매 인사이트")
        self.insight_box.setStyleSheet(
            "QGroupBox { background: #FDFEFE; border: 1px solid #AED6F1;"
            "border-radius: 8px; padding: 8px; font-size: 13px; }"
            "QGroupBox::title { color: #1A5276; font-weight: bold; }")
        insight_layout = QVBoxLayout(self.insight_box)
        insight_ctrl = QHBoxLayout()
        self.insight_period = QComboBox()
        self.insight_period.addItems(["최근 7일", "최근 15일", "이번달", "지난달", "올해"])
        self.insight_period.currentIndexChanged.connect(self._refresh_insight)
        insight_ctrl.addWidget(QLabel("기간:"))
        insight_ctrl.addWidget(self.insight_period)
        insight_ctrl.addStretch()
        insight_layout.addLayout(insight_ctrl)
        self.insight_text = QLabel("데이터를 불러오는 중...")
        self.insight_text.setWordWrap(True)
        self.insight_text.setStyleSheet("font-size: 12px; color: #2C3E50; padding: 4px;")
        self.insight_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        insight_layout.addWidget(self.insight_text)
        self.outer.addWidget(self.insight_box)

        # 우측 하단에 버전 표시
        version_row = QHBoxLayout()
        version_row.addStretch()
        self.version_label = QLabel(APP_VERSION)
        self.version_label.setStyleSheet("color: #95A5A6; font-size: 12px; background: transparent;")
        version_row.addWidget(self.version_label)
        self.outer.addLayout(version_row)

        self._cards = []
        self.api_preview_box = None
        self._update_design_buttons()
        self.refresh()

    def open_settings(self):
        if DashboardSettingsDialog(self).exec() == QDialog.Accepted:
            self._design = int(_qsettings.value("dashboard/design", self._design) or self._design)
            self._update_design_buttons()
            self.refresh()

    def set_design(self, design_id):
        self._design = design_id
        _qsettings.setValue("dashboard/design", design_id)
        self._update_design_buttons()
        self.refresh()

    def _update_design_buttons(self):
        for key, btn in self._design_buttons.items():
            btn.setChecked(key == self._design)

    # ---------- 배경/제목 스타일 (디자인별) ----------
    def _refresh_insight(self):
        """판매 추이 인사이트를 분석해서 텍스트로 표시"""
        try:
            from datetime import date as _date, timedelta as _td
            _today = _date.today()
            period_text = self.insight_period.currentText()
            today_str = _today.isoformat()
            if period_text == "최근 7일":
                since = (_today - _td(days=6)).isoformat()
            elif period_text == "최근 15일":
                since = (_today - _td(days=14)).isoformat()
            elif period_text == "이번달":
                since = _date(_today.year, _today.month, 1).isoformat()
            elif period_text == "지난달":
                first_this = _date(_today.year, _today.month, 1)
                last_end = first_this - _td(days=1)
                since = _date(last_end.year, last_end.month, 1).isoformat()
                today_str = last_end.isoformat()
            elif period_text == "올해":
                since = _date(_today.year, 1, 1).isoformat()
            else:
                since = (_today - _td(days=6)).isoformat()
            data = db.get_insight_data_range(since, today_str)
            # 총 집계는 get_profit_by_period로 정확하게
            period_rows = db.get_profit_by_period("day", date_from=since, date_to=today_str)
            data["totals"] = {
                "sales": sum(r["total_sales"] or 0 for r in period_rows),
                "fee": sum(r["total_fee"] or 0 for r in period_rows),
                "cost": sum(r["total_cost"] or 0 for r in period_rows),
                "profit": sum(r["profit"] or 0 for r in period_rows),
            }
            products = data["products"]
            expenses = data["expenses"]
            totals = data["totals"]
            lines = []

            sales = totals.get("sales") or 0
            profit = totals.get("profit") or 0
            profit_rate = profit / sales * 100 if sales else 0

            lines.append(f"📅 {self.insight_period.currentText()}  |  "
                         f"총 매출 {sales:,.0f}원  |  이익 {profit:,.0f}원  |  이익률 {profit_rate:.1f}%")
            lines.append("")

            def short_name(name, max_len=16):
                """상품명을 짧게 축약"""
                if not name: return ""
                # 긴 수식어 제거 패턴
                import re as _re
                n = _re.sub(r'[가-힣A-Za-z0-9]+[시ml]?\s*x?\s*[가-힣A-Za-z0-9]+cm[가-힣A-Za-z0-9]*', '', name)
                n = _re.sub(r'\s+', ' ', n).strip() or name
                return n[:max_len] + ("…" if len(n) > max_len else "")

            if products:
                top = products[0]
                opt = f" {top['option_name']}" if top.get('option_name') else ""
                lines.append(f"🏆 판매량 1위: {top['product_name']}{opt} "
                             f"({top['total_qty']:,.0f}개 / {top['total_sales']:,.0f}원)")

                with_rate = [(p, (p["total_sales"] or 0) - (p["total_cost"] or 0))
                             for p in products if (p["total_sales"] or 0) > 0
                             and (p["total_cost"] or 0) > 0]
                if with_rate:
                    best = max(with_rate, key=lambda x: x[1]/max(x[0]["total_sales"],1))
                    worst = min(with_rate, key=lambda x: x[1]/max(x[0]["total_sales"],1))
                    best_rate = best[1]/best[0]["total_sales"]*100
                    worst_rate = worst[1]/worst[0]["total_sales"]*100
                    b_opt = f" {best[0]['option_name']}" if best[0].get('option_name') else ""
                    lines.append(f"📈 수익률 최고: {best[0]['product_name']}{b_opt} ({best_rate:.1f}%)")
                    if worst_rate < 10:
                        w_opt = f" {worst[0]['option_name']}" if worst[0].get('option_name') else ""
                        lines.append(f"⚠️  수익률 주의: {worst[0]['product_name']}{w_opt} "
                                     f"({worst_rate:.1f}%) → 원가/판매가 점검 필요")

                low_seller = min(products, key=lambda p: p["total_qty"] or 0)
                l_opt = f" {low_seller['option_name']}" if low_seller.get('option_name') else ""
                lines.append(f"📉 판매량 최저: {low_seller['product_name']}{l_opt} "
                             f"({low_seller['total_qty']:,.0f}개)")

            lines.append("")
            if expenses:
                total_exp = sum(e["total"] or 0 for e in expenses)
                # 급여 제외한 상위 3개 지출 항목 표시
                non_salary = [e for e in expenses if e["category"] not in ("급여","인건비","급여비")]
                for i, e in enumerate(non_salary[:3]):
                    lines.append(f"💸 지출{i+1}: {e['category']} ({e['total']:,.0f}원)")
                exp_ratio = total_exp / sales * 100 if sales else 0
                if exp_ratio > 30:
                    lines.append(f"⚠️  지출이 매출의 {exp_ratio:.1f}%입니다 — 비용 절감 검토를 권합니다")
                else:
                    lines.append(f"✅ 지출 비율 {exp_ratio:.1f}% — 적정 수준입니다")

            self.insight_text.setText("\n".join(lines))
        except Exception as e:
            self.insight_text.setText(f"데이터 없음 ({e})")

    def _apply_page_style(self):
        # 사용자가 정한 글꼴/크기를 상호명에 덧입힘
        self._font_css = ""
        font = _qsettings.value("dashboard/font", "")
        size = int(_qsettings.value("dashboard/font_size", 48) or 48)
        if font:
            self._font_css += f"font-family:'{font}';"
        self._font_css += f"font-size:{size}px;"

        if self._design == 1:  # 그라데이션
            self.setStyleSheet("DashboardTab { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                                "stop:0 #F5F7FA, stop:1 #E8ECF4); }")
            self.store_label.setStyleSheet("font-size: 48px; font-weight: 800; color: #2C3E50; letter-spacing: 2px; background: transparent;")
            self.subtitle_label.setStyleSheet("font-size: 16px; color: #888; background: transparent;")
            self._apply_user_font()
        elif self._design == 2:  # 다크 (채널별 이번 달 매출 표시)
            self.setStyleSheet("DashboardTab { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                                "stop:0 #1C2833, stop:1 #212F3D); }")
            self.store_label.setStyleSheet("font-size: 48px; font-weight: 800; color: #ECF0F1; letter-spacing: 2px; background: transparent;")
            self.subtitle_label.setStyleSheet("font-size: 16px; color: #7F8C8D; background: transparent;")
            self._apply_user_font()
        elif self._design == 4:  # 실시간 주문(API) - 콘솔 느낌의 진한 배경
            self.setStyleSheet("DashboardTab { background: #0F172A; }")
            self.store_label.setStyleSheet("font-size: 36px; font-weight: 800; color: #E2E8F0; letter-spacing: 1px; background: transparent;")
            self.subtitle_label.setStyleSheet("font-size: 14px; color: #64748B; background: transparent;")
            self._apply_user_font()
        else:  # 미니멀
            self.setStyleSheet("DashboardTab { background: #FFFFFF; }")
            self.store_label.setStyleSheet("font-size: 44px; font-weight: 700; color: #111827; letter-spacing: -1px; background: transparent;")
            self.subtitle_label.setStyleSheet("font-size: 14px; color: #9CA3AF; background: transparent;")
            self._apply_user_font()

    # ---------- 카드 생성 (디자인별) ----------
    def _build_api_preview(self, online_channels):
        """API 연동 후 실시간 주문을 보여줄 화면의 디자인 시안 (지금은 화면만)"""
        if self.api_preview_box is not None:
            self.api_preview_box.setParent(None)
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        status = QLabel("📡  마켓 API 연동  ·  준비중 (디자인 시안)")
        status.setAlignment(Qt.AlignCenter)
        status.setStyleSheet(
            "background-color: rgba(251,191,36,0.15); color: #FBBF24; border: 1px solid #B45309;"
            "border-radius: 8px; padding: 8px; font-size: 12px;")
        v.addWidget(status)

        # 상단 지표 4개
        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        month_total = sum(self._month_sales_map.values()) if self._month_sales_map else 0
        for label_text, value, color in [
            ("오늘 신규주문", "—", "#38BDF8"),
            ("발송 대기", "—", "#FBBF24"),
            ("이번 달 매출", fmt_won(month_total), "#34D399"),
            ("연동 채널", f"{len(online_channels)}개", "#A78BFA"),
        ]:
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background-color: #1E293B; border: 1px solid #334155;"
                f"border-top: 3px solid {color}; border-radius: 10px; }}")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 10)
            t = QLabel(label_text)
            t.setStyleSheet("color: #94A3B8; font-size: 11px; border: none;")
            val = QLabel(value)
            val.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold; border: none;")
            cl.addWidget(t)
            cl.addWidget(val)
            metrics.addWidget(card)
        v.addLayout(metrics)

        # 실시간 주문 목록 (샘플 레이아웃)
        list_frame = QFrame()
        list_frame.setStyleSheet(
            "QFrame { background-color: #1E293B; border: 1px solid #334155; border-radius: 10px; }")
        lf = QVBoxLayout(list_frame)
        lf.setContentsMargins(16, 12, 16, 12)
        lf.setSpacing(6)

        head = QLabel("실시간 주문 수신")
        head.setStyleSheet("color: #E2E8F0; font-size: 14px; font-weight: bold; border: none;")
        lf.addWidget(head)

        col = QLabel("　수신시각　│　채널　│　주문번호　│　상품　│　수량　│　금액　│　상태")
        col.setStyleSheet("color: #64748B; font-size: 11px; border: none; padding: 4px 0;")
        lf.addWidget(col)

        for icon, ch_name, color in [("🛍️", "스마트스토어", "#03C75A"),
                                      ("🚀", "쿠팡", "#4A90D9"),
                                      ("🏬", "11번가", "#FF6B6B")]:
            row = QLabel(f"　--:--:--　│  {icon} {ch_name}　│　-　│　-　│　-　│　-　│　대기중")
            row.setStyleSheet(
                f"color: #94A3B8; font-size: 12px; border: none; border-left: 3px solid {color};"
                "padding: 6px 10px; background-color: rgba(255,255,255,0.02);")
            lf.addWidget(row)

        hint = QLabel("API 연동이 완료되면 각 마켓의 주문이 이 목록에 실시간으로 쌓입니다.")
        hint.setStyleSheet("color: #64748B; font-size: 11px; border: none; padding-top: 8px;")
        lf.addWidget(hint)
        v.addWidget(list_frame)

        self.api_preview_box = box
        self.outer.insertWidget(self.outer.count() - 1, box)

    def _apply_user_font(self):
        """디자인별 기본 스타일에 사용자가 고른 글꼴·크기·색을 덧붙임"""
        extra = self._font_css
        text_color = _qsettings.value("dashboard/text_color", "") or ""
        if text_color:
            extra += f"color:{text_color};"
        self.store_label.setStyleSheet(self.store_label.styleSheet() + extra)
        # 바탕색을 정했으면 디자인 배경 대신 그 색을 사용
        bg = _qsettings.value("dashboard/bg_color", "") or ""
        if bg:
            self.setStyleSheet(f"DashboardTab {{ background: {bg}; }}")

    def _make_card_gradient(self, channel_name):
        icon, color1, color2 = self.CHANNEL_STYLE.get(channel_name, self.DEFAULT_STYLE)
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {color1}, stop:1 {color2});
                border-radius: 18px;
            }}
        """)
        card.setFixedSize(170, 150)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(color1))
        shadow.setOffset(0, 8)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignCenter)
        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 42px; background: transparent;")
        card_layout.addWidget(icon_label)
        name_label = QLabel(channel_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: white; background: transparent;")
        card_layout.addWidget(name_label)
        return card

    def _make_card_dark(self, channel_name):
        """다크 카드 - 채널별 이번 달 매출을 함께 보여주는 실용형 디자인"""
        icon, color1, color2 = self.CHANNEL_STYLE.get(channel_name, self.DEFAULT_STYLE)
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #2C3E50;
                border: 1px solid #3E5871;
                border-bottom: 4px solid {color1};
                border-radius: 12px;
            }}
        """)
        card.setFixedSize(180, 150)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 90))
        shadow.setOffset(0, 5)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(4)

        top_row = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 24px; background: transparent; border: none;")
        top_row.addWidget(icon_label)
        top_row.addStretch()
        card_layout.addLayout(top_row)

        name_label = QLabel(channel_name)
        name_label.setWordWrap(True)
        name_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {color2}; background: transparent; border: none;")
        card_layout.addWidget(name_label)

        card_layout.addStretch()

        month_sales = (self._general_sales if channel_name == "일반매출"
                        else self._month_sales_map.get(channel_name, 0))
        sales_caption = QLabel("이번 달 매출")
        sales_caption.setStyleSheet("font-size: 10px; color: #95A5A6; background: transparent; border: none;")
        card_layout.addWidget(sales_caption)
        sales_label = QLabel(fmt_won(month_sales))
        sales_label.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: white; background: transparent; border: none;")
        card_layout.addWidget(sales_label)
        return card

    def _make_card_minimal(self, channel_name):
        icon, color1, _ = self.CHANNEL_STYLE.get(channel_name, self.DEFAULT_STYLE)
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #FAFAFA;
                border: 1px solid #EEEEEE;
                border-top: 3px solid {color1};
                border-radius: 10px;
            }}
        """)
        card.setFixedSize(170, 140)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(14)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 3)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignCenter)
        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 32px; background: transparent;")
        card_layout.addWidget(icon_label)
        name_label = QLabel(channel_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #374151; background: transparent;")
        card_layout.addWidget(name_label)
        return card

    def refresh(self):
        # 사용자가 설정한 상호명/부제목 적용
        self.store_label.setText(_qsettings.value("dashboard/store_name", STORE_NAME))
        self.subtitle_label.setText(_qsettings.value("dashboard/subtitle", "온라인 판매 통합 장부"))
        self._apply_page_style()
        insight_on = _qsettings.value("dashboard/insight_on", "true") == "true"
        self.insight_box.setVisible(insight_on)
        if insight_on:
            self._refresh_insight()

        # 다크 디자인 카드에 표시할 채널별 이번 달 매출 집계
        self._month_sales_map = {}
        this_month = date.today().strftime("%Y-%m")
        try:
            for r in db.get_channel_profit_for_month(this_month):
                self._month_sales_map[r["channel_name"]] = r["total_sales"]
        except Exception:
            self._month_sales_map = {}

        # 온라인 채널이 아닌 일반거래처들의 매출을 하나로 묶어 "일반매출"로 집계
        try:
            self._general_sales = db.get_general_sales_total(this_month)
        except Exception:
            self._general_sales = 0
        self._month_sales_map["일반매출"] = self._general_sales

        for card in self._cards:
            self.card_row.removeWidget(card)
            card.setParent(None)
        self._cards = []

        channels = db.get_channels()
        online_channels = [
            c for c in channels
            if (c["channel_type"] or "온라인채널") == "온라인채널" and c["name"] != "기타"
        ]

        # 📡 실시간 주문(API) 디자인은 카드 대신 주문 현황 패널을 보여줌
        if self._design == 4:
            self._build_api_preview(online_channels)
            return

        if self.api_preview_box is not None:
            self.api_preview_box.setParent(None)
            self.api_preview_box = None

        make_card = {1: self._make_card_gradient, 2: self._make_card_dark,
                     3: self._make_card_minimal}[self._design]

        self.card_row.addStretch(1)
        for ch in online_channels:
            card = make_card(ch["name"])
            self.card_row.addWidget(card)
            self._cards.append(card)
        # 일반거래처(직거래·도매 등) 매출 카드 1개를 맨 뒤에 추가
        general_card = make_card("일반매출")
        self.card_row.addWidget(general_card)
        self._cards.append(general_card)
        self.card_row.addStretch(1)


# ---------------------------------------------------------------------------
# 주문관리 탭 (파일 업로드 핵심 기능)
# ---------------------------------------------------------------------------
PERIOD_PRESETS = [
    ("최근 7일", "recent7"),
    ("최근 15일", "recent15"),
    ("최근 30일", "recent30"),
    ("이번달", "this_month"),
    ("지난달", "last_month"),
    ("올해", "this_year"),
    ("전체 기간", "all"),
]


def compute_period_range(preset_key):
    """프리셋 키를 받아 (date_from, date_to) 문자열 튜플을 반환 ('all'이면 (None, None))"""
    today = QDate.currentDate()
    if preset_key == "recent7":
        return today.addDays(-6).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
    if preset_key == "recent15":
        return today.addDays(-14).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
    if preset_key == "recent30":
        return today.addDays(-29).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
    if preset_key == "this_month":
        first = QDate(today.year(), today.month(), 1)
        return first.toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
    if preset_key == "last_month":
        first_this_month = QDate(today.year(), today.month(), 1)
        last_day_prev = first_this_month.addDays(-1)
        first_day_prev = QDate(last_day_prev.year(), last_day_prev.month(), 1)
        return first_day_prev.toString("yyyy-MM-dd"), last_day_prev.toString("yyyy-MM-dd")
    if preset_key == "this_year":
        return QDate(today.year(), 1, 1).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
    return None, None  # "all"


def make_period_combo(default_key="all"):
    """조회 기간 선택 콤보. default_key로 기본 선택값 지정 (예: 'this_month')"""
    combo = QComboBox()
    for label, key in PERIOD_PRESETS:
        combo.addItem(label, key)
    idx = combo.findData(default_key)
    combo.setCurrentIndex(idx if idx >= 0 else len(PERIOD_PRESETS) - 1)
    return combo


_qsettings = QSettings("OnlineLedgerApp", "Ledger")


def make_checkbox_cell():
    """표의 체크박스 컬럼에 넣을 실제 QCheckBox 위젯을 만들어서 반환.
    (기존엔 QTableWidgetItem의 체크박스 장식 + 델리게이트로 클릭을 가로채는
    방식을 썼는데, Qt 내부적으로 클릭/더블클릭 이벤트가 항상 예측 가능하게
    editorEvent로 전달되지 않아 "가끔 체크가 안 된다"는 문제가 있었음.
    실제 QCheckBox 위젯을 셀에 꽂아두면 표준적인 클릭 동작이 보장되므로
    이 문제가 근본적으로 해결됨.)
    반환: (container_widget, checkbox) - container_widget을 setCellWidget()에 사용"""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignCenter)
    checkbox = QCheckBox()
    layout.addWidget(checkbox)
    container._checkbox = checkbox
    return container, checkbox


def get_row_checkbox(table: QTableWidget, row: int, col: int = 0):
    """setCellWidget으로 넣어둔 체크박스를 가져옴 (없으면 None)"""
    widget = table.cellWidget(row, col)
    if widget is None:
        return None
    return getattr(widget, "_checkbox", None)


def is_row_checked(table: QTableWidget, row: int, col: int = 0) -> bool:
    checkbox = get_row_checkbox(table, row, col)
    return bool(checkbox and checkbox.isChecked())


def set_row_checked(table: QTableWidget, row: int, checked: bool, col: int = 0):
    checkbox = get_row_checkbox(table, row, col)
    if checkbox:
        checkbox.setChecked(checked)


def enable_persistent_column_widths(table: QTableWidget, key: str):
    """표의 컬럼 폭을 사용자가 조정하면 자동으로 저장하고,
    다음에 표를 새로고침/재시작해도 그 폭을 그대로 복원함.
    - refresh() 안에서 fill_table 등으로 컬럼을 다시 채운 '직후'에 restore_column_widths(table, key)를 호출해야 함.
    - 이 함수는 __init__에서 딱 한 번만 호출해서 저장 신호를 연결해두면 됨."""

    def _save(*_args):
        widths = [table.columnWidth(i) for i in range(table.columnCount())]
        _qsettings.setValue(f"colwidths/{key}", widths)

    table.horizontalHeader().sectionResized.connect(_save)


def restore_column_widths(table: QTableWidget, key: str):
    widths = _qsettings.value(f"colwidths/{key}")
    if not widths:
        return
    for i, w in enumerate(widths):
        if i < table.columnCount():
            try:
                table.setColumnWidth(i, int(w))
            except (TypeError, ValueError):
                pass


def fit_table_height(table, max_rows=8, min_rows=3):
    """표 높이를 실제 행 수에 맞게 조절 (헤더 + 행수 기준).
    행이 적은데도 표가 화면 아래까지 길게 늘어져 보이는 것을 방지."""
    rows = max(min(table.rowCount(), max_rows), min_rows)
    row_h = table.verticalHeader().defaultSectionSize()
    header_h = table.horizontalHeader().height() or 26
    table.setMaximumHeight(header_h + row_h * rows + 8)


def tight_pair(label_text, widget):
    """라벨과 위젯을 간격 좁게(4px) 묶어서 하나의 컨테이너로 반환.
    컨테이너 자체가 가로로 늘어나지 않도록 크기정책을 고정해서, 여러 개를
    나란히 배치해도 서로 멀어지지 않고 왼쪽에 붙어있게 함."""
    container = QWidget()
    container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    h = QHBoxLayout(container)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(4)
    label = QLabel(label_text)
    label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
    h.addWidget(label)
    h.addWidget(widget)
    return container


class EditSupplierDialog(QDialog):
    """거래처(매입처) 상세정보 수정 - 이름/사업자번호/연락처/담당자/메모"""

    def __init__(self, channel, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.setWindowTitle(f"거래처 수정 - {channel['name']}")
        self.resize(420, 420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(channel["name"] or "")
        self.biznum_input = QLineEdit(channel["business_number"] or "")
        self.contact_input = QLineEdit(channel["contact"] or "")
        self.manager_input = QLineEdit(channel["manager"] or "")
        self.memo_input = QLineEdit(channel["memo"] or "")
        try:
            current_rate = channel["discount_rate"] or 0
        except (IndexError, KeyError):
            current_rate = 0
        self.discount_input = QLineEdit(str(current_rate) if current_rate else "")
        self.discount_input.setPlaceholderText("예: 3  (공급가액에서 3% 깎아줄 때)")
        try:
            self.address_input = QLineEdit(channel["address"] or "")
            self.btype_input = QLineEdit(channel["business_type_ch"] or "")
            self.bitem_input = QLineEdit(channel["business_item_ch"] or "")
        except (IndexError, KeyError):
            self.address_input = QLineEdit("")
            self.btype_input = QLineEdit("")
            self.bitem_input = QLineEdit("")
        try:
            self.ceo_input = QLineEdit(channel["ceo"] or "")
        except (IndexError, KeyError):
            self.ceo_input = QLineEdit("")
        def _fmt_b(e):
            t="".join(x for x in e.text() if x.isdigit())
            if len(t)>3: t=t[:3]+"-"+t[3:]
            if len(t)>6: t=t[:6]+"-"+t[6:]
            e.blockSignals(True); e.setText(t[:12]); e.blockSignals(False)
        def _fmt_p(e):
            t="".join(x for x in e.text() if x.isdigit())
            if len(t)<=3: pass
            elif len(t)<=7: t=t[:3]+"-"+t[3:]
            else: t=t[:3]+"-"+t[3:7]+"-"+t[7:]
            e.blockSignals(True); e.setText(t[:13]); e.blockSignals(False)
        self.biznum_input.textEdited.connect(lambda: _fmt_b(self.biznum_input))
        self.contact_input.textEdited.connect(lambda: _fmt_p(self.contact_input))
        form.addRow("업체명 *", self.name_input)
        form.addRow("사업자등록번호", self.biznum_input)
        form.addRow("대표자 이름", self.ceo_input)
        form.addRow("사업장 주소", self.address_input)
        form.addRow("업태", self.btype_input)
        form.addRow("종목", self.bitem_input)
        form.addRow("담당자", self.manager_input)
        form.addRow("연락처", self.contact_input)
        form.addRow("매입 할인율(%)", self.discount_input)
        form.addRow("메모", self.memo_input)
        hint = QLabel("💡 매입 할인율을 넣어두면, 매입 지출 등록에서 '미결제 내역'을 볼 때\n"
                       "   할인 적용된 실제 결제금액을 함께 계산해서 보여줍니다.")
        hint.setStyleSheet("color: #666;")
        hint.setWordWrap(True)
        layout.addLayout(form)
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "알림", "업체명을 입력해주세요.")
            return
        try:
            db.update_channel_details(
                self.channel["id"], name, self.biznum_input.text().strip(),
                self.contact_input.text().strip(), self.manager_input.text().strip(),
                self.memo_input.text().strip(),
            )
        except Exception:
            QMessageBox.warning(self, "알림", f"'{name}'은(는) 이미 사용 중인 이름입니다.")
            return
        try:
            rate_text = self.discount_input.text().strip()
            db.set_supplier_discount_rate(self.channel["id"], float(rate_text) if rate_text else 0.0)
        except ValueError:
            QMessageBox.warning(self, "알림", "매입 할인율은 숫자로 입력해주세요. (예: 3 또는 3.5)")
            return
        try:
            import database as _db
            _db.update_channel_extra(
                self.channel["id"],
                address=self.address_input.text().strip(),
                business_type=self.btype_input.text().strip(),
                business_item=self.bitem_input.text().strip(),
                ceo=self.ceo_input.text().strip())
            pass
        except Exception:
            pass
        notify_data_changed()
        self.accept()


class NewChannelDialog(QDialog):
    """새 업체/채널 등록: 1단계에서 유형(온라인채널/일반업체) 선택 -> 2단계에서 상세정보 입력"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("새 업체/채널 등록")
        self.resize(420, 320)
        self.result_channel_id = None

        outer = QVBoxLayout(self)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        # ---------- 1단계: 유형 선택 ----------
        page_type = QWidget()
        type_layout = QVBoxLayout(page_type)
        type_layout.addWidget(QLabel("등록할 유형을 선택하세요"))

        online_btn = QPushButton("🛒 온라인 판매채널\n(스마트스토어, 11번가, 쿠팡, ESM 등)")
        online_btn.setMinimumHeight(60)
        online_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        type_layout.addWidget(online_btn)

        offline_btn = QPushButton("🏢 거래처 등록\n(도매처, 매입처, 협력업체 등)")
        offline_btn.setMinimumHeight(60)
        offline_btn.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        type_layout.addWidget(offline_btn)
        type_layout.addStretch()

        # ---------- 2단계 (온라인채널): 간단한 정보만 ----------
        page_online = QWidget()
        form_online = QFormLayout(page_online)
        self.online_name = QLineEdit()
        form_online.addRow("채널명 *", self.online_name)
        self.online_platform = QComboBox()
        self.online_platform.setEditable(True)
        self.online_platform.addItems(["오픈마켓", "종합몰", "자사몰(이커머스)", "소셜커머스",
                                        "라이브커머스", "해외몰", "기타"])
        self.online_platform.setCurrentIndex(0)
        form_online.addRow("판매 형태", self.online_platform)
        self.online_url = QLineEdit()
        self.online_url.setPlaceholderText("예: https://sell.smartstore.naver.com")
        form_online.addRow("셀러센터 주소", self.online_url)
        self.online_settle_cycle = QComboBox()
        self.online_settle_cycle.setEditable(True)
        self.online_settle_cycle.addItems(["구매확정 후 정산", "주 1회", "월 2회", "월 1회", "기타"])
        self.online_settle_cycle.setCurrentIndex(0)
        form_online.addRow("정산 주기", self.online_settle_cycle)
        self.online_contact = QLineEdit()
        form_online.addRow("담당자 연락처", self.online_contact)
        self.online_memo = QLineEdit()
        form_online.addRow("메모", self.online_memo)
        online_btns = QHBoxLayout()
        back1 = QPushButton("← 이전")
        back1.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        save1 = QPushButton("✅ 등록")
        save1.clicked.connect(self.save_online)
        online_btns.addWidget(back1)
        online_btns.addWidget(save1)
        online_btns_widget = QWidget()
        online_btns_widget.setLayout(online_btns)
        form_online.addRow(online_btns_widget)

        # ---------- 2단계 (일반업체): 상세정보 ----------
        page_offline = QWidget()
        form_offline = QFormLayout(page_offline)
        self.offline_name = QLineEdit()
        self.offline_biznum = QLineEdit()
        self.offline_biznum.setPlaceholderText("예: 503-81-66757")
        self.offline_contact = QLineEdit()
        self.offline_contact.setPlaceholderText("예: 055-1234-5678")
        self.offline_manager = QLineEdit()
        self.offline_address = QLineEdit()
        self.offline_address.setPlaceholderText("예: 경상남도 김해시 생림면 생림대로 519-126")
        self.offline_address.setMinimumWidth(300)
        self.offline_business_type = QLineEdit()
        self.offline_business_type.setPlaceholderText("예: 도소매")
        self.offline_business_item = QLineEdit()
        self.offline_business_item.setPlaceholderText("예: 포장자재, 식품용기")
        self.offline_memo = QLineEdit()
        form_offline.addRow("업체명 *", self.offline_name)
        self.offline_ceo = QLineEdit()
        form_offline.addRow("대표자 이름", self.offline_ceo)
        self.offline_biznum.textEdited.connect(lambda: _fmt_biznum(self.offline_biznum))
        form_offline.addRow("사업자등록번호", self.offline_biznum)
        self.offline_contact.textEdited.connect(lambda: _fmt_phone(self.offline_contact))
        form_offline.addRow("연락처", self.offline_contact)
        self.offline_manager = QLineEdit()
        form_offline.addRow("담당자", self.offline_manager)
        form_offline.addRow("사업장 주소", self.offline_address)
        form_offline.addRow("업태", self.offline_business_type)
        form_offline.addRow("종목", self.offline_business_item)
        form_offline.addRow("메모", self.offline_memo)
        offline_btns = QHBoxLayout()
        back2 = QPushButton("← 이전")
        back2.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        save2 = QPushButton("✅ 등록")
        save2.clicked.connect(self.save_offline)
        offline_btns.addWidget(back2)
        offline_btns.addWidget(save2)
        offline_btns_widget = QWidget()
        offline_btns_widget.setLayout(offline_btns)
        form_offline.addRow(offline_btns_widget)

        self.stack.addWidget(page_type)     # index 0
        self.stack.addWidget(page_online)   # index 1
        self.stack.addWidget(page_offline)  # index 2

    def save_online(self):
        name = self.online_name.text().strip()
        if not name:
            QMessageBox.warning(self, "알림", "채널명을 입력해주세요.")
            return
        self.result_channel_id = db.add_channel_detailed(
            name, channel_type="온라인채널",
            contact=self.online_contact.text().strip(),
            memo=self.online_memo.text().strip())
        if self.result_channel_id:
            try:
                db.update_channel_platform_info(
                    self.result_channel_id,
                    self.online_platform.currentText().strip(),
                    self.online_url.text().strip(),
                    self.online_settle_cycle.currentText().strip())
            except Exception:
                pass
        if self.result_channel_id is None:
            QMessageBox.warning(self, "알림", f"'{name}'은(는) 이미 등록된 채널명입니다.")
            return
        notify_data_changed()
        self.accept()

    def save_offline(self):
        name = self.offline_name.text().strip()
        if not name:
            QMessageBox.warning(self, "알림", "업체명을 입력해주세요.")
            return
        self.result_channel_id = db.add_channel_detailed(
            name, channel_type="일반업체",
            business_number=self.offline_biznum.text().strip(),
            contact=self.offline_contact.text().strip(),
            manager=self.offline_ceo.text().strip() if hasattr(self,'offline_ceo') else "",
            memo=self.offline_memo.text().strip(),
        )
        if self.result_channel_id:
            # 주소/업태/종목은 별도 컬럼에 저장
            try:
                db.update_channel_extra(
                    self.result_channel_id,
                    address=self.offline_address.text().strip(),
                    business_type=self.offline_business_type.text().strip(),
                    business_item=self.offline_business_item.text().strip())
            except Exception:
                pass
        if self.result_channel_id is None:
            QMessageBox.warning(self, "알림", f"'{name}'은(는) 이미 등록된 업체명입니다.")
            return
        notify_data_changed()
        self.accept()


class ChannelPickerDialog(QDialog):
    """등록된 모든 채널(온라인 판매채널+일반거래처)에서 선택 - 주문관리 수동입력용"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("판매채널/거래처 선택")
        self.resize(600, 450)
        self.selected_channel = None

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("채널명/거래처명 검색...")
        self.search_input.textChanged.connect(self.refresh)
        layout.addWidget(self.search_input)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(lambda r, c: self.confirm_selection())
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        select_btn = QPushButton("✅ 선택")
        select_btn.clicked.connect(self.confirm_selection)
        btn_row.addWidget(select_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._channels = []
        self.refresh()

    def refresh(self):
        keyword = self.search_input.text().strip().lower()
        all_channels = db.get_channels()
        if keyword:
            all_channels = [c for c in all_channels if keyword in c["name"].lower()]
        self._channels = all_channels
        headers = ["채널/거래처명", "유형"]
        rows = [(c["name"], c["channel_type"] or "온라인채널") for c in all_channels]
        fill_table(self.table, headers, rows)

    def confirm_selection(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._channels):
            QMessageBox.warning(self, "알림", "채널/거래처를 선택해주세요.")
            return
        self.selected_channel = self._channels[row]
        self.accept()


class SupplierPickerDialog(QDialog):
    """등록된 거래처(매입처) 목록에서 선택 (입고관리에서 사용)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("거래처 선택")
        self.resize(600, 450)
        self.selected_supplier = None

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("거래처명 검색...")
        self.search_input.textChanged.connect(self.refresh)
        layout.addWidget(self.search_input)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(lambda r, c: self.confirm_selection())
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        select_btn = QPushButton("✅ 선택")
        select_btn.clicked.connect(self.confirm_selection)
        btn_row.addWidget(select_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._suppliers = []
        self.refresh()

    def refresh(self):
        keyword = self.search_input.text().strip()
        all_suppliers = db.get_suppliers()
        if keyword:
            all_suppliers = [s for s in all_suppliers if keyword.lower() in s["name"].lower()]
        self._suppliers = all_suppliers
        headers = ["거래처명", "사업자등록번호", "연락처", "담당자"]
        rows = [(s["name"], s["business_number"] or "", s["contact"] or "", s["manager"] or "")
                for s in all_suppliers]
        fill_table(self.table, headers, rows)

    def confirm_selection(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._suppliers):
            QMessageBox.warning(self, "알림", "거래처를 선택해주세요.")
            return
        self.selected_supplier = self._suppliers[row]
        self.accept()


KOREAN_BANKS = [
    "KB국민은행", "신한은행", "우리은행", "하나은행", "IBK기업은행",
    "NH농협은행", "SC제일은행", "한국씨티은행", "KDB산업은행", "수협은행",
    "카카오뱅크", "케이뱅크", "토스뱅크",
    "부산은행", "대구은행(iM뱅크)", "광주은행", "전북은행", "경남은행", "제주은행",
    "새마을금고", "신협", "우체국", "저축은행",
]


class EditBankAccountDialog(QDialog):
    """통장 등록/수정"""

    def __init__(self, account=None, parent=None):
        super().__init__(parent)
        self.account = account
        self.setWindowTitle("통장 수정" if account else "새 통장 등록")
        self.resize(360, 260)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(account["name"] if account else "")
        self.bank_name_input = QComboBox()
        self.bank_name_input.setEditable(True)  # 목록에 없는 은행/금고도 직접 입력 가능
        self.bank_name_input.addItems(KOREAN_BANKS)
        if account and account["bank_name"]:
            idx = self.bank_name_input.findText(account["bank_name"])
            if idx >= 0:
                self.bank_name_input.setCurrentIndex(idx)
            else:
                self.bank_name_input.setCurrentText(account["bank_name"])
        else:
            self.bank_name_input.setCurrentIndex(-1)
            self.bank_name_input.setCurrentText("")
        self.account_number_input = QLineEdit(account["account_number"] if account else "")
        self.balance_input = QLineEdit(str(account["balance"]) if account else "0")
        self.memo_input = QLineEdit(account["memo"] if account else "")
        form.addRow("통장 별칭 *", self.name_input)
        form.addRow("은행명", self.bank_name_input)
        form.addRow("계좌번호", self.account_number_input)
        form.addRow("현재 잔액", self.balance_input)
        form.addRow("메모", self.memo_input)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "알림", "통장 별칭을 입력해주세요.")
            return
        bank_name = self.bank_name_input.currentText().strip()
        balance_text = self.balance_input.text().strip().replace(",", "")
        balance = int(balance_text) if balance_text.lstrip("-").isdigit() else 0
        if self.account:
            old_balance = self.account["balance"] or 0
            # 잔액을 직접 바꾸면 입출금 내역과 어긋날 수 있으므로 한 번 더 확인
            if balance != old_balance and old_balance != 0:
                diff = balance - old_balance
                reply = QMessageBox.warning(
                    self, "⚠️ 잔액 수정 확인",
                    f"통장 잔액을 직접 바꾸려고 합니다.\n\n"
                    f"    현재 잔액 : {fmt_won(old_balance)}\n"
                    f"    변경 잔액 : {fmt_won(balance)}   ({'+' if diff >= 0 else ''}{diff:,}원)\n\n"
                    "잔액은 매입지출·경비지출·정산입금이 등록될 때마다 자동으로 계산됩니다.\n"
                    "여기서 직접 고치면 실제 입출금 내역과 잔액이 서로 안 맞게 될 수 있어요.\n"
                    "(통장을 처음 등록할 때의 시작 잔액을 바로잡는 경우가 아니라면 권장하지 않습니다)\n\n"
                    "그래도 변경하시겠습니까?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
            db.update_bank_account(self.account["id"], name, bank_name,
                                    self.account_number_input.text().strip(), balance,
                                    self.memo_input.text().strip())
        else:
            db.add_bank_account(name, bank_name,
                                 self.account_number_input.text().strip(), balance,
                                 self.memo_input.text().strip())
        notify_data_changed()
        self.accept()


class BankTransactionDetailDialog(QDialog):
    """리포트 통장현황에서 통장 더블클릭시 그 통장의 입출금 내역 상세"""

    def __init__(self, bank_account, parent=None):
        super().__init__(parent)
        self.bank_account = bank_account
        label = bank_account["bank_name"] or bank_account["name"]
        self.setWindowTitle(f"입출금 내역 - {label}")
        self.resize(700, 480)

        layout = QVBoxLayout(self)
        title = QLabel(f"🏦 {label} ({bank_account['name']}) - 입출금 내역")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.summary_label = QLabel(f"현재 잔액: {fmt_won(bank_account['balance'])}")
        self.summary_label.setStyleSheet("padding: 6px; background: #f0f0f0;")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        layout.addWidget(self.table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.refresh()

    def refresh(self):
        transactions = db.get_bank_transactions(500, bank_account_id=self.bank_account["id"])
        # 은행 통장처럼 보이도록: 오래된 순으로 정렬해서 잔액을 누적 계산한 뒤,
        # 화면에는 최근 건이 위로 오도록 뒤집어서 표시
        txs = sorted(transactions, key=lambda t: (t["date"] or "", t["kind"]))
        current_balance = self.bank_account["balance"] or 0
        net = sum(t["amount"] or 0 for t in txs)
        opening = current_balance - net  # 내역 이전의 시작 잔액

        running = opening
        lines = []
        for t in txs:
            amt = t["amount"] or 0
            running += amt
            # 내역: 출금이면 어디에 쓴 돈인지(거래처/경비), 입금이면 어디서 들어온 돈인지
            if "이체" in t["kind"]:
                arrow = "→" if amt < 0 else "←"
                desc = f"통장이체 {arrow} {t['ref_name'] or '통장'}"
            elif "매입지출" in t["kind"]:
                desc = f"매입대금 - {t['ref_name'] or '거래처'}"
            elif "지출" in t["kind"]:
                desc = f"지출 ({t['category'] or '기타'})"
            else:
                desc = f"정산입금 - {t['ref_name'] or '채널'}"
            lines.append((
                t["date"],
                desc,
                fmt_won(amt) if amt > 0 else "",      # 입금
                fmt_won(-amt) if amt < 0 else "",     # 출금
                fmt_won(running),                     # 잔액
                t["memo"] or "",
            ))

        lines.reverse()  # 최근 건이 위로
        lines.append((("(시작 잔액)"), "", "", "", fmt_won(opening), ""))

        headers = ["날짜", "내역", "입금", "출금", "잔액", "메모"]
        fill_table(self.table, headers, lines)

        total_in = sum(t["amount"] for t in txs if (t["amount"] or 0) > 0)
        total_out = -sum(t["amount"] for t in txs if (t["amount"] or 0) < 0)
        self.summary_label.setText(
            f"현재 잔액: {fmt_won(current_balance)}   |   총 입금: {fmt_won(total_in)}   |   "
            f"총 출금: {fmt_won(total_out)}   |   거래 {len(txs)}건"
        )


CARD_COMPANIES = [
    "신한카드", "삼성카드", "KB국민카드", "현대카드", "롯데카드", "하나카드",
    "우리카드", "BC카드", "NH농협카드", "카카오뱅크카드", "토스뱅크카드", "기타",
]


class EditCardDialog(QDialog):
    """카드 등록/수정"""

    def __init__(self, card=None, parent=None):
        super().__init__(parent)
        self.card = card
        self.setWindowTitle("카드 수정" if card else "새 카드 등록")
        self.resize(360, 240)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(card["name"] if card else "")
        self.company_input = QComboBox()
        self.company_input.setEditable(True)
        self.company_input.addItems(CARD_COMPANIES)
        if card and card["card_company"]:
            idx = self.company_input.findText(card["card_company"])
            if idx >= 0:
                self.company_input.setCurrentIndex(idx)
            else:
                self.company_input.setCurrentText(card["card_company"])
        else:
            self.company_input.setCurrentIndex(-1)
            self.company_input.setCurrentText("")
        self.number_input = QLineEdit(card["card_number"] if card else "")
        self.number_input.setPlaceholderText("뒷 4자리만 적어두셔도 됩니다")
        self.memo_input = QLineEdit(card["memo"] if card else "")
        form.addRow("카드 별칭 *", self.name_input)
        form.addRow("카드사", self.company_input)
        form.addRow("카드번호", self.number_input)
        form.addRow("메모", self.memo_input)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "알림", "카드 별칭을 입력해주세요.")
            return
        company = self.company_input.currentText().strip()
        if self.card:
            db.update_card(self.card["id"], name, company,
                           self.number_input.text().strip(), self.memo_input.text().strip())
        else:
            db.add_card(name, company, self.number_input.text().strip(),
                        self.memo_input.text().strip())
        notify_data_changed()
        self.accept()


class CardManagementDialog(QDialog):
    """카드 목록 관리 - 더블클릭하면 수정"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("카드 관리")
        self.resize(620, 400)

        layout = QVBoxLayout(self)
        title = QLabel("💳 보유 카드 목록 (더블클릭하면 수정)")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ 새 카드 등록")
        add_btn.clicked.connect(self.add_card)
        btn_row.addWidget(add_btn)
        delete_btn = QPushButton("🗑️ 선택 삭제")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_double_clicked)
        layout.addWidget(self.table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._cards = []
        self.refresh()

    def refresh(self):
        cards = db.get_cards()
        self._cards = cards
        fill_table(self.table, ["카드 별칭", "카드사", "카드번호", "메모"],
                   [(c["name"], c["card_company"] or "", c["card_number"] or "", c["memo"] or "")
                    for c in cards])

    def add_card(self):
        if EditCardDialog(None, self).exec() == QDialog.Accepted:
            self.refresh()

    def on_double_clicked(self, row, column):
        if 0 <= row < len(self._cards):
            if EditCardDialog(self._cards[row], self).exec() == QDialog.Accepted:
                self.refresh()

    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._cards):
            QMessageBox.warning(self, "알림", "삭제할 카드를 선택해주세요.")
            return
        card = self._cards[row]
        if confirm_delete(self, f"'{card['name']}' 카드",
                          "이 카드로 기록된 지출/매입 내역의 카드 정보가 사라집니다."):
            db.delete_card(card["id"])
            notify_data_changed()
            self.refresh()


class BankAccountManagementDialog(QDialog):
    """통장 목록 관리 - 더블클릭하면 수정"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("통장 관리")
        self.resize(650, 420)

        layout = QVBoxLayout(self)
        title = QLabel("🏦 통장 목록 (더블클릭하면 수정)")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ 새 통장 등록")
        add_btn.clicked.connect(self.add_account)
        btn_row.addWidget(add_btn)
        delete_btn = QPushButton("🗑️ 선택 삭제")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_double_clicked)
        layout.addWidget(self.table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._accounts = []
        self.refresh()

    def refresh(self):
        accounts = db.get_bank_accounts()
        self._accounts = accounts
        headers = ["통장별칭", "은행명", "계좌번호", "잔액", "메모"]
        rows = [(a["name"], a["bank_name"] or "", a["account_number"] or "",
                 fmt_won(a["balance"]), a["memo"] or "") for a in accounts]
        fill_table(self.table, headers, rows)

    def add_account(self):
        dialog = EditBankAccountDialog(None, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def on_double_clicked(self, row, column):
        if row < 0 or row >= len(self._accounts):
            return
        dialog = EditBankAccountDialog(self._accounts[row], self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._accounts):
            QMessageBox.warning(self, "알림", "삭제할 통장을 선택해주세요.")
            return
        account = self._accounts[row]
        if confirm_delete(
                self, f"'{account['name']}' 통장",
                "이 통장에 연결된 정산 입금·지출 기록의 통장 정보가 사라지고, 통장현황에서도 빠집니다.",
                extra_warning=f"현재 잔액 {fmt_won(account['balance'])} 정보도 함께 없어집니다.",
                double_check=True):
            db.delete_bank_account(account["id"])
            notify_data_changed()
            self.refresh()


class SupplierManagementDialog(QDialog):
    """거래처 목록을 보여주고, 더블클릭하면 상세(수정) 화면으로 이동"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("거래처 관리")
        self.resize(700, 480)

        layout = QVBoxLayout(self)
        title = QLabel("🏢 거래처 관리")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ 거래처 추가")
        add_btn.clicked.connect(self.add_supplier)
        btn_row.addWidget(add_btn)
        edit_btn = QPushButton("✏️ 수정")
        edit_btn.clicked.connect(self.edit_selected)
        btn_row.addWidget(edit_btn)
        del_btn = QPushButton("🗑️ 삭제")
        del_btn.setStyleSheet("color: red;")
        del_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        note = QLabel("💡 더블클릭해도 수정할 수 있어요")
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_double_clicked)
        layout.addWidget(self.table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._suppliers = []
        self.refresh()

    def refresh(self):
        suppliers = db.get_suppliers()
        self._suppliers = suppliers
        headers = ["거래처명", "사업자등록번호", "연락처", "담당자", "연결된 매입건수"]
        rows = [
            (s["name"], s["business_number"] or "", s["contact"] or "", s["manager"] or "",
             f"{len(db.get_purchases(supplier_id=s['id'])):,}건")
            for s in suppliers
        ]
        fill_table(self.table, headers, rows)

    def add_supplier(self):
        # 거래처(일반업체) 등록 창 - 기존 NewChannelDialog에서 일반업체 탭으로 바로
        dialog = NewChannelDialog(self)
        dialog.stack.setCurrentIndex(2)   # 일반거래처 탭
        if dialog.exec() == QDialog.Accepted:
            notify_data_changed()
            self.refresh()

    def edit_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._suppliers):
            QMessageBox.warning(self, "알림", "수정할 거래처를 선택해주세요.")
            return
        self.on_double_clicked(row, 0)

    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._suppliers):
            QMessageBox.warning(self, "알림", "삭제할 거래처를 선택해주세요.")
            return
        sup = self._suppliers[row]
        if not confirm_delete(self, f"'{sup['name']}' 거래처",
                              "연결된 매입/주문 내역 자체는 남지만, 거래처 이름 정보는 사라집니다."):
            return
        try:
            db.delete_channel(sup["id"])
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실패:\n{e}")
            return
        notify_data_changed()
        self.refresh()

    def on_double_clicked(self, row, column):
        if row < 0 or row >= len(self._suppliers):
            return
        channel = self._suppliers[row]
        dialog = EditSupplierDialog(channel, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()


class MultiOrderDialog(QDialog):
    """수동주문 복수등록 전용 창
    왼쪽에서 상품을 고르면 오른쪽 '등록 목록'에 담기고,
    수량/단가를 확인한 뒤 [등록] 버튼으로 한 번에 저장한다."""

    def __init__(self, channel_id, order_date, buyer, status, parent=None):
        super().__init__(parent)
        self.channel_id = channel_id
        self.order_date = order_date
        self.buyer = buyer
        self.status = status
        self.saved_count = 0
        self.setWindowTitle("복수 주문 등록")
        self.resize(1000, 600)

        layout = QVBoxLayout(self)
        title = QLabel("🧾 복수 주문 등록")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        note = QLabel("① 왼쪽에서 상품을 더블클릭하거나 [→ 담기]로 목록에 추가  "
                       "② 오른쪽에서 수량·단가 확인  ③ [담기 완료]\n"
                       "→ 배송비와 거래명세표·송장요청서는 주문등록 폼에서 지정한 뒤 [주문 등록]을 누르세요")
        note.setStyleSheet("color:#666;")
        layout.addWidget(note)

        body = QHBoxLayout()

        # 왼쪽: 상품 검색/목록
        left = QVBoxLayout()
        left.addWidget(QLabel("📦 상품 목록"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("상품명/옵션 검색...")
        self.search.textChanged.connect(self.refresh_products)
        left.addWidget(self.search)
        self.prod_table = QTableWidget()
        self.prod_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.prod_table.cellDoubleClicked.connect(lambda r, c: self.add_selected())
        left.addWidget(self.prod_table)
        add_btn = QPushButton("→ 담기")
        add_btn.clicked.connect(self.add_selected)
        left.addWidget(add_btn)
        body.addLayout(left, stretch=3)

        # 오른쪽: 등록 목록
        right = QVBoxLayout()
        right.addWidget(QLabel("📝 등록할 목록 (수량·단가를 고칠 수 있어요)"))
        self.cart_table = QTableWidget()
        self.cart_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cart_table.itemChanged.connect(self._update_total)
        right.addWidget(self.cart_table)
        cart_btns = QHBoxLayout()
        del_btn = QPushButton("🗑️ 선택 삭제")
        del_btn.clicked.connect(self.remove_selected)
        cart_btns.addWidget(del_btn)
        clear_btn = QPushButton("전체 비우기")
        clear_btn.clicked.connect(self.clear_cart)
        cart_btns.addWidget(clear_btn)
        cart_btns.addStretch()
        right.addLayout(cart_btns)
        self.total_label = QLabel("합계: 0원")
        self.total_label.setStyleSheet(
            "font-size:15px; font-weight:bold; color:#1A5276;"
            "padding:6px 10px; background:#EAF2F8; border-radius:5px;")
        right.addWidget(self.total_label)
        body.addLayout(right, stretch=4)

        layout.addLayout(body)

        btn_row = QHBoxLayout()
        self.ok_btn = QPushButton("✅ 담기 완료")
        self.ok_btn.setToolTip("담은 품목을 주문등록 폼으로 가져갑니다 (배송비·서류는 폼에서 지정)")
        self.ok_btn.setStyleSheet("font-weight:bold; background:#D5F5E3; min-height:34px;")
        self.ok_btn.clicked.connect(self.do_confirm)
        btn_row.addWidget(self.ok_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._products = []
        self._cart = []
        self.refresh_products()
        self._refresh_cart()

    def refresh_products(self):
        kw = self.search.text().strip().lower()
        products = db.get_products()
        if kw:
            products = [p for p in products
                        if kw in (p["name"] or "").lower()
                        or kw in (p["option_name"] or "").lower()]
        self._products = products
        fill_table(self.prod_table, ["상품명", "옵션", "판매가", "재고"],
                   [(p["name"], p["option_name"] or "",
                     fmt_price(p["sale_price"]), f"{p['stock_qty'] or 0:,}")
                    for p in products])

    def add_selected(self):
        row = self.prod_table.currentRow()
        if row < 0 or row >= len(self._products):
            QMessageBox.warning(self, "알림", "담을 상품을 골라주세요.")
            return
        p = self._products[row]
        self._cart.append({"name": p["name"], "option_name": p["option_name"] or "",
                            "qty": 1, "price": p["sale_price"] or 0})
        self._refresh_cart()

    def remove_selected(self):
        row = self.cart_table.currentRow()
        if 0 <= row < len(self._cart):
            self._cart.pop(row)
            self._refresh_cart()

    def clear_cart(self):
        self._cart = []
        self._refresh_cart()

    def _refresh_cart(self):
        self.cart_table.blockSignals(True)
        headers = ["상품명", "옵션", "수량", "단가", "금액"]
        self.cart_table.setColumnCount(len(headers))
        self.cart_table.setHorizontalHeaderLabels(headers)
        self.cart_table.setRowCount(len(self._cart))
        for r, it in enumerate(self._cart):
            for col, val in enumerate([it["name"], it["option_name"]]):
                cell = QTableWidgetItem(str(val))
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.cart_table.setItem(r, col, cell)
            # 수량·단가는 직접 고칠 수 있게
            self.cart_table.setItem(r, 2, QTableWidgetItem(str(it["qty"])))
            self.cart_table.setItem(r, 3, QTableWidgetItem(str(it["price"])))
            amt = QTableWidgetItem(fmt_won(it["qty"] * it["price"]))
            amt.setFlags(amt.flags() & ~Qt.ItemIsEditable)
            self.cart_table.setItem(r, 4, amt)
        self.cart_table.resizeColumnsToContents()
        self.cart_table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)
        self.cart_table.blockSignals(False)
        self._update_total()

    def _update_total(self):
        # 표에서 고친 수량·단가를 반영
        for r, it in enumerate(self._cart):
            try:
                qty_item = self.cart_table.item(r, 2)
                price_item = self.cart_table.item(r, 3)
                if qty_item:
                    it["qty"] = max(1, int(str(qty_item.text()).replace(",", "") or 1))
                if price_item:
                    it["price"] = int(str(price_item.text()).replace(",", "") or 0)
            except (ValueError, AttributeError):
                pass
        total = sum(it["qty"] * it["price"] for it in self._cart)
        self.total_label.setText(f"합계: {total:,}원   ({len(self._cart)}개 품목)")

    def do_confirm(self):
        """DB에 바로 저장하지 않고, 담긴 목록만 확정해서 폼으로 넘김"""
        self._update_total()
        if not self._cart:
            QMessageBox.warning(self, "알림", "등록할 상품을 담아주세요.")
            return
        self.accept()


class MultiProductPickerDialog(QDialog):
    """여러 품목을 체크박스로 한 번에 선택 (입고관리 일괄 입고용)"""

    def __init__(self, parent=None, multi_mode=False):
        """multi_mode=True: 수동주문 등록용 - 수량/가격 입력 후 등록"""
        super().__init__(parent)
        self.multi_mode = multi_mode
        self.setWindowTitle("품목 선택 후 가격 확인" if multi_mode else "여러 품목 선택")
        self.resize(780, 540)
        self.selected_products = []

        layout = QVBoxLayout(self)
        if multi_mode:
            note = QLabel("등록할 품목을 체크하고, 수량/판매단가를 확인한 뒤 [등록] 버튼을 누르세요.")
        else:
            note = QLabel("입고할 품목을 체크한 뒤 아래 '선택 완료'를 누르세요. "
                           "수량·단가는 다음 화면에서 품목별로 입력합니다.")
        note.setStyleSheet("color: #666;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("상품명/옵션 검색...")
        self.search_input.textChanged.connect(self.refresh)
        layout.addWidget(self.search_input)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        sel_row = QHBoxLayout()
        all_btn = QPushButton("전체 선택")
        all_btn.clicked.connect(lambda: self._set_all(True))
        sel_row.addWidget(all_btn)
        none_btn = QPushButton("전체 해제")
        none_btn.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(none_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("✅ 선택 완료")
        ok_btn.clicked.connect(self.confirm)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._products = []
        self.refresh()

    def refresh(self):
        keyword = self.search_input.text().strip().lower()
        products = db.get_products()
        if keyword:
            products = [p for p in products
                        if keyword in (p["name"] or "").lower()
                        or keyword in (p["option_name"] or "").lower()]
        self._products = products

        if self.multi_mode:
            headers = ["선택", "상품명", "옵션", "수량", "판매단가", "재고"]
        else:
            headers = ["선택", "상품명(대분류)", "옵션(소분류)", "현재고", "최근 원가"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(products))
        for r, p in enumerate(products):
            container, _ = make_checkbox_cell()
            self.table.setCellWidget(r, 0, container)
            if self.multi_mode:
                qty_spin = QSpinBox(); qty_spin.setRange(1,9999); qty_spin.setValue(1); qty_spin.setFixedWidth(65)
                price_edit = QLineEdit(str(p["sale_price"] or 0)); price_edit.setFixedWidth(90)
                for col, val in enumerate([p["name"], p["option_name"] or ""], start=1):
                    item = QTableWidgetItem(str(val))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(r, col, item)
                self.table.setCellWidget(r, 3, qty_spin)
                self.table.setCellWidget(r, 4, price_edit)
                stock_item = QTableWidgetItem(f"{p['stock_qty'] or 0:,}")
                stock_item.setFlags(stock_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, 5, stock_item)
            else:
                for c, val in enumerate([p["name"], p["option_name"] or "",
                                          f"{p['stock_qty'] or 0:,}", fmt_price(p["cost_price"])], start=1):
                    item = QTableWidgetItem(str(val))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)

    def _set_all(self, checked):
        for r in range(self.table.rowCount()):
            set_row_checked(self.table, r, checked)

    def confirm(self):
        self.selected_products = []
        for r, p in enumerate(self._products):
            if not is_row_checked(self.table, r):
                continue
            if self.multi_mode:
                qty_w = self.table.cellWidget(r, 3)
                price_w = self.table.cellWidget(r, 4)
                qty = qty_w.value() if qty_w else 1
                try:
                    price = int((price_w.text() if price_w else "0").replace(",",""))
                except Exception:
                    price = p.get("sale_price") or 0
                item = dict(p)
                item["qty_override"] = qty
                item["sale_price"] = price
            else:
                item = dict(p)
            self.selected_products.append(item)
        if not self.selected_products:
            QMessageBox.warning(self, "알림", "품목을 하나 이상 선택해주세요.")
            return
        self.accept()


class BatchPurchaseDialog(QDialog):
    """여러 품목을 한 번에 입고 등록 - 거래처/입고일은 공통, 수량·단가는 품목별로 입력"""

    def __init__(self, products, supplier_id=None, purchase_date=None, parent=None):
        super().__init__(parent)
        self.products = products
        self.setWindowTitle("여러 품목 일괄 입고")
        self.resize(820, 560)

        layout = QVBoxLayout(self)
        title = QLabel(f"📦 여러 품목 일괄 입고 ({len(products)}개 품목)")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # 공통 항목: 거래처 / 입고일
        common_row = QHBoxLayout()
        self.supplier_combo = QComboBox()
        self.supplier_combo.setFixedWidth(200)
        self.supplier_combo.addItem("", None)
        for s in db.get_suppliers():
            self.supplier_combo.addItem(s["name"], s["id"])
        if supplier_id:
            idx = self.supplier_combo.findData(supplier_id)
            if idx >= 0:
                self.supplier_combo.setCurrentIndex(idx)
        common_row.addWidget(tight_pair("거래처 *:", self.supplier_combo))

        self.date_edit = make_date_edit()
        self.date_edit.setDate(purchase_date or QDate.currentDate())
        self.date_edit.setFixedWidth(160)
        common_row.addWidget(tight_pair("입고일:", self.date_edit))
        common_row.addStretch()
        layout.addLayout(common_row)

        hint = QLabel("💡 수량과 단가는 표에서 직접 입력하세요. 단가는 소수점 한 자리까지 가능하고, "
                       "합계금액은 자동으로 계산됩니다. 수량을 0으로 두면 그 품목은 등록되지 않아요.")
        hint.setStyleSheet("color: #666;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 품목별 입력 표 (수량/단가는 편집 가능)
        self.table = QTableWidget()
        headers = ["상품명(대분류)", "옵션(소분류)", "현재고", "수량", "단가", "합계금액"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(products))
        for r, p in enumerate(products):
            for c, val in enumerate([p["name"], p["option_name"] or "", f"{p['stock_qty'] or 0:,}"]):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)
            # 수량: 기본 0 (입력해야 등록됨)
            self.table.setItem(r, 3, QTableWidgetItem("0"))
            # 단가: 그 거래처+품목의 직전 입고단가가 있으면 그걸, 없으면 품목 원가
            last = db.get_last_purchase_price(supplier_id, p["id"]) if supplier_id else None
            self.table.setItem(r, 4, QTableWidgetItem(str(last if last else (p["cost_price"] or 0))))
            total_item = QTableWidgetItem("0")
            total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 5, total_item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(
            "padding: 8px; background: #EAF2F8; font-weight: bold; border-radius: 6px;")
        layout.addWidget(self.summary_label)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("➕ 일괄 입고 등록")
        save_btn.clicked.connect(self.save_all)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._update_summary()

    def _on_item_changed(self, item):
        """수량이나 단가를 고치면 그 행의 합계금액을 다시 계산"""
        if item.column() not in (3, 4):
            return
        r = item.row()
        self.table.blockSignals(True)
        qty = to_int(self.table.item(r, 3).text(), 0)
        unit = to_float(self.table.item(r, 4).text(), 0)
        total = qty * unit
        text = str(int(round(total))) if abs(total - round(total)) < 1e-9 else f"{total:.1f}"
        self.table.item(r, 5).setText(text)
        self.table.blockSignals(False)
        self._update_summary()

    def _collect_rows(self):
        """수량이 0이 아닌 행만 모아서 반환"""
        rows = []
        for r in range(self.table.rowCount()):
            qty = to_int(self.table.item(r, 3).text(), 0)
            if qty == 0:
                continue
            unit = to_float(self.table.item(r, 4).text(), 0)
            rows.append((self.products[r], qty, unit, qty * unit))
        return rows

    def _update_summary(self):
        rows = self._collect_rows()
        total_amount = sum(t for _, _, _, t in rows)
        total_qty = sum(q for _, q, _, _ in rows)
        self.summary_label.setText(
            f"등록 대상: {len(rows)}개 품목   |   총 수량: {total_qty:,}개   |   "
            f"총 합계금액: {fmt_price(total_amount)}"
        )

    def save_all(self):
        supplier_id = self.supplier_combo.currentData()
        if supplier_id is None:
            QMessageBox.warning(self, "알림", "거래처를 선택해주세요.")
            return
        rows = self._collect_rows()
        if not rows:
            QMessageBox.warning(self, "알림", "수량을 입력한 품목이 없습니다.")
            return

        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        registered = 0
        try:
            for product, qty, unit, total in rows:
                db.add_purchase(date_str, supplier_id, product["id"], qty, unit, total, 0, "")
                # 재고 증가 + 원가를 최신 매입단가로 갱신 (단일 입고와 동일한 처리)
                fresh = next((p for p in db.get_products() if p["id"] == product["id"]), None)
                if fresh:
                    db.update_product(
                        fresh["id"], fresh["sku"], fresh["name"], unit, fresh["sale_price"],
                        (fresh["stock_qty"] or 0) + qty, fresh["memo"],
                        option_name=fresh["option_name"],
                        cost_source="일괄 입고 등록",
                    )
                registered += 1
        except Exception as e:
            QMessageBox.critical(self, "오류", f"일괄 입고 중 오류가 발생했습니다:\n{e}")
            return
        finally:
            notify_data_changed()

        QMessageBox.information(self, "완료", f"{registered}개 품목을 한 번에 입고 등록했습니다.")
        self.accept()


class ProductPickerDialog(QDialog):
    """등록된 품목 목록에서 선택 (수동 주문의 상품명/판매단가 자동 채우기용).
    recent_source를 주면 최근에 쓴 품목이 목록 위쪽에 먼저 나옴
    ('order'=주문 이력 기준 / 'purchase'=입고 이력 기준)"""

    def __init__(self, parent=None, recent_source=None, sales_channel_id=None):
        super().__init__(parent)
        self.recent_source = recent_source
        self.sales_channel_id = sales_channel_id
        self.setWindowTitle("상품 선택")
        self.resize(600, 450)
        self.selected_product = None

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("상품명 검색...")
        self.search_input.textChanged.connect(self.refresh)
        layout.addWidget(self.search_input)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(lambda r, c: self.confirm_selection())
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        select_btn = QPushButton("✅ 선택")
        select_btn.clicked.connect(self.confirm_selection)
        btn_row.addWidget(select_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._products = []
        self.refresh()

    def refresh(self):
        keyword = self.search_input.text().strip().lower()
        all_products = db.get_products()
        if keyword:
            all_products = [
                p for p in all_products
                if keyword in p["name"].lower() or keyword in (p["option_name"] or "").lower()
            ]

        # 자주/많이 쓰는 품목을 위쪽으로 정렬해서 바로 고를 수 있게 함
        recent_ids = []
        if not conv_on("recent_first"):
            self.recent_source = None
        if self.recent_source == "sales":
            try:
                recent_ids = db.get_product_sales_ranking_ids(self.sales_channel_id)
            except Exception:
                recent_ids = []
        elif self.recent_source:
            try:
                recent_ids = db.get_recent_product_ids(self.recent_source)
            except Exception:
                recent_ids = []
        rank = {pid: i for i, pid in enumerate(recent_ids)}
        all_products = sorted(all_products, key=lambda p: rank.get(p["id"], 10**6))
        self._products = all_products

        headers = ["", "상품명(대분류)", "옵션(소분류)", "SKU", "판매가", "재고"]
        mark = "💰" if self.recent_source == "sales" else "🕘"
        rows = [(mark if p["id"] in rank else "", p["name"], p["option_name"], p["sku"],
                 fmt_won(p["sale_price"]), p["stock_qty"])
                for p in all_products]
        fill_table(self.table, headers, rows)
        if recent_ids:
            if self.recent_source == "sales":
                self.setWindowTitle("상품 선택  (💰 = 매출이 높은 품목부터 표시됩니다)")
            else:
                self.setWindowTitle("상품 선택  (🕘 = 최근 사용한 품목이 위에 표시됩니다)")

    def confirm_selection(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._products):
            QMessageBox.warning(self, "알림", "상품을 선택해주세요.")
            return
        self.selected_product = self._products[row]
        self.accept()


class ProductStockHistoryDialog(QDialog):
    """품목 더블클릭 메뉴에서 '입출고 내역'을 고르면 뜨는 창.
    입고(매입)/판매(주문)/재고조정을 하나의 시간순 타임라인으로 보여줌"""

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        label = f"{product['name']} {product['option_name']}".strip() if product["option_name"] else product["name"]
        self.setWindowTitle(f"입출고 내역 - {label}")
        self.resize(700, 500)

        layout = QVBoxLayout(self)
        title = QLabel(f"📦 {label} - 입출고 내역")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.summary_label = QLabel(f"현재 재고: {product['stock_qty'] or 0}개")
        self.summary_label.setStyleSheet("padding: 6px; background: #f0f0f0;")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        layout.addWidget(self.table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.refresh()

    def refresh(self):
        history = db.get_product_stock_history(self.product["id"])
        headers = ["날짜", "구분", "변동수량", "거래처/채널", "메모"]
        rows = [
            (h["date"], h["kind"], f"{'+' if h['change'] >= 0 else ''}{h['change']}개", h["related"], h["memo"])
            for h in history
        ]
        fill_table(self.table, headers, rows, sort_state=self._sort_state)


class StockAdjustDialog(QDialog):
    """품목 재고를 +/-로 조정 (실사/파손/분실 등 사유와 함께 이력 기록)"""

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle(f"재고 조정 - {product['name']}")
        self.resize(360, 260)

        layout = QVBoxLayout(self)
        info = QLabel(f"현재 재고: {product['stock_qty'] or 0}개")
        info.setStyleSheet("font-weight: bold;")
        layout.addWidget(info)

        form = QFormLayout()
        self.date_edit = make_date_edit()
        self.date_edit.setDate(QDate.currentDate())
        self.change_spin = QSpinBox()
        self.change_spin.setRange(-999999, 999999)
        self.change_spin.setValue(0)
        self.reason_combo = QComboBox()
        self.reason_combo.addItems(["재고실사조정", "파손", "분실", "반품입고", "기타"])
        self.memo_input = QLineEdit()
        self.memo_input.setFixedWidth(220)

        form.addRow("조정일", self.date_edit)
        form.addRow("조정수량 (+면 증가, -면 감소)", self.change_spin)
        form.addRow("사유", self.reason_combo)
        form.addRow("메모", self.memo_input)
        layout.addLayout(form)

        preview = QLabel("")
        preview.setStyleSheet("color: #666;")
        layout.addWidget(preview)

        def update_preview(v):
            new_stock = (product["stock_qty"] or 0) + v
            preview.setText(f"조정 후 재고: {new_stock}개")
        self.change_spin.valueChanged.connect(update_preview)
        update_preview(0)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("✅ 조정 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        change_qty = self.change_spin.value()
        if change_qty == 0:
            QMessageBox.warning(self, "알림", "조정수량이 0입니다. 증가시킬 값(+) 또는 감소시킬 값(-)을 입력해주세요.")
            return
        db.add_stock_adjustment(
            self.product["id"], self.date_edit.date().toString("yyyy-MM-dd"),
            change_qty, self.reason_combo.currentText(), self.memo_input.text().strip(),
        )
        notify_data_changed()
        self.accept()


class OptionPickerDialog(QDialog):
    """저장된 옵션 프리셋 + 기존 주문에서 실제로 쓰인 옵션명 목록에서 선택"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("옵션 선택")
        self.resize(450, 450)
        self.selected_option = None

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("옵션명 검색...")
        self.search_input.textChanged.connect(self.refresh)
        layout.addWidget(self.search_input)

        self.list_widget = QTableWidget()
        self.list_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.list_widget.cellDoubleClicked.connect(lambda r, c: self.confirm_selection())
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        select_btn = QPushButton("✅ 선택")
        select_btn.clicked.connect(self.confirm_selection)
        btn_row.addWidget(select_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._options = []
        self.refresh()

    def refresh(self):
        keyword = self.search_input.text().strip().lower()
        presets = db.get_option_presets()
        used = db.get_distinct_order_options()
        # 저장된 프리셋을 먼저, 그다음 기존 주문 이력에서 쓰인 것 (중복 제거)
        seen = set()
        merged = []
        for label in presets + used:
            key = label.strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(label)
        if keyword:
            merged = [m for m in merged if keyword in m.lower()]
        self._options = merged
        fill_table(self.list_widget, ["옵션명"], [(m,) for m in merged])

    def confirm_selection(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._options):
            QMessageBox.warning(self, "알림", "옵션을 선택해주세요.")
            return
        self.selected_option = self._options[row]
        self.accept()


class QtyPresetEditDialog(QDialog):
    """수량 드롭다운에 나오는 수량 목록을 사용자가 직접 편집하는 창"""

    def __init__(self, scope, parent=None):
        super().__init__(parent)
        self.scope = scope
        self.setWindowTitle("수량 목록 직접 설정")
        self.resize(360, 420)

        layout = QVBoxLayout(self)
        note = QLabel("자주 쓰는 수량을 등록해두면 드롭다운에서 바로 고를 수 있어요.\n"
                       "(숫자만 입력, 위에서부터 나오는 순서대로 표시됩니다)")
        note.setStyleSheet("color: #666;")
        note.setWordWrap(True)
        layout.addWidget(note)

        add_row = QHBoxLayout()
        self.qty_input = QLineEdit()
        self.qty_input.setPlaceholderText("예: 144")
        self.qty_input.returnPressed.connect(self.add_qty)
        add_row.addWidget(self.qty_input)
        add_btn = QPushButton("➕ 추가")
        add_btn.clicked.connect(self.add_qty)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        up_btn = QPushButton("▲ 위로")
        up_btn.clicked.connect(lambda: self.move_item(-1))
        btn_row.addWidget(up_btn)
        down_btn = QPushButton("▼ 아래로")
        down_btn.clicked.connect(lambda: self.move_item(1))
        btn_row.addWidget(down_btn)
        del_btn = QPushButton("🗑️ 삭제")
        del_btn.setStyleSheet("color: red;")
        del_btn.clicked.connect(self.delete_item)
        btn_row.addWidget(del_btn)
        layout.addLayout(btn_row)

        save_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        save_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        save_row.addWidget(cancel_btn)
        layout.addLayout(save_row)

        for q in db.get_qty_presets(scope):
            self.list_widget.addItem(f"{q:,}")

    def add_qty(self):
        text = self.qty_input.text().strip().replace(",", "")
        if not text.isdigit() or int(text) <= 0:
            QMessageBox.warning(self, "알림", "1 이상의 숫자를 입력해주세요.")
            return
        value = f"{int(text):,}"
        existing = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        if value in existing:
            QMessageBox.warning(self, "알림", "이미 목록에 있는 수량입니다.")
            return
        self.list_widget.addItem(value)
        self.qty_input.clear()

    def move_item(self, direction):
        row = self.list_widget.currentRow()
        new_row = row + direction
        if row < 0 or new_row < 0 or new_row >= self.list_widget.count():
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(new_row, item)
        self.list_widget.setCurrentRow(new_row)

    def delete_item(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row)

    def save(self):
        values = []
        for i in range(self.list_widget.count()):
            t = self.list_widget.item(i).text().replace(",", "")
            if t.isdigit():
                values.append(int(t))
        if not values:
            QMessageBox.warning(self, "알림", "수량을 하나 이상 등록해주세요.")
            return
        db.set_qty_presets(self.scope, values)
        self.accept()


class QuickAddOptionDialog(QDialog):
    """새 옵션명을 프리셋으로 등록 (다음에 옵션 선택에서 바로 고를 수 있게 저장됨)"""

    def __init__(self, parent=None, default_label=""):
        super().__init__(parent)
        self.setWindowTitle("옵션 등록")
        self.resize(360, 140)
        self.new_option = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.label_input = QLineEdit(default_label)
        form.addRow("옵션명 *", self.label_input)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("✅ 등록")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        label = self.label_input.text().strip()
        if not label:
            QMessageBox.warning(self, "알림", "옵션명을 입력해주세요.")
            return
        db.add_option_preset(label)
        self.new_option = label
        self.accept()


class QuickAddProductDialog(QDialog):
    """수동 주문 입력 중 상품이 목록에 없을 때 바로 등록하는 간단한 다이얼로그"""

    def __init__(self, parent=None, default_name=""):
        super().__init__(parent)
        self.setWindowTitle("새 상품 등록")
        self.resize(380, 250)
        self.new_product_id = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(default_name)
        self.option_input = QLineEdit()
        self.sku_input = QLineEdit()
        self.cost_input = QLineEdit("0")
        self.price_input = QLineEdit("0")
        self.stock_input = QLineEdit("0")
        form.addRow("상품명(대분류) *", self.name_input)
        form.addRow("옵션(소분류)", self.option_input)
        form.addRow("SKU/코드", self.sku_input)
        self.cost_input.setPlaceholderText("소수점 한 자리까지 가능 (예: 314.5)")
        form.addRow("원가", self.cost_input)
        form.addRow("판매가", self.price_input)
        form.addRow("재고수량", self.stock_input)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("✅ 등록")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "알림", "상품명을 입력해주세요.")
            return

        def to_int(s):
            s = s.strip().replace(",", "")
            return int(s) if s.isdigit() else 0

        db.add_product(
            self.sku_input.text().strip(), name,
            to_float(self.cost_input.text()), to_int(self.price_input.text()),
            to_int(self.stock_input.text()), option_name=self.option_input.text().strip(),
        )
        product = next((p for p in db.get_products() if p["name"] == name), None)
        self.new_product_id = product["id"] if product else None
        self.new_product = product
        self.accept()


class ShipmentRequestDialog(QDialog):
    """송장요청서 작성 - 받는분 정보 입력, 과거 이력 불러오기, 수량 분할"""

    def __init__(self, default_product="", default_qty=1, default_receiver="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("송장요청서 작성")
        self.resize(880, 560)
        self.rows = []

        layout = QVBoxLayout(self)
        title = QLabel("🚚 송장요청서 작성")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # 과거 이력에서 고르기
        hist_row = QHBoxLayout()
        self.history_combo = QComboBox()
        self.history_combo.setMinimumWidth(420)
        self.history_combo.addItem("(과거 이력에서 고르기)", None)
        try:
            for h in db.get_shipment_history():
                label = f"{h['receiver']} · {h['phone']} · {(h['address'] or '')[:24]}"
                self.history_combo.addItem(label, dict(h))
        except Exception:
            pass
        self.history_combo.currentIndexChanged.connect(self._load_history)
        hist_row.addWidget(tight_pair("📜 과거 발송:", self.history_combo))
        hist_row.addStretch()
        layout.addLayout(hist_row)

        # 입력 폼
        form = QGridLayout()
        form.setVerticalSpacing(8)
        form.setHorizontalSpacing(10)
        self.receiver = QLineEdit(default_receiver)
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("010-0000-0000")
        self.phone.textEdited.connect(self._auto_hyphen)
        self.phone2 = QLineEdit()
        self.address = QLineEdit()
        self.address.setMinimumWidth(420)
        self.product = QLineEdit(default_product)
        self.product.setMinimumWidth(260)
        self.qty = QSpinBox()
        self.qty.setRange(1, 999999)
        self.qty.setValue(int(default_qty or 1))
        self.message = QLineEdit()
        self.message.setPlaceholderText("예: 부재시 경비실")

        fields = [("받는분 성명 *", self.receiver, 0, 0), ("전화번호 *", self.phone, 0, 2),
                   ("기타 연락처", self.phone2, 1, 0), ("품목명", self.product, 1, 2),
                   ("주소 *", self.address, 2, 0), ("내품수량", self.qty, 3, 0),
                   ("배송메세지", self.message, 3, 2)]
        for label, widget, r, col in fields:
            form.addWidget(QLabel(label), r, col)
            if label == "주소 *":
                form.addWidget(widget, r, col + 1, 1, 3)
            else:
                form.addWidget(widget, r, col + 1)
        form.setColumnStretch(4, 1)
        layout.addLayout(form)

        # 수량 분할
        split_box = QGroupBox("📦 수량 분할 (한 번에 다 못 보낼 때 여러 박스로 나눠서)")
        split_layout = QHBoxLayout(split_box)
        self.split_cb = QCheckBox("나눠서 보내기")
        self.split_cb.stateChanged.connect(self._toggle_split)
        split_layout.addWidget(self.split_cb)
        self.split_per = QSpinBox()
        self.split_per.setRange(1, 999999)
        self.split_per.setValue(100)
        self.split_per.setEnabled(False)
        self.split_per.valueChanged.connect(self._update_split_hint)
        self.qty.valueChanged.connect(self._update_split_hint)
        split_layout.addWidget(tight_pair("박스당 수량:", self.split_per))
        self.split_hint = QLabel("")
        self.split_hint.setStyleSheet("color: #1A5276;")
        split_layout.addWidget(self.split_hint)
        split_layout.addStretch()
        layout.addWidget(split_box)

        # 목록에 담기
        add_row = QHBoxLayout()
        add_btn = QPushButton("➕ 목록에 추가")
        add_btn.clicked.connect(self.add_to_list)
        add_row.addWidget(add_btn)
        del_btn = QPushButton("🗑️ 선택 삭제")
        del_btn.clicked.connect(self.delete_selected)
        add_row.addWidget(del_btn)
        add_row.addStretch()
        layout.addLayout(add_row)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("💾 송장요청서 저장")
        ok_btn.clicked.connect(self._confirm)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._refresh_table()

    def _auto_hyphen(self, text):
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits and len(digits) == len(text.replace("-", "").replace(" ", "")):
            formatted = format_phone(digits)
            if formatted != text:
                self.phone.blockSignals(True)
                self.phone.setText(formatted)
                self.phone.blockSignals(False)

    def _load_history(self):
        h = self.history_combo.currentData()
        if not h:
            return
        self.receiver.setText(h.get("receiver", "") or "")
        self.phone.setText(h.get("phone", "") or "")
        self.address.setText(h.get("address", "") or "")
        if h.get("product"):
            self.product.setText(h["product"])
        if h.get("message"):
            self.message.setText(h["message"])

    def _toggle_split(self):
        self.split_per.setEnabled(self.split_cb.isChecked())
        self._update_split_hint()

    def _update_split_hint(self):
        if not self.split_cb.isChecked():
            self.split_hint.setText("")
            return
        total, per = self.qty.value(), max(self.split_per.value(), 1)
        boxes = (total + per - 1) // per
        last = total - per * (boxes - 1)
        self.split_hint.setText(f"→ {boxes}박스 (마지막 박스 {last}개)")

    def add_to_list(self):
        if not self.receiver.text().strip():
            QMessageBox.warning(self, "알림", "받는분 성명을 입력해주세요.")
            return
        if not self.address.text().strip():
            QMessageBox.warning(self, "알림", "주소를 입력해주세요.")
            return

        base = {
            "receiver": self.receiver.text().strip(), "phone": self.phone.text().strip(),
            "phone2": self.phone2.text().strip(), "address": self.address.text().strip(),
            "product": self.product.text().strip(), "inner_name": self.product.text().strip(),
            "message": self.message.text().strip(), "fare_type": "신용",
        }
        total = self.qty.value()
        if self.split_cb.isChecked():
            per = max(self.split_per.value(), 1)
            boxes = (total + per - 1) // per
            for i in range(boxes):
                qty = min(per, total - per * i)
                row = dict(base)
                row["qty"] = qty
                row["box_qty"] = 1
                row["message"] = (base["message"] + f" ({i + 1}/{boxes})").strip()
                self.rows.append(row)
        else:
            row = dict(base)
            row["qty"] = total
            row["box_qty"] = 1
            self.rows.append(row)

        self._refresh_table()
        self.receiver.clear(); self.phone.clear(); self.phone2.clear()
        self.address.clear(); self.message.clear()

    def delete_selected(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.rows):
            self.rows.pop(r)
            self._refresh_table()

    def _refresh_table(self):
        fill_table(self.table, ["받는분", "전화번호", "주소", "품목명", "수량", "박스", "메세지"],
                   [(x["receiver"], x["phone"], x["address"], x["product"],
                     f"{x['qty']:,}", x["box_qty"], x.get("message", "")) for x in self.rows])

    def _confirm(self):
        if not self.rows:
            self.add_to_list()
        if not self.rows:
            return
        self.accept()


class ReturnDialog(QDialog):
    """반품 처리 - 전체 반품 / 일부 수량만 반품 선택"""

    def __init__(self, order, parent=None):
        super().__init__(parent)
        self.order = order
        self.total_qty = int(order["qty"] or 0)
        self.return_qty = self.total_qty
        self.reason = ""
        self.setWindowTitle("반품 처리")
        self.resize(430, 330)

        layout = QVBoxLayout(self)
        title = QLabel("↩️ 반품 처리")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        label = f"{order['product_name']} {order['option_name'] or ''}".strip()
        unit = int(order["sale_price"] or 0)
        info = QLabel(
            f"구매자 : {order['buyer_name'] or '-'}\n"
            f"주문일 : {order['order_date']}\n"
            f"상품   : {label}\n"
            f"수량   : {self.total_qty}개   |   단가 {fmt_price(unit)}\n"
            f"금액   : {fmt_price(order['total_amount'])}")
        info.setStyleSheet("padding: 10px; background: #EAF2F8; border-radius: 6px;")
        layout.addWidget(info)

        self.all_radio = QCheckBox("전체 반품 (주문 전부를 반품 처리)")
        self.all_radio.setChecked(True)
        self.all_radio.stateChanged.connect(self._toggle)
        layout.addWidget(self.all_radio)

        qty_row = QHBoxLayout()
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, max(self.total_qty, 1))
        self.qty_spin.setValue(self.total_qty)
        self.qty_spin.setEnabled(False)
        self.qty_spin.valueChanged.connect(self._update_hint)
        qty_row.addWidget(tight_pair("반품 수량:", self.qty_spin))
        qty_row.addWidget(QLabel(f"/ {self.total_qty}개"))
        qty_row.addStretch()
        layout.addLayout(qty_row)

        self.hint = QLabel("")
        self.hint.setStyleSheet("color: #1A5276; padding: 4px;")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self.reason_combo = QComboBox()
        self.reason_combo.setEditable(True)
        self.reason_combo.addItems(["단순 변심", "상품 불량", "오배송", "파손", "기타"])
        self.reason_combo.setCurrentIndex(0)
        layout.addWidget(tight_pair("반품 사유:", self.reason_combo))

        layout.addStretch()
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("↩️ 반품 처리")
        ok_btn.clicked.connect(self._confirm)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        self._update_hint()

    def _toggle(self):
        is_all = self.all_radio.isChecked()
        self.qty_spin.setEnabled(not is_all)
        if is_all:
            self.qty_spin.setValue(self.total_qty)
        self._update_hint()

    def _update_hint(self):
        qty = self.total_qty if self.all_radio.isChecked() else self.qty_spin.value()
        unit = int(self.order["sale_price"] or 0)
        left = self.total_qty - qty
        if left > 0:
            self.hint.setText(
                f"· 반품 {qty}개 ({fmt_price(unit * qty)})  →  재고로 되돌아옵니다\n"
                f"· 남은 주문 {left}개 ({fmt_price(unit * left)})는 매출로 유지됩니다")
        else:
            self.hint.setText("· 주문 전체가 반품되어 매출에서 빠지고, 재고가 모두 되돌아옵니다")

    def _confirm(self):
        self.return_qty = self.total_qty if self.all_radio.isChecked() else self.qty_spin.value()
        self.reason = self.reason_combo.currentText().strip()
        self.accept()


class OrderDetailDialog(QDialog):
    """주문 1건의 상세 정보 (주문일 / 상품·옵션 / 구매자 / 주소 / 연락처 등)"""

    def __init__(self, order, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"주문 상세 - {order['order_no'] or ''}")
        self.resize(560, 560)

        self.order = order
        layout = QVBoxLayout(self)
        top_row = QHBoxLayout()
        title = QLabel("🔍 주문 상세 정보")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        top_row.addWidget(title)
        top_row.addStretch()
        history_btn = QPushButton("📜 과거 주문내역")
        history_btn.setToolTip("최근 1년간 같은 구매자, 또는 구매자가 달라도 수취인+주소나 "
                                "전화번호가 같은 주문을 찾아 보여줍니다\n"
                                "(구매담당자가 바뀌어도 같은 거래처의 과거 구매를 확인할 수 있어요)")
        history_btn.clicked.connect(self.show_past_orders)
        top_row.addWidget(history_btn)
        layout.addLayout(top_row)

        def val(key):
            try:
                v = order[key]
            except (IndexError, KeyError):
                return ""
            return "" if v is None else str(v)

        product_label = val("product_name")
        if val("option_name"):
            product_label += f"\n   └ {val('option_name')}"

        sections = [
            ("주문 정보", [
                ("주문일", val("order_date")),
                ("주문번호", val("order_no")),
                ("판매채널", val("channel_name")),
                ("주문상태", val("status")),
                ("정산상태", "✅ 정산완료" if order["is_settled"] else "미정산"),
            ]),
            ("상품 정보", [
                ("상품명 / 옵션", product_label),
                ("수량", f"{order['qty'] or 0:,}개"),
                ("판매단가", fmt_price(order["sale_price"])),
                ("매출금액", fmt_price(order["total_amount"])),
                ("수수료", fmt_won(order["fee_amount"])),
                ("배송비", fmt_won(order["shipping_fee"])),
                ("정산예정금액", fmt_won(order["settlement_amount"])),
            ]),
            ("받는 분 정보", [
                ("구매자", val("buyer_name")),
                ("수취인", val("receiver_name")),
                ("연락처", val("phone")),
                ("주소", val("address")),
                ("메모", val("memo")),
            ]),
        ]

        for section_title, fields in sections:
            box = QGroupBox(section_title)
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for label_text, value in fields:
                value_label = QLabel(value if value else "-")
                value_label.setWordWrap(True)
                value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                if not value:
                    value_label.setStyleSheet("color: #AAA;")
                form.addRow(f"{label_text} :", value_label)
            layout.addWidget(box)

        layout.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def show_past_orders(self):
        PastOrderHistoryDialog(self.order, self).exec()


class PastOrderHistoryDialog(QDialog):
    """같은 구매자/수취인+주소/전화번호의 과거 주문 이력 (기간 선택 가능)"""

    def __init__(self, order, parent=None):
        super().__init__(parent)
        self.order = order

        def g(key):
            try:
                return order[key] or ""
            except (IndexError, KeyError):
                return ""
        self._buyer = g("buyer_name")
        self._receiver = g("receiver_name")
        self._address = g("address")
        self._phone = g("phone")
        who = self._buyer or self._receiver or "이 주문"

        self.setWindowTitle(f"과거 주문내역 - {who}")
        self.resize(980, 560)

        layout = QVBoxLayout(self)
        title = QLabel(f"📜 {who} 관련 주문내역")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        criteria = []
        if self._buyer:
            criteria.append(f"구매자 '{self._buyer}'")
        if self._receiver and self._address:
            criteria.append(f"수취인 '{self._receiver}' + 같은 주소")
        if self._phone:
            criteria.append(f"전화 '{self._phone}'")
        note = QLabel("💡 " + (" 또는 ".join(criteria) if criteria else "기준 정보(구매자/수취인/전화)가 없어 이 주문만 표시합니다")
                       + (" 가 일치하는 주문을 모았습니다. (지금 보고 있는 주문은 ▶ 로 표시)" if criteria else ""))
        note.setStyleSheet("color: #666;")
        note.setWordWrap(True)
        layout.addWidget(note)

        period_row = QHBoxLayout()
        self.period_combo = QComboBox()
        self.period_combo.addItem("최근 1년", 12)
        self.period_combo.addItem("최근 3년", 36)
        self.period_combo.addItem("최근 5년", 60)
        self.period_combo.setCurrentIndex(0)   # 기본 1년
        self.period_combo.currentIndexChanged.connect(self.refresh)
        period_row.addWidget(tight_pair("조회 기간:", self.period_combo))
        period_row.addStretch()
        layout.addLayout(period_row)

        self.summary = QLabel("")
        self.summary.setStyleSheet(
            "padding: 8px; background: #EAF2F8; font-weight: bold; border-radius: 6px;")
        layout.addWidget(self.summary)

        self._sort_state = {"column": None, "ascending": False}
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.refresh()
        enable_header_click_sort(self.table, self._sort_state, self.refresh)

    def refresh(self):
        months = self.period_combo.currentData() or 12
        rows = db.get_related_order_history(
            buyer_name=self._buyer or None,
            receiver_name=self._receiver or None,
            address=self._address or None,
            phone=self._phone or None,
            months=months,
            include_order_id=self.order["id"],
        )
        total_amount = sum(r["total_amount"] or 0 for r in rows)
        total_qty = sum(r["qty"] or 0 for r in rows)
        self.summary.setText(
            f"주문 {len(rows)}건   |   총 수량 {total_qty:,}개   |   총 매출 {fmt_won(total_amount)}")

        headers = ["", "주문일", "채널", "상품명", "옵션", "수량", "판매단가", "매출금액", "구매자", "수취인"]
        table_rows = []
        for r in rows:
            def rg(key):
                try:
                    return r[key] or ""
                except (IndexError, KeyError):
                    return ""
            table_rows.append((
                "▶" if r["id"] == self.order["id"] else "",
                r["order_date"], r["channel_name"] or "", r["product_name"], r["option_name"] or "",
                f"{r['qty'] or 0:,}", fmt_price(r["sale_price"]), fmt_price(r["total_amount"]),
                rg("buyer_name"), rg("receiver_name"),
            ))
        fill_table(self.table, headers, table_rows, persist_key="past_order_history")


class OrderEditDialog(QDialog):
    """주문 1건 수정 (파일업로드/수동입력 구분 없이 모든 주문에 사용)"""

    def __init__(self, order, parent=None):
        super().__init__(parent)
        self.order = order
        self.setWindowTitle(f"주문 수정 - {order['order_no']}")
        self.resize(420, 480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.channel_combo = QComboBox()
        for ch in db.get_channels():
            self.channel_combo.addItem(ch["name"], ch["id"])
        idx = self.channel_combo.findData(order["channel_id"])
        if idx >= 0:
            self.channel_combo.setCurrentIndex(idx)

        self.date_edit = QLineEdit(order["order_date"] or "")
        self.product_input = QLineEdit(order["product_name"] or "")
        self.option_input = QLineEdit(order["option_name"] or "")
        self.qty_input = QLineEdit(str(order["qty"] or 0))
        self.price_input = QLineEdit(str(order["sale_price"] or 0))
        self.total_input = QLineEdit(str(order["total_amount"] or 0))
        self.qty_input.textChanged.connect(self._auto_calc_total)
        self.price_input.textChanged.connect(self._auto_calc_total)
        self.fee_input = QLineEdit(str(order["fee_amount"] or 0))
        self.shipping_input = QLineEdit(str(order["shipping_fee"] or 0))
        self.settlement_input = QLineEdit(str(order["settlement_amount"] or 0))
        self.buyer_input = QLineEdit(order["buyer_name"] or "")
        self.status_combo = QComboBox()
        self.status_combo.addItems(["결제완료", "미결재", "배송준비", "배송중", "배송완료", "구매확정", "취소", "반품"])
        status_idx = self.status_combo.findText(order["status"] or "")
        if status_idx >= 0:
            self.status_combo.setCurrentIndex(status_idx)
        else:
            self.status_combo.setEditText(order["status"] or "")
        self.memo_input = QLineEdit(order["memo"] or "")

        form.addRow("판매 채널", self.channel_combo)
        form.addRow("주문일 (YYYY-MM-DD)", self.date_edit)
        form.addRow("상품명", self.product_input)
        form.addRow("옵션명", self.option_input)
        form.addRow("수량", self.qty_input)
        form.addRow("판매단가", self.price_input)
        form.addRow("매출금액 (수량×판매단가로 자동계산됨)", self.total_input)
        form.addRow("수수료", self.fee_input)
        form.addRow("배송비", self.shipping_input)
        form.addRow("정산금액", self.settlement_input)
        form.addRow("구매자명", self.buyer_input)
        form.addRow("주문상태", self.status_combo)
        form.addRow("메모", self.memo_input)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _auto_calc_total(self):
        def to_int(s, default=0):
            s = (s or "").strip().replace(",", "")
            return int(s) if s.lstrip("-").isdigit() else default
        qty = to_int(self.qty_input.text(), 0)
        price = to_int(self.price_input.text(), 0)
        self.total_input.setText(str(qty * price))

    def save(self):
        def to_int(s, default=0):
            s = (s or "").strip().replace(",", "")
            return int(s) if s.lstrip("-").isdigit() else default

        if not self.product_input.text().strip():
            QMessageBox.warning(self, "알림", "상품명은 필수입니다.")
            return

        row = {
            "channel_id": self.channel_combo.currentData(),
            "order_no": self.order["order_no"],
            "order_date": self.date_edit.text().strip(),
            "product_name": self.product_input.text().strip(),
            "option_name": self.option_input.text().strip(),
            "qty": to_int(self.qty_input.text(), 1),
            "sale_price": to_int(self.price_input.text()),
            "total_amount": to_int(self.total_input.text()),
            "fee_amount": to_int(self.fee_input.text()),
            "shipping_fee": to_int(self.shipping_input.text()),
            "settlement_amount": to_int(self.settlement_input.text()),
            "buyer_name": self.buyer_input.text().strip(),
            "status": self.status_combo.currentText(),
            "memo": self.memo_input.text().strip(),
        }
        db.update_order(self.order["id"], row)
        if row["status"] == "결제완료" and not self.order["is_settled"]:
            db.mark_orders_settled([(self.order["id"], row["settlement_amount"], row["order_date"])])
            if row["channel_id"]:
                db.add_settlement(row["channel_id"], row["order_date"], row["settlement_amount"], "수동 결제완료 처리")
        matching.rematch_all_orders()
        notify_data_changed()
        self.accept()


class PurchaseEditDialog(QDialog):
    """입고(매입) 1건 수정용 다이얼로그"""

    def __init__(self, purchase, parent=None):
        super().__init__(parent)
        self.purchase = purchase
        self._product_id = purchase["product_id"]
        self.setWindowTitle("입고 내역 수정")
        self.resize(420, 360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.supplier_combo = QComboBox()
        for s in db.get_suppliers():
            self.supplier_combo.addItem(s["name"], s["id"])
        idx = self.supplier_combo.findData(purchase["supplier_id"])
        if idx >= 0:
            self.supplier_combo.setCurrentIndex(idx)

        self.date_input = QLineEdit(purchase["purchase_date"] or "")

        self.product_input = QLineEdit(purchase["product_name"] or "")
        self.product_input.setReadOnly(True)
        self.option_input = QLineEdit(purchase["option_name"] or "")
        self.option_input.setReadOnly(True)
        product_row = QWidget()
        product_row_layout = QHBoxLayout(product_row)
        product_row_layout.setContentsMargins(0, 0, 0, 0)
        product_row_layout.addWidget(self.product_input)
        pick_btn = QPushButton("📋 상품 선택")
        pick_btn.clicked.connect(self.pick_product)
        product_row_layout.addWidget(pick_btn)

        self.qty_input = QLineEdit(str(purchase["qty"] or 0))
        self.unit_cost_input = QLineEdit(str(purchase["unit_cost"] or 0))
        self.total_input = QLineEdit(str(purchase["total_amount"] or 0))
        # 수량이나 단가를 고치면 합계금액을 자동으로 다시 계산
        self.qty_input.textChanged.connect(self._auto_calc_total)
        self.unit_cost_input.textChanged.connect(self._auto_calc_total)
        self.paid_input = QLineEdit(str(purchase["paid_amount"] or 0))
        self.memo_input = QLineEdit(purchase["memo"] or "")

        form.addRow("거래처", self.supplier_combo)
        form.addRow("입고일 (YYYY-MM-DD)", self.date_input)
        form.addRow("상품명(대분류)", product_row)
        form.addRow("옵션(소분류)", self.option_input)
        form.addRow("수량", self.qty_input)
        form.addRow("단가", self.unit_cost_input)
        form.addRow("합계금액", self.total_input)
        form.addRow("지급액", self.paid_input)
        form.addRow("메모", self.memo_input)
        layout.addLayout(form)

        if not purchase["product_id"]:
            warn = QLabel("⚠️ 이 입고건은 현재 연결된 품목이 없어요. '📋 상품 선택'으로 품목을 연결해주세요.")
            warn.setStyleSheet("color: #C0392B;")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def pick_product(self):
        dialog = ProductPickerDialog(self, recent_source="purchase")
        if dialog.exec() == QDialog.Accepted and dialog.selected_product:
            p = dialog.selected_product
            self._product_id = p["id"]
            self.product_input.setText(p["name"])
            self.option_input.setText(p["option_name"] or "")

    def _auto_calc_total(self):
        """수량 × 단가로 합계금액을 자동 계산 (단가는 소수점 허용)"""
        qty = to_int(self.qty_input.text(), 0)
        unit_cost = to_float(self.unit_cost_input.text(), 0)
        total = qty * unit_cost
        # 소수점이 없으면 정수로 깔끔하게 표시
        self.total_input.setText(
            str(int(round(total))) if abs(total - round(total)) < 1e-9 else f"{total:.1f}")

    def save(self):
        def to_int(s, default=0):
            s = (s or "").strip().replace(",", "")
            return int(s) if s.lstrip("-").isdigit() else default

        db.update_purchase(
            self.purchase["id"],
            self.date_input.text().strip(),
            self.supplier_combo.currentData(),
            self._product_id,
            to_int(self.qty_input.text()),
            to_float(self.unit_cost_input.text()),   # 단가는 소수점 한 자리까지 허용
            to_float(self.total_input.text()),
            to_int(self.paid_input.text()),
            self.memo_input.text().strip(),
        )
        try:
            matching.rematch_all_orders()
        except Exception:
            pass
        notify_data_changed()
        self.accept()


class IncomingTab(QWidget):
    """입고관리 - 거래처(매입처)로부터 상품을 입고(매입)받은 내역을 수기로 기록.
    등록하면 품목관리의 재고수량이 자동으로 늘어나고, 원가도 최신 매입단가로 갱신됩니다."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("📥 입고관리 (매입 등록)")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        note = QLabel("💡 여기서 입고를 등록하면 품목관리의 재고수량이 자동으로 늘어나고, "
                      "원가도 최근 매입단가로 갱신돼요.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        form_box = QGroupBox("입고(매입) 등록")
        form = QFormLayout(form_box)

        self.supplier_combo = QComboBox()
        self.supplier_combo.setFixedWidth(220)  # 한글 약 15자 기준
        self.supplier_combo.currentIndexChanged.connect(lambda _: self._update_last_price_hint())
        supplier_row = QWidget()
        supplier_row_layout = QHBoxLayout(supplier_row)
        supplier_row_layout.setContentsMargins(0, 0, 0, 0)
        supplier_row_layout.addWidget(self.supplier_combo)
        pick_supplier_btn = QPushButton("📋 거래처 선택")
        pick_supplier_btn.clicked.connect(self.pick_supplier)
        supplier_row_layout.addWidget(pick_supplier_btn)
        add_supplier_btn = QPushButton("➕ 새 거래처 등록")
        add_supplier_btn.clicked.connect(self.add_new_supplier)
        supplier_row_layout.addWidget(add_supplier_btn)
        supplier_row_layout.addStretch()
        form.addRow("거래처 *", supplier_row)

        self.date_edit = make_date_edit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setFixedWidth(150)
        form.addRow("입고일", self.date_edit)

        self.product_input = QLineEdit()
        self.product_input.setFixedWidth(220)  # 한글 약 15자 기준
        product_row = QWidget()
        product_row_layout = QHBoxLayout(product_row)
        product_row_layout.setContentsMargins(0, 0, 0, 0)
        product_row_layout.addWidget(self.product_input)
        pick_btn = QPushButton("📋 상품 선택")
        pick_btn.clicked.connect(self.pick_product)
        product_row_layout.addWidget(pick_btn)
        add_product_btn = QPushButton("➕ 상품 등록")
        add_product_btn.clicked.connect(self.quick_add_product)
        product_row_layout.addWidget(add_product_btn)
        product_row_layout.addStretch()
        form.addRow("품목명 *", product_row)
        self._picked_product_id = None

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(-9999999, 9999999)  # 반품(마이너스 입고)도 입력 가능하도록
        self.qty_spin.setValue(1)
        self.qty_spin.setGroupSeparatorShown(True)  # 천단위 콤마 표시
        self.qty_spin.setFixedWidth(110)
        self.qty_preset = QComboBox()
        self._reload_qty_presets()
        self.qty_preset.currentTextChanged.connect(self._apply_qty_preset)
        self.qty_preset.setFixedWidth(100)
        qty_row = QWidget()
        qty_row_layout = QHBoxLayout(qty_row)
        qty_row_layout.setContentsMargins(0, 0, 0, 0)
        qty_row_layout.addWidget(self.qty_preset)
        qty_row_layout.addWidget(self.qty_spin)
        return_btn = QPushButton("↩️ 반품(마이너스)")
        return_btn.setToolTip("업체에 반품하는 경우 - 누르면 현재 수량의 부호가 반전됩니다")
        return_btn.clicked.connect(self.toggle_return_sign)
        qty_row_layout.addWidget(return_btn)
        qty_row_layout.addStretch()
        form.addRow("수량 (반품시 마이너스)", qty_row)

        # 단가는 '공급가액(부가세 별도)'을 기준으로 저장함.
        # 세금계산서에 합계금액(VAT포함)만 적혀 있는 경우도 많아서,
        # 어느 쪽을 넣어도 나머지가 자동으로 계산되게 함.
        self.unit_cost_input = QLineEdit("0")
        self.unit_cost_input.setFixedWidth(200)

        unit_row = QWidget()
        unit_row_layout = QHBoxLayout(unit_row)
        unit_row_layout.setContentsMargins(0, 0, 0, 0)
        unit_row_layout.addWidget(self.unit_cost_input)
        self.unit_supply_input = QLineEdit()
        self.unit_supply_input.setFixedWidth(110)
        self.unit_supply_input.setPlaceholderText("공급가액")
        self.unit_vat_input = QLineEdit()
        self.unit_vat_input.setFixedWidth(110)
        self.unit_vat_input.setPlaceholderText("합계(VAT포함)")
        unit_row_layout.addWidget(QLabel("공급가액"))
        unit_row_layout.addWidget(self.unit_supply_input)
        unit_row_layout.addWidget(QLabel("↔ 합계"))
        unit_row_layout.addWidget(self.unit_vat_input)
        unit_row_layout.addStretch()
        self._unit_vat_busy = False
        self.unit_supply_input.textEdited.connect(self._on_unit_supply_edited)
        self.unit_vat_input.textEdited.connect(self._on_unit_vat_edited)
        self.unit_cost_input.textEdited.connect(self._on_unit_cost_edited)
        form.addRow("단가 (공급가액 기준)", unit_row)

        unit_hint = QLabel("    └ 세금계산서의 공급가액이나 합계금액 중 아는 쪽을 넣으면 "
                           "나머지가 자동 계산됩니다. 단가에는 공급가액이 들어갑니다.")
        unit_hint.setStyleSheet("color:#888; font-size:11px;")
        unit_hint.setWordWrap(True)
        form.addRow("", unit_hint)

        self.total_input = QLineEdit()
        self.total_input.setFixedWidth(200)
        self.total_input.setPlaceholderText("비워두면 수량×단가로 자동 계산")
        form.addRow("합계금액", self.total_input)

        self.paid_input = QLineEdit("0")
        self.paid_input.setFixedWidth(200)
        form.addRow("지급액 (결제한 금액)", self.paid_input)

        self.memo_input = QLineEdit()
        self.memo_input.setFixedWidth(400)
        form.addRow("메모", self.memo_input)

        save_btn = QPushButton("➕ 입고 등록")
        save_btn.setFixedWidth(220)
        save_btn.clicked.connect(self.save_purchase)
        save_btn_row = QHBoxLayout()
        save_btn_row.addWidget(save_btn)
        batch_btn = QPushButton("📦 여러 품목 한번에 입고")
        batch_btn.setToolTip("여러 품목을 체크박스로 골라서 한 번에 입고 등록합니다 "
                              "(거래처·입고일은 공통, 수량·단가는 품목별로 입력)")
        batch_btn.setFixedWidth(220)
        batch_btn.clicked.connect(self.open_batch_purchase)
        save_btn_row.addWidget(batch_btn)
        save_btn_row.addStretch()
        form.addRow(save_btn_row)

        layout.addWidget(form_box)

        action_box = QGroupBox("선택 항목 관리 (표 왼쪽 체크박스로 선택)")
        action_layout = QHBoxLayout(action_box)
        edit_btn = QPushButton("✏️ 수정")
        edit_btn.clicked.connect(self.edit_checked)
        action_layout.addWidget(edit_btn)
        delete_btn = QPushButton("🗑️ 삭제")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(self.delete_checked)
        action_layout.addWidget(delete_btn)
        action_layout.addStretch()
        layout.addWidget(action_box)

        filter_box = QGroupBox("조회 필터 (입고 리스트)")
        filter_layout = QHBoxLayout(filter_box)
        self.list_date_from = make_date_edit()
        self.list_date_from.setDate(QDate.currentDate())   # 기본은 오늘
        filter_layout.addWidget(tight_pair("시작일:", self.list_date_from))
        self.list_date_to = make_date_edit()
        self.list_date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(tight_pair("종료일:", self.list_date_to))
        filter_layout.addSpacing(24)  # 날짜 입력칸과 버튼 사이에만 약간 여백
        list_search_btn = QPushButton("조회")
        list_search_btn.clicked.connect(self.refresh)
        filter_layout.addWidget(list_search_btn)
        today_btn = QPushButton("오늘")
        today_btn.clicked.connect(self.reset_list_filter)
        filter_layout.addWidget(today_btn)
        week7_btn = QPushButton("최근 7일")
        week7_btn.clicked.connect(self.set_last_7days)
        filter_layout.addWidget(week7_btn)
        thisweek_btn = QPushButton("이번주")
        thisweek_btn.clicked.connect(self.set_this_week)
        filter_layout.addWidget(thisweek_btn)
        thismonth_btn = QPushButton("이번달")
        thismonth_btn.clicked.connect(self.set_this_month)
        filter_layout.addWidget(thismonth_btn)
        filter_layout.addStretch()
        layout.addWidget(filter_box)

        # 조회된 입고 리스트의 집계 (건수/수량/금액/지급/미결제)
        self.list_summary_label = QLabel("")
        self.list_summary_label.setStyleSheet(
            "padding: 10px; background: #EAF2F8; border-radius: 6px; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.list_summary_label)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_double_clicked)
        enable_persistent_column_widths(self.table, "purchases")
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh, exclude_columns=(0,))
        layout.addWidget(self.table)

        self.reload_suppliers()
        self.refresh()

    def reset_list_filter(self):
        """기본값: 오늘 하루"""
        today = QDate.currentDate()
        self.list_date_from.setDate(today)
        self.list_date_to.setDate(today)
        self.refresh()

    def set_last_7days(self):
        self.list_date_from.setDate(QDate.currentDate().addDays(-6))
        self.list_date_to.setDate(QDate.currentDate())
        self.refresh()

    def set_this_week(self):
        """이번주 (월요일 ~ 오늘)"""
        today = QDate.currentDate()
        self.list_date_from.setDate(today.addDays(-(today.dayOfWeek() - 1)))
        self.list_date_to.setDate(today)
        self.refresh()

    def set_this_month(self):
        today = QDate.currentDate()
        self.list_date_from.setDate(QDate(today.year(), today.month(), 1))
        self.list_date_to.setDate(today)
        self.refresh()

    def reload_suppliers(self):
        """기본값은 빈칸(선택 안 함) - 실수로 엉뚱한 거래처에 입고되는 것 방지"""
        current = self.supplier_combo.currentData()
        self.supplier_combo.clear()
        self.supplier_combo.addItem("", None)
        for s in db.get_suppliers():
            self.supplier_combo.addItem(s["name"], s["id"])
        if current:
            idx = self.supplier_combo.findData(current)
            if idx >= 0:
                self.supplier_combo.setCurrentIndex(idx)
        else:
            self.supplier_combo.setCurrentIndex(0)

    def pick_supplier(self):
        try:
            dialog = SupplierPickerDialog(self)
            if dialog.exec() == QDialog.Accepted and dialog.selected_supplier:
                self.reload_suppliers()  # 콤보를 최신 상태로 먼저 맞춘 뒤 선택 반영
                idx = self.supplier_combo.findData(dialog.selected_supplier["id"])
                if idx >= 0:
                    self.supplier_combo.setCurrentIndex(idx)
                else:
                    # findData가 실패해도 최소한 이름은 바로 보이도록 함
                    self.supplier_combo.setCurrentText(dialog.selected_supplier["name"])
                self.supplier_combo.update()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"거래처 선택 중 오류가 발생했습니다:\n{e}")

    def add_new_supplier(self):
        dialog = NewChannelDialog(self)
        dialog.stack.setCurrentIndex(2)  # 바로 '일반 거래업체' 상세입력으로
        if dialog.exec() == QDialog.Accepted and dialog.result_channel_id:
            self.reload_suppliers()
            idx = self.supplier_combo.findData(dialog.result_channel_id)
            if idx >= 0:
                self.supplier_combo.setCurrentIndex(idx)

    def _update_last_price_hint(self):
        """거래처+품목이 정해지면 이전 입고단가를 자동으로 불러와 단가란에 채워줌"""
        if not hasattr(self, "unit_cost_input") or not hasattr(self, "supplier_combo"):
            return  # 초기화 중 신호가 먼저 발생하는 경우 방지
        supplier_id = self.supplier_combo.currentData()
        product_id = getattr(self, "_picked_product_id", None)
        self._last_known_unit_cost = db.get_last_purchase_price(supplier_id, product_id)
        if self._last_known_unit_cost is not None:
            self.unit_cost_input.setText(str(self._last_known_unit_cost))
            self._sync_unit_vat_fields()

    def pick_product(self):
        dialog = ProductPickerDialog(self, recent_source="purchase")
        if dialog.exec() == QDialog.Accepted and dialog.selected_product:
            p = dialog.selected_product
            display_name = f"{p['name']} {p['option_name']}".strip() if p["option_name"] else p["name"]
            self.product_input.setText(display_name)
            self._picked_product_id = p["id"]
            self.unit_cost_input.setText(str(p["cost_price"] or 0))
            self._sync_unit_vat_fields()
            self._update_last_price_hint()

    def quick_add_product(self):
        dialog = QuickAddProductDialog(self, default_name=self.product_input.text().strip())
        if dialog.exec() == QDialog.Accepted and getattr(dialog, "new_product", None):
            p = dialog.new_product
            self.product_input.setText(p["name"])
            self._picked_product_id = p["id"]
            self.unit_cost_input.setText(str(p["cost_price"] or 0))
            self._sync_unit_vat_fields()
            self._update_last_price_hint()

    def _reload_qty_presets(self):
        """수량 목록을 DB에서 다시 읽어옴 (사용자가 직접 설정한 목록)"""
        self.qty_preset.blockSignals(True)
        self.qty_preset.clear()
        for q in db.get_qty_presets("incoming"):
            self.qty_preset.addItem(f"{q:,}")
        self.qty_preset.addItem("✏️ 수량목록 직접설정")
        self.qty_preset.blockSignals(False)

    def _apply_qty_preset(self, text):
        if "직접설정" in text:
            dialog = QtyPresetEditDialog("incoming", self)
            if dialog.exec() == QDialog.Accepted:
                self._reload_qty_presets()
            else:
                self.qty_preset.setCurrentIndex(0)
            return
        digits = text.replace(",", "").strip()
        if digits.isdigit():
            self.qty_spin.setValue(int(digits))

    def open_batch_purchase(self):
        """여러 품목 선택 -> 품목별 수량·단가 입력 -> 일괄 등록"""
        if not db.get_products():
            QMessageBox.warning(self, "알림", "먼저 품목관리에서 품목을 등록해주세요.")
            return
        picker = MultiProductPickerDialog(self)
        if picker.exec() != QDialog.Accepted or not picker.selected_products:
            return
        dialog = BatchPurchaseDialog(
            picker.selected_products,
            supplier_id=self.supplier_combo.currentData(),
            purchase_date=self.date_edit.date(),
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted:
            self.refresh(auto_fit_columns=True)

    def toggle_return_sign(self):
        """반품 버튼: 현재 수량의 부호를 반전 (양수<->음수). 반품(업체에 되돌려줌)은
        마이너스 수량으로 등록하면 재고가 그만큼 줄고, 지급했던 금액도 그만큼 줄어듦"""
        self.qty_spin.setValue(-self.qty_spin.value())

    def _sync_unit_vat_fields(self):
        """단가가 프로그램에서 자동으로 채워졌을 때 공급가액·합계 칸도 맞춰줌"""
        if not hasattr(self, "unit_supply_input"):
            return
        self._unit_vat_busy = True
        try:
            supply = to_float(self.unit_cost_input.text(), 0)
            self.unit_supply_input.setText(self._fmt_unit(supply))
            self.unit_vat_input.setText(self._fmt_unit(round(supply * 1.1, 1)))
        finally:
            self._unit_vat_busy = False

    # ----- 입고 단가: 공급가액 <-> 합계금액(VAT포함) 자동 계산 -----
    @staticmethod
    def _fmt_unit(v):
        """소수점 한 자리까지만 보여주고, 정수면 소수점을 떼어냄"""
        return f"{v:.1f}".rstrip("0").rstrip(".") if v else "0"

    def _on_unit_supply_edited(self, text):
        """공급가액을 넣으면 합계(×1.1)와 단가를 채움"""
        if getattr(self, "_unit_vat_busy", False):
            return
        self._unit_vat_busy = True
        try:
            supply = to_float(text, 0)
            self.unit_vat_input.setText(self._fmt_unit(round(supply * 1.1, 1)))
            self.unit_cost_input.setText(self._fmt_unit(round(supply, 1)))
            if hasattr(self, '_auto_calc_total'):
                self._auto_calc_total()
        finally:
            self._unit_vat_busy = False

    def _on_unit_vat_edited(self, text):
        """합계(VAT포함)를 넣으면 공급가액(÷1.1)과 단가를 채움"""
        if getattr(self, "_unit_vat_busy", False):
            return
        self._unit_vat_busy = True
        try:
            total = to_float(text, 0)
            supply = round(total / 1.1, 1) if total else 0
            self.unit_supply_input.setText(self._fmt_unit(supply))
            self.unit_cost_input.setText(self._fmt_unit(supply))
            if hasattr(self, '_auto_calc_total'):
                self._auto_calc_total()
        finally:
            self._unit_vat_busy = False

    def _on_unit_cost_edited(self, text):
        """단가를 직접 고치면 공급가액·합계 칸도 맞춰줌"""
        if getattr(self, "_unit_vat_busy", False):
            return
        self._unit_vat_busy = True
        try:
            supply = to_float(text, 0)
            self.unit_supply_input.setText(self._fmt_unit(supply))
            self.unit_vat_input.setText(self._fmt_unit(round(supply * 1.1, 1)))
        finally:
            self._unit_vat_busy = False

    def save_purchase(self):
        def to_int(s, default=0):
            s = (s or "").strip().replace(",", "")
            return int(s) if s.lstrip("-").isdigit() else default

        supplier_id = self.supplier_combo.currentData()
        product_name = self.product_input.text().strip()
        if supplier_id is None:
            QMessageBox.warning(self, "알림", "거래처를 선택하거나 등록해주세요.")
            return
        if not product_name:
            QMessageBox.warning(self, "알림", "품목명을 입력하거나 선택해주세요.")
            return

        # 상품명으로 기존 품목을 찾아 재고/원가에 반영 (직접 타이핑한 경우 대비)
        # 화면에 "대분류 옵션" 형태로 보이는 이름을 그대로 입력하는 경우가 많아서,
        # 대분류만이 아니라 "대분류+옵션" 조합과도 비교함 (공백 차이도 무시)
        product_id = self._picked_product_id
        if product_id is None:
            def norm(s):
                return "".join((s or "").split()).lower()

            target = norm(product_name)
            for p in db.get_products():
                combined = f"{p['name']} {p['option_name'] or ''}"
                reversed_combined = f"{p['option_name'] or ''} {p['name']}"
                if target in (norm(p["name"]), norm(combined), norm(reversed_combined)):
                    product_id = p["id"]
                    break

        qty = self.qty_spin.value()
        if qty == 0:
            QMessageBox.warning(self, "알림", "수량을 입력해주세요.")
            return
        if qty < 0:
            reply = QMessageBox.question(
                self, "반품 확인",
                f"수량이 마이너스({qty})입니다. 반품(업체에 {abs(qty)}개를 돌려줌)으로 등록하시겠습니까?\n"
                "재고가 그만큼 줄어들고, 합계금액/지급액도 마이너스로 기록됩니다."
            )
            if reply != QMessageBox.Yes:
                return
        unit_cost = to_float(self.unit_cost_input.text(), 0)
        total_text = self.total_input.text().strip()
        total_amount = to_int(total_text) if total_text else qty * unit_cost
        paid_amount = to_int(self.paid_input.text(), 0)

        # 이전 입고단가와 10% 이상 차이나면 경고 (등록은 그대로 진행)
        last_cost = db.get_last_purchase_price(supplier_id, product_id) if product_id else None
        if last_cost and last_cost > 0 and unit_cost > 0:
            diff_ratio = abs(unit_cost - last_cost) / last_cost
            if diff_ratio >= 0.10:
                QMessageBox.warning(
                    self, "단가 변동 알림",
                    f"이전 입고단가({fmt_won(last_cost)})와 10% 이상 차이가 납니다.\n"
                    f"이번 입고단가: {fmt_won(unit_cost)} (변동률 {diff_ratio*100:.1f}%)\n\n"
                    "그대로 등록을 진행합니다."
                )

        # 등록된 품목이 없으면 입고를 저장하기 전에 먼저 새로 등록해서 product_id를 확보함
        # (예전엔 입고를 먼저 저장한 뒤에 품목을 나중에 만들어서, 새로 만든 품목과 입고
        #  기록이 서로 연결이 안 되는 바람에 리스트/수정창에 품목명·옵션이 안 보였음)
        newly_created = False
        if product_id is None:
            reply = QMessageBox.question(
                self, "새 품목 등록 확인",
                f"'{product_name}' 은(는) 품목관리에 등록된 품목과 이름이 일치하지 않습니다.\n\n"
                "새 품목으로 등록할까요?\n"
                "(기존 품목에 재고를 더하려면 '아니오'를 누르고 '📋 상품 선택' 버튼으로 골라주세요)"
            )
            if reply != QMessageBox.Yes:
                return
            product_id = db.add_product("", product_name, unit_cost, 0, qty, "자동등록(입고)")
            newly_created = True

        db.add_purchase(
            self.date_edit.date().toString("yyyy-MM-dd"), supplier_id, product_id,
            qty, unit_cost, total_amount, paid_amount, self.memo_input.text().strip(),
        )

        # 새로 만든 품목은 이미 재고=입고수량/원가=입고단가로 등록됐으니 중복 반영하지 않고,
        # 기존 품목에 입고한 경우에만 재고를 "추가로" 늘리고 원가를 최신 단가로 갱신
        if not newly_created:
            product = next((p for p in db.get_products() if p["id"] == product_id), None)
            if product:
                db.update_product(
                    product_id, product["sku"], product["name"], unit_cost,
                    product["sale_price"], (product["stock_qty"] or 0) + qty, product["memo"],
                    option_name=product["option_name"],
                    cost_source="입고 등록",
                )

        msg = "입고가 등록되었습니다. 품목관리의 재고/원가에 반영됐어요."
        try:
            matching.rematch_all_orders()
            notify_data_changed()
        except Exception as e:
            msg += f"\n\n⚠️ 후속 처리 중 오류가 있었습니다:\n{e}"
        finally:
            self.product_input.clear()
            self._picked_product_id = None
            self.qty_spin.setValue(1)
            self.qty_preset.setCurrentIndex(0)
            self.unit_cost_input.setText("0")
            self._sync_unit_vat_fields()
            self.total_input.clear()
            self.paid_input.setText("0")
            self.memo_input.clear()
            QMessageBox.information(self, "완료", msg)
            self.refresh(auto_fit_columns=True)

    def refresh(self, auto_fit_columns=False):
        date_from = self.list_date_from.date().toString("yyyy-MM-dd") if hasattr(self, "list_date_from") else None
        date_to = self.list_date_to.date().toString("yyyy-MM-dd") if hasattr(self, "list_date_to") else None
        purchases = db.get_purchases(date_from=date_from, date_to=date_to)

        headers = ["선택", "입고일", "거래처", "상품명(대분류)", "옵션(소분류)", "수량", "단가", "합계금액", "지급액", "미결제", "메모"]

        display_rows = []
        for p in purchases:
            unpaid = (p["total_amount"] or 0) - (p["paid_amount"] or 0)
            display_rows.append((
                "", p["purchase_date"], p["supplier_name"], p["product_name"], p["option_name"] or "", p["qty"],
                fmt_price(p["unit_cost"]), fmt_price(p["total_amount"]), fmt_won(p["paid_amount"]),
                fmt_won(unpaid), p["memo"],
            ))
        # 조회 결과 집계
        total_count = len(purchases)
        total_qty = sum(p["qty"] or 0 for p in purchases)
        total_amount = sum(p["total_amount"] or 0 for p in purchases)
        total_paid = sum(p["paid_amount"] or 0 for p in purchases)
        total_unpaid = total_amount - total_paid
        supplier_count = len({p["supplier_id"] for p in purchases if p["supplier_id"]})
        self.list_summary_label.setText(
            f"📊 조회 결과   —   입고 {total_count:,}건 (거래처 {supplier_count}곳)   |   "
            f"총 수량 {total_qty:,}개   |   총 매입금액 {fmt_price(total_amount)}   |   "
            f"지급 {fmt_won(total_paid)}   |   미결제 {fmt_won(total_unpaid)}"
        )

        display_rows, purchases = apply_table_sort(display_rows, purchases, self._sort_state)
        self._purchase_ids = [p["id"] for p in purchases]

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(purchases))

        for r, values in enumerate(display_rows):
            checkbox_container, _ = make_checkbox_cell()
            self.table.setCellWidget(r, 0, checkbox_container)

            for c, val in enumerate(values):
                if c == 0:
                    continue
                text = str(val) if val is not None else ""
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if looks_numeric(text):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)

        header = self.table.horizontalHeader()
        header.blockSignals(True)
        self.table.resizeColumnsToContents()
        header.blockSignals(False)
        self.table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        if auto_fit_columns:
            # 등록 직후: 저장된 폭 대신 지금 내용 기준으로 다시 맞춤 (이 폭이 새로 저장됨)
            self.table.resizeColumnsToContents()
        else:
            restore_column_widths(self.table, "purchases")

    def get_checked_ids(self):
        checked = []
        for r in range(self.table.rowCount()):
            if is_row_checked(self.table, r):
                checked.append(self._purchase_ids[r])
        return checked

    def on_double_clicked(self, row, column):
        if column == 0 or row < 0 or row >= len(self._purchase_ids):
            return
        pid = self._purchase_ids[row]
        menu = QMenu(self)
        edit_action = menu.addAction("✏️ 수정")
        delete_action = menu.addAction("🗑️ 삭제")
        chosen = menu.exec(QCursor.pos())
        if chosen == edit_action:
            self._open_edit(pid)
        elif chosen == delete_action:
            self._delete_ids([pid])

    def edit_checked(self):
        checked = self.get_checked_ids()
        if len(checked) != 1:
            QMessageBox.warning(self, "알림", "수정은 한 번에 한 건만 가능합니다.\n체크박스에서 1개만 선택해주세요.")
            return
        self._open_edit(checked[0])

    def _open_edit(self, purchase_id):
        purchase = db.get_purchase_by_id(purchase_id)
        if not purchase:
            return
        dialog = PurchaseEditDialog(purchase, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def delete_checked(self):
        checked = self.get_checked_ids()
        if not checked:
            QMessageBox.warning(self, "알림", "삭제할 항목을 체크박스에서 선택해주세요.")
            return
        self._delete_ids(checked)

    def _delete_ids(self, ids):
        if confirm_delete(
                self, f"입고(매입) 내역 {len(ids)}건",
                "품목 재고는 자동으로 다시 줄어들지 않으니, 필요하면 품목관리에서 직접 조정해주세요.",
                double_check=len(ids) >= 10):
            try:
                for pid in ids:
                    db.delete_purchase(pid)
            except Exception as e:
                QMessageBox.critical(self, "오류", f"삭제 중 오류가 발생했습니다:\n{e}")
            finally:
                self.refresh()
                notify_data_changed()


class OrderStatusSettingsDialog(QDialog):
    """수동 주문등록에서 쓸 주문상태 목록을 직접 정하는 창"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("주문상태 설정")
        self.resize(360, 400)

        layout = QVBoxLayout(self)
        note = QLabel("💡 수동 주문등록의 주문상태 드롭다운에 나올 항목을 정합니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        add_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("예: 배송중")
        self.input.returnPressed.connect(self.add_item)
        add_row.addWidget(self.input)
        add_btn = QPushButton("➕ 추가")
        add_btn.clicked.connect(self.add_item)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        up_btn = QPushButton("▲ 위로")
        up_btn.clicked.connect(lambda: self.move_item(-1))
        btn_row.addWidget(up_btn)
        down_btn = QPushButton("▼ 아래로")
        down_btn.clicked.connect(lambda: self.move_item(1))
        btn_row.addWidget(down_btn)
        del_btn = QPushButton("🗑️ 삭제")
        del_btn.setStyleSheet("color: red;")
        del_btn.clicked.connect(self.delete_item)
        btn_row.addWidget(del_btn)
        layout.addLayout(btn_row)

        save_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        save_row.addWidget(save_btn)
        reset_btn = QPushButton("기본값")
        reset_btn.clicked.connect(self.reset_default)
        save_row.addWidget(reset_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        save_row.addWidget(cancel_btn)
        layout.addLayout(save_row)

        saved = _qsettings.value("order/status_list")
        items = [s for s in (saved.split("|") if isinstance(saved, str) and saved else []) if s]
        for s in (items or ["외상", "결재완료"]):
            self.list_widget.addItem(s)

    def add_item(self):
        text = self.input.text().strip()
        if not text:
            return
        existing = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        if text in existing:
            QMessageBox.warning(self, "알림", "이미 목록에 있는 상태입니다.")
            return
        self.list_widget.addItem(text)
        self.input.clear()

    def move_item(self, direction):
        row = self.list_widget.currentRow()
        new_row = row + direction
        if row < 0 or new_row < 0 or new_row >= self.list_widget.count():
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(new_row, item)
        self.list_widget.setCurrentRow(new_row)

    def delete_item(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row)

    def reset_default(self):
        self.list_widget.clear()
        for s in ("외상", "결재완료"):
            self.list_widget.addItem(s)

    def save(self):
        items = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        if not items:
            QMessageBox.warning(self, "알림", "주문상태를 하나 이상 등록해주세요.")
            return
        _qsettings.setValue("order/status_list", "|".join(items))
        self.accept()


class OrdersTab(QWidget):
    def __init__(self, on_data_changed=None):
        super().__init__()
        self.on_data_changed = on_data_changed
        layout = QVBoxLayout(self)

        title_row = QHBoxLayout()
        title = QLabel("🛒 주문 관리 (파일 업로드 / 수동 입력)")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title_row.addWidget(title)
        title_row.addStretch()
        gear_btn = QPushButton("⚙️ 주문관리 설정")
        gear_btn.setToolTip("수동 주문등록에서 서류를 자동으로 뽑을지 미리 정해둡니다")
        gear_btn.clicked.connect(self.open_orders_settings)
        title_row.addWidget(gear_btn)
        layout.addLayout(title_row)

        # 업로드 영역
        upload_box = QGroupBox("주문 파일 업로드")
        upload_layout = QHBoxLayout(upload_box)
        upload_layout.setSpacing(15)

        self.channel_combo = QComboBox()
        self.reload_channels()
        upload_layout.addWidget(tight_pair("판매 채널:", self.channel_combo))

        add_channel_btn = QPushButton("➕ 채널 추가")
        add_channel_btn.clicked.connect(self.add_new_channel)
        upload_layout.addWidget(add_channel_btn)

        delete_channel_btn = QPushButton("🗑️ 선택 채널 삭제")
        delete_channel_btn.setStyleSheet("color: red;")
        delete_channel_btn.clicked.connect(self.delete_selected_channel)
        upload_layout.addWidget(delete_channel_btn)

        upload_btn = QPushButton("📁 엑셀/CSV 파일 선택해서 업로드")
        upload_btn.clicked.connect(self.upload_file)
        upload_layout.addWidget(upload_btn)
        upload_layout.addStretch()

        layout.addWidget(upload_box)

        # 업로드 파일 목록 (10개 정도 한번에 보이도록 높이 확보)
        history_box = QGroupBox("📋 업로드 파일 목록 (기본: 최근 7일)")
        history_layout = QVBoxLayout(history_box)
        history_hint = QLabel("💡 목록에 안 보이면 조회 기간을 넓혀보세요. 기간 밖이라 안 보이는 것일 뿐, "
                               "주문 데이터는 그대로 저장되어 있습니다.")
        history_hint.setStyleSheet("color: #666;")
        history_hint.setWordWrap(True)
        history_layout.addWidget(history_hint)

        history_filter_row = QHBoxLayout()
        self.history_date_from = make_date_edit()
        # 기본을 최근 7일로 (오늘만 보이면 어제 올린 파일이 사라진 것처럼 보임)
        self.history_date_from.setDate(QDate.currentDate())   # 기본 오늘
        history_filter_row.addWidget(tight_pair("검색 시작일:", self.history_date_from))
        self.history_date_to = make_date_edit()
        self.history_date_to.setDate(QDate.currentDate())
        history_filter_row.addWidget(tight_pair("검색 종료일:", self.history_date_to))
        history_search_btn = QPushButton("조회")
        history_search_btn.clicked.connect(self.refresh_upload_history)
        history_filter_row.addWidget(history_search_btn)
        for text, days in [("최근 7일", 7), ("지난주", -1), ("이번달", 0)]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked, d=days: self._set_history_period(d))
            history_filter_row.addWidget(btn)
        del_upload_btn = QPushButton("🗑️ 업로드 삭제")
        del_upload_btn.setStyleSheet("color: red;")
        del_upload_btn.setToolTip("선택한 업로드 기록을 삭제합니다 (그 파일로 등록된 주문도 함께 지울지 물어봅니다)")
        del_upload_btn.clicked.connect(self.delete_upload_history)
        history_filter_row.addWidget(del_upload_btn)
        history_filter_row.addStretch()
        history_layout.addLayout(history_filter_row)

        self.upload_count_label = QLabel("")
        self.upload_count_label.setStyleSheet(
            "padding: 5px; background: #EAF2F8; border-radius: 5px; font-weight: bold;")
        history_layout.addWidget(self.upload_count_label)

        self.upload_history_table = QTableWidget()
        self.upload_history_table.setMinimumHeight(200)
        self.upload_history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.upload_history_table.cellDoubleClicked.connect(self.on_upload_history_double_clicked)
        # 요청하신 대로 컬럼(헤더) 배경을 노란색으로
        self.upload_history_table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)
        self._upload_history_sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.upload_history_table, self._upload_history_sort_state, self.refresh_upload_history)
        history_layout.addWidget(self.upload_history_table)
        layout.addWidget(history_box)

        # 수동 등록 영역 (기본으로 펼쳐서 보이게 함 - 체크박스로 접었다 펼 수도 있음)
        manual_box = QGroupBox("✍️ 수동 주문 등록 (파일 없이 직접 입력)")
        manual_box.setCheckable(True)
        manual_box.setChecked(_qsettings.value("order/manual_expanded", "false") == "true")  # 기본 접힘
        manual_box.toggled.connect(
            lambda checked: _qsettings.setValue("order/manual_expanded", "true" if checked else "false"))
        self.manual_box = manual_box
        self._manual_box_widget = None  # 내용 위젯 (생성 후 설정)
        self.editing_order_id = None   # 수정 중인 주문 id (없으면 등록 모드)
        manual_outer = QVBoxLayout(manual_box)

        self.manual_content = QWidget()
        manual_outer_v = QVBoxLayout(self.manual_content)
        manual_outer_v.setContentsMargins(0, 0, 0, 0)

        basic_grid = QGridLayout()
        basic_grid.setHorizontalSpacing(20)
        basic_grid.setVerticalSpacing(8)

        self.manual_channel = QComboBox()
        self.manual_channel.setFixedWidth(200)
        manual_channel_row = QWidget()
        manual_channel_row_layout = QHBoxLayout(manual_channel_row)
        manual_channel_row_layout.setContentsMargins(0, 0, 0, 0)
        manual_channel_row_layout.addWidget(self.manual_channel)
        self.manual_channel.currentIndexChanged.connect(lambda _: self._fill_last_sale_price())
        manual_pick_channel_btn = QPushButton("📋 거래처 선택")
        manual_pick_channel_btn.clicked.connect(self.pick_manual_channel)
        manual_channel_row_layout.addWidget(manual_pick_channel_btn)
        manual_add_channel_btn = QPushButton("➕ 거래처 추가")
        manual_add_channel_btn.clicked.connect(self.add_new_supplier)
        manual_channel_row_layout.addWidget(manual_add_channel_btn)
        manual_channel_row_layout.addStretch()

        self.manual_date = make_date_edit()
        self.manual_date.setDate(QDate.currentDate())
        self.manual_date.setFixedWidth(160)

        self.manual_product = QLineEdit()
        self.manual_product.setFixedWidth(220)
        manual_product_row = QWidget()
        manual_product_row_layout = QHBoxLayout(manual_product_row)
        manual_product_row_layout.setContentsMargins(0, 0, 0, 0)
        manual_product_row_layout.addWidget(self.manual_product)
        pick_product_btn = QPushButton("📋 상품 선택")
        pick_product_btn.clicked.connect(self.pick_product)
        manual_product_row_layout.addWidget(pick_product_btn)
        self.multi_pick_btn = QPushButton("➕ 복수선택")
        self.multi_pick_btn.setToolTip("여러 상품을 담아서 한 번에 등록합니다")
        self.multi_pick_btn.clicked.connect(self.pick_multi_products)
        self.multi_pick_btn.setVisible(
            _qsettings.value("order/multi_pick", "false") == "true")
        manual_product_row_layout.addWidget(self.multi_pick_btn)
        add_product_btn = QPushButton("➕ 상품 등록")
        add_product_btn.clicked.connect(self.quick_add_product)
        manual_product_row_layout.addWidget(add_product_btn)
        manual_product_row_layout.addStretch()

        # 옵션명은 상품 선택시 자동으로 채워지므로 별도 선택/등록 버튼 없이 입력칸만 둠
        self.manual_option = QLineEdit()
        self.manual_option.setFixedWidth(220)
        manual_option_row = self.manual_option

        # 수량: 스핀박스(위아래 화살표로 직접 증감) + 프리셋 드롭다운(자주 쓰는 수량 바로 선택)
        self.manual_qty_spin = QSpinBox()
        self.manual_qty_spin.setRange(1, 999999)
        self.manual_qty_spin.setValue(1)
        self.manual_qty_preset = QComboBox()
        self._reload_manual_qty_presets()
        self.manual_qty_preset.currentTextChanged.connect(self._apply_qty_preset)
        self.manual_qty_preset.setFixedWidth(110)
        self.manual_qty_spin.setFixedWidth(110)
        manual_qty_row = QWidget()
        manual_qty_row_layout = QHBoxLayout(manual_qty_row)
        manual_qty_row_layout.setContentsMargins(0, 0, 0, 0)
        manual_qty_row_layout.addWidget(self.manual_qty_preset)
        manual_qty_row_layout.addWidget(self.manual_qty_spin)
        manual_qty_row_layout.addStretch()

        self.manual_price = QLineEdit("0")
        self.manual_price.setFixedWidth(150)
        self.manual_buyer = QLineEdit()
        self.manual_buyer.setFixedWidth(180)
        self.manual_status = QComboBox()
        self._reload_status_presets()
        manual_status_row = QWidget()
        manual_status_row_layout = QHBoxLayout(manual_status_row)
        manual_status_row_layout.setContentsMargins(0, 0, 0, 0)
        manual_status_row_layout.addWidget(self.manual_status)
        status_setting_btn = QPushButton("⚙️ 주문상태 설정")
        status_setting_btn.setToolTip("주문상태 목록을 직접 추가·삭제할 수 있어요")
        status_setting_btn.clicked.connect(self.open_status_settings)
        manual_status_row_layout.addWidget(status_setting_btn)
        manual_status_row_layout.addStretch()
        self.manual_status.setCurrentText("미결재")

        self.manual_total = QLineEdit()
        self.manual_total.setPlaceholderText("비워두면 수량×판매단가로 자동 계산")
        self.manual_total.setFixedWidth(260)
        self.manual_fee = QLineEdit("0")
        self.manual_fee.setFixedWidth(150)

        # 배송비: 단가 × 건수로 계산 (여러 건 배송 시 편하게)
        self.manual_shipping = QLineEdit("0")
        self.manual_shipping.setFixedWidth(120)
        self.manual_shipping_qty = QSpinBox()
        self.manual_shipping_qty.setRange(1, 999)
        self.manual_shipping_qty.setValue(1)
        self.manual_shipping_qty.setFixedWidth(70)
        self.manual_shipping_total = QLabel("합계 0원")
        self.manual_shipping_total.setStyleSheet("color: #1A5276; font-weight: bold;")
        self.manual_shipping.textChanged.connect(self._update_shipping_total)
        self.manual_shipping_qty.valueChanged.connect(self._update_shipping_total)

        manual_shipping_row = QWidget()
        manual_shipping_row_layout = QHBoxLayout(manual_shipping_row)
        manual_shipping_row_layout.setContentsMargins(0, 0, 0, 0)
        manual_shipping_row_layout.addWidget(self.manual_shipping)
        manual_shipping_row_layout.addWidget(QLabel("×"))
        manual_shipping_row_layout.addWidget(self.manual_shipping_qty)
        manual_shipping_row_layout.addWidget(QLabel("건"))
        for amount in (1000, 3000, 5000):
            btn = QPushButton(f"+{amount:,}")
            btn.setFixedWidth(64)
            btn.clicked.connect(lambda checked=False, a=amount: self.add_shipping_amount(a))
            manual_shipping_row_layout.addWidget(btn)
        manual_shipping_row_layout.addWidget(self.manual_shipping_total)
        manual_shipping_row_layout.addStretch()

        self.manual_settlement = QLineEdit()
        self.manual_settlement.setPlaceholderText("비워두면 매출금액-수수료+배송비로 자동 계산")
        self.manual_settlement.setFixedWidth(260)
        self.manual_memo = QLineEdit()
        self.manual_memo.setFixedWidth(400)

        # 왼쪽 2열은 기본 입력, 오른쪽 1열은 예전 "고급 설정"에 있던 항목들
        # (접었다 펴는 방식이 화면을 뭉개서, 한 화면에 나란히 두도록 바꿈)
        left_fields = [
            ("거래처 *", manual_channel_row), ("주문일", self.manual_date),
            ("상품명 *", manual_product_row), ("옵션명", manual_option_row),
            ("수량", manual_qty_row), ("판매단가", self.manual_price),
            ("구매자명", self.manual_buyer), ("주문상태", manual_status_row),
        ]
        for i, (label_text, widget) in enumerate(left_fields):
            row, col_pair = divmod(i, 2)
            basic_grid.addWidget(QLabel(label_text), row, col_pair * 2)
            basic_grid.addWidget(widget, row, col_pair * 2 + 1)

        right_fields = [
            ("매출금액", self.manual_total), ("수수료", self.manual_fee),
            ("배송비", manual_shipping_row), ("정산금액", self.manual_settlement),
            ("메모", self.manual_memo),
        ]
        for i, (label_text, widget) in enumerate(right_fields):
            lab = QLabel(label_text)
            lab.setStyleSheet("color: #1A5276;")
            basic_grid.addWidget(lab, i, 4)
            basic_grid.addWidget(widget, i, 5)

        basic_grid.setHorizontalSpacing(10)
        basic_grid.setVerticalSpacing(8)
        for col in range(6):
            basic_grid.setColumnStretch(col, 0)
        basic_grid.setColumnStretch(6, 1)   # 맨 오른쪽 빈 열이 남는 공간 흡수
        manual_outer_v.addLayout(basic_grid)


        # 등록과 동시에 서류를 뽑을지 선택 (기본은 꺼둠)
        # 복수 담기 목록 표시 (담긴 게 있을 때만 보임)
        cart_row = QHBoxLayout()
        self.multi_cart_label = QLabel("")
        self.multi_cart_label.setStyleSheet(
            "background:#FEF9E7; border:1px solid #F7DC6F; border-radius:5px;"
            "padding:6px 10px; color:#7D6608; font-weight:bold;")
        self.multi_cart_label.setVisible(False)
        cart_row.addWidget(self.multi_cart_label, stretch=1)
        cart_clear_btn = QPushButton("✖ 담기 비우기")
        cart_clear_btn.clicked.connect(self.clear_multi_cart)
        cart_row.addWidget(cart_clear_btn)
        manual_outer_v.addLayout(cart_row)
        self._multi_cart = []

        doc_row = QHBoxLayout()
        self.doc_statement_cb = QCheckBox("📄 거래명세표 출력")
        self.doc_statement_cb.setChecked(_qsettings.value("doc/statement", "false") == "true")
        self.doc_statement_cb.stateChanged.connect(
            lambda s: _qsettings.setValue("doc/statement", "true" if s else "false"))
        self.doc_statement_cb.setChecked(conv_on("doc_statement", False))
        self.doc_statement_cb.setToolTip("주문 등록과 함께 거래명세표를 저장합니다")
        doc_row.addWidget(self.doc_statement_cb)
        self.doc_statement_format = QComboBox()
        self.doc_statement_format.addItem("엑셀(.xlsx)", "excel")
        self.doc_statement_format.addItem("그림(.png)", "image")
        self.doc_statement_format.addItem("둘 다(엑셀+그림)", "both")
        self.doc_statement_format.setFixedWidth(150)
        self.doc_statement_format.setFixedWidth(130)
        doc_row.addWidget(self.doc_statement_format)
        self.doc_invoice_cb = QCheckBox("🚚 송장요청서 출력")
        self.doc_invoice_cb.setChecked(_qsettings.value("doc/invoice", "false") == "true")
        self.doc_invoice_cb.stateChanged.connect(
            lambda s: _qsettings.setValue("doc/invoice", "true" if s else "false"))
        self.doc_invoice_cb.setChecked(conv_on("doc_invoice", False))
        self.doc_invoice_cb.setToolTip("택배사에 올릴 송장요청서를 엑셀로 저장합니다")
        doc_row.addWidget(self.doc_invoice_cb)
        doc_row.addStretch()

        manual_outer_v.addLayout(doc_row)

        self.manual_save_btn = QPushButton("➕ 주문 등록")
        self.manual_save_btn.clicked.connect(self.save_manual_order)
        self.manual_cancel_btn = QPushButton("✖ 수정 취소")
        self.manual_cancel_btn.clicked.connect(self.cancel_order_edit)
        self.manual_cancel_btn.setVisible(False)
        save_row = QHBoxLayout()
        save_row.addWidget(self.manual_save_btn, stretch=1)
        save_row.addWidget(self.manual_cancel_btn)
        manual_outer_v.addLayout(save_row)

        manual_outer.addWidget(self.manual_content)
        self.manual_content.setVisible(True)
        manual_box.toggled.connect(self.manual_content.setVisible)
        layout.addWidget(manual_box)

        # 필터 영역
        filter_box = QGroupBox("조회 필터")
        filter_layout = QHBoxLayout(filter_box)
        filter_layout.setSpacing(15)

        self.filter_channel = QComboBox()
        self.filter_channel.addItem("전체", None)
        filter_layout.addWidget(tight_pair("채널:", self.filter_channel))

        self.date_from = make_date_edit()
        self.date_from.setDate(QDate.currentDate().addDays(-6))  # 기본 최근 7일
        filter_layout.addWidget(tight_pair("시작일:", self.date_from))

        self.date_to = make_date_edit()
        self.date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(tight_pair("종료일:", self.date_to))

        self.buyer_search_input = QLineEdit()
        self.buyer_search_input.setPlaceholderText("이름 / 전화번호(뒷 4자리도 OK)")
        self.buyer_search_input.setFixedWidth(200)
        # 엔터를 누르면 바로 조회 (조회 버튼과 동일하게 동작 - 파일별 보기도 해제)
        self.buyer_search_input.returnPressed.connect(self.clear_upload_filter)
        self.buyer_search_input.setToolTip(
            "이름 또는 전화번호로 검색합니다 (엔터로 바로 조회).\n"
            "검색어를 넣으면 날짜 범위와 상관없이 전체 기간에서 찾습니다.")
        self.buyer_search_input.textEdited.connect(self._auto_hyphen_search)
        filter_layout.addWidget(tight_pair("구매자 검색:", self.buyer_search_input))

        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.clear_upload_filter)
        filter_layout.addWidget(search_btn)

        today_btn = QPushButton("오늘")
        today_btn.clicked.connect(lambda: self._set_order_period(0))
        filter_layout.addWidget(today_btn)
        week_btn = QPushButton("최근 7일")
        week_btn.clicked.connect(lambda: self._set_order_period(6))
        filter_layout.addWidget(week_btn)

        reset_filter_btn = QPushButton("🔄 필터 초기화")
        reset_filter_btn.clicked.connect(self.reset_filters)
        filter_layout.addWidget(reset_filter_btn)

        clear_btn = QPushButton("전체 주문 삭제")
        clear_btn.setStyleSheet("color: red;")
        clear_btn.clicked.connect(self.clear_all)
        filter_layout.addWidget(clear_btn)


        filter_layout.addStretch()

        layout.addWidget(filter_box)

        # 선택 항목 관리 (체크박스로 수정/삭제)
        order_action_box = QGroupBox("선택 항목 관리 (표 왼쪽 체크박스로 선택 - 파일업로드/수동입력 모두 가능)")
        order_action_layout = QHBoxLayout(order_action_box)
        order_edit_btn = QPushButton("✏️ 수정")
        order_edit_btn.clicked.connect(self.edit_checked_order)
        order_action_layout.addWidget(order_edit_btn)
        order_delete_btn = QPushButton("🗑️ 삭제")
        order_delete_btn.setStyleSheet("color: red;")
        order_delete_btn.clicked.connect(self.delete_checked_orders)
        order_action_layout.addWidget(order_delete_btn)
        order_reassign_btn = QPushButton("🔀 채널 일괄변경")
        order_reassign_btn.clicked.connect(self.reassign_checked_orders_channel)
        order_action_layout.addWidget(order_reassign_btn)
        order_check_all_btn = QPushButton("전체 선택")
        order_check_all_btn.clicked.connect(lambda: self.set_all_order_checked(True))
        order_action_layout.addWidget(order_check_all_btn)
        order_uncheck_all_btn = QPushButton("전체 해제")
        order_uncheck_all_btn.clicked.connect(lambda: self.set_all_order_checked(False))
        order_action_layout.addWidget(order_uncheck_all_btn)
        order_action_layout.addStretch()
        layout.addWidget(order_action_box)

        # 테이블
        self.order_count_label = QLabel("")
        self.order_count_label.setStyleSheet(
            "padding: 6px; background: #EAF2F8; border-radius: 6px; font-weight: bold;")
        layout.addWidget(self.order_count_label)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_order_double_clicked)
        enable_persistent_column_widths(self.table, "orders")
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh, exclude_columns=(0,))
        layout.addWidget(self.table)

        self.reload_channels(for_filter=True)
        self.refresh_upload_history()
        self.refresh()

    def pick_multi_products(self):
        """복수 주문 담기 - 담긴 목록은 [주문 등록] 누를 때 함께 저장됨"""
        ch_id = self.manual_channel.currentData()
        if not ch_id:
            QMessageBox.warning(self, "알림", "거래처를 먼저 선택해주세요.")
            return
        dialog = MultiOrderDialog(
            ch_id,
            self.manual_date.date().toString("yyyy-MM-dd"),
            self.manual_buyer.text().strip(),
            self.manual_status.currentText(),
            self)
        if dialog.exec() == QDialog.Accepted and dialog._cart:
            self._multi_cart = list(dialog._cart)
            self._update_multi_cart_label()

    def _update_multi_cart_label(self):
        """담긴 품목을 폼에 표시"""
        cart = getattr(self, "_multi_cart", [])
        if not cart:
            self.multi_cart_label.setVisible(False)
            return
        total = sum(it["qty"] * it["price"] for it in cart)
        names = ", ".join(f"{it['name']}({it['qty']}개)" for it in cart[:3])
        more = f" 외 {len(cart)-3}건" if len(cart) > 3 else ""
        self.multi_cart_label.setText(
            f"📦 담긴 품목 {len(cart)}개 · 합계 {total:,}원   |   {names}{more}"
            "    ← 아래 [주문 등록]을 누르면 함께 저장됩니다")
        self.multi_cart_label.setVisible(True)

    def clear_multi_cart(self):
        self._multi_cart = []
        self._update_multi_cart_label()

    def pick_product(self):
        # 일반거래처 주문이면 그 거래처에서 매출이 높았던 상품부터 보여줌
        channel_id = self.manual_channel.currentData()
        channel = next((ch for ch in db.get_channels() if ch["id"] == channel_id), None)
        is_offline = channel is not None and (channel["channel_type"] or "온라인채널") != "온라인채널"
        if is_offline:
            dialog = ProductPickerDialog(self, recent_source="sales", sales_channel_id=channel_id)
        else:
            dialog = ProductPickerDialog(self, recent_source="sales",
                                      sales_channel_id=self.manual_channel.currentData())
        if dialog.exec() == QDialog.Accepted and dialog.selected_product:
            p = dialog.selected_product
            self.manual_product.setText(p["name"])
            self.manual_option.setText(p["option_name"] or "")
            self._fill_last_sale_price()

    def _fill_last_sale_price(self):
        """업체(채널) + 상품이 정해지면 그 조합으로 마지막에 판매했던 단가를 채워줌.
        이력이 없으면 직전에 입력했던 값 -> 품목 판매가 순으로 대체"""
        if not hasattr(self, "manual_price"):
            return
        channel_id = self.manual_channel.currentData()
        product_name = self.manual_product.text().strip()
        option_name = self.manual_option.text().strip()
        if not product_name:
            return
        last_price = db.get_last_sale_price(channel_id, product_name, option_name)
        if last_price:
            self.manual_price.setText(str(last_price))
            return
        fallback = getattr(self, "_last_manual_price", 0)
        if fallback:
            self.manual_price.setText(str(fallback))
            return
        product = next((p for p in db.get_products()
                        if p["name"] == product_name and (p["option_name"] or "") == option_name), None)
        if product:
            self.manual_price.setText(str(product["sale_price"] or 0))

    def quick_add_product(self):
        dialog = QuickAddProductDialog(self, default_name=self.manual_product.text().strip())
        if dialog.exec() == QDialog.Accepted and getattr(dialog, "new_product", None):
            p = dialog.new_product
            self.manual_product.setText(p["name"])
            self.manual_price.setText(str(p["sale_price"] or 0))
            QMessageBox.information(self, "완료", f"'{p['name']}' 상품이 등록되었습니다.")

    def pick_option(self):
        dialog = OptionPickerDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_option:
            self.manual_option.setText(dialog.selected_option)

    def quick_add_option(self):
        dialog = QuickAddOptionDialog(self, default_label=self.manual_option.text().strip())
        if dialog.exec() == QDialog.Accepted and dialog.new_option:
            self.manual_option.setText(dialog.new_option)

    def _update_shipping_total(self):
        total = to_int(self.manual_shipping.text(), 0) * self.manual_shipping_qty.value()
        self.manual_shipping_total.setText(f"합계 {total:,}원")

    def add_shipping_amount(self, amount):
        current = self.manual_shipping.text().strip().replace(",", "")
        current_val = int(current) if current.lstrip("-").isdigit() else 0
        self.manual_shipping.setText(str(current_val + amount))

    def delete_selected_channel(self):
        cid = self.channel_combo.currentData()
        name = self.channel_combo.currentText()
        if cid is None:
            QMessageBox.warning(self, "알림", "삭제할 채널을 선택해주세요.")
            return
        order_count = db.get_channel_order_count(cid)
        detail = "채널을 삭제해도 주문 데이터 자체는 남지만, 채널 정보(수수료율·정산통장 설정 포함)는 사라집니다."
        warn = (f"이 채널과 연결된 주문이 {order_count:,}건 있습니다." if order_count else "")
        if confirm_delete(self, f"'{name}' 채널", detail, extra_warning=warn,
                          double_check=bool(order_count)):
            db.delete_channel(cid)
            self.reload_channels()
            QMessageBox.information(self, "완료", f"'{name}' 채널이 삭제되었습니다.")

    def _reload_status_presets(self):
        """주문상태 목록을 불러옴 (기본: 외상 / 결재완료, 설정에서 바꿀 수 있음)"""
        saved = _qsettings.value("order/status_list")
        items = [s for s in (saved.split("|") if isinstance(saved, str) and saved else []) if s]
        if not items:
            items = ["외상", "결재완료"]
        current = self.manual_status.currentText()
        self.manual_status.blockSignals(True)
        self.manual_status.clear()
        self.manual_status.addItems(items)
        idx = self.manual_status.findText(current)
        if idx >= 0:
            self.manual_status.setCurrentIndex(idx)
        self.manual_status.blockSignals(False)

    def open_status_settings(self):
        dialog = OrderStatusSettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self._reload_status_presets()

    def pick_manual_channel(self):
        # 수동 주문등록은 일반거래처 대상이므로 거래처만 고를 수 있게 함
        dialog = SupplierPickerDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_supplier:
            self.reload_channels()
            idx = self.manual_channel.findData(dialog.selected_supplier["id"])
            if idx >= 0:
                self.manual_channel.setCurrentIndex(idx)

    def add_new_channel(self):
        """업로드용 채널 추가 - 판매채널 탭으로 바로"""
        dialog = NewChannelDialog(self)
        dialog.stack.setCurrentIndex(1)
        if dialog.exec() != QDialog.Accepted or not dialog.result_channel_id:
            return
        self.reload_channels()
        idx = self.channel_combo.findData(dialog.result_channel_id)
        if idx >= 0:
            self.channel_combo.setCurrentIndex(idx)
        QMessageBox.information(self, "완료", "채널이 등록되었습니다.")

    def add_new_supplier(self):
        """수동주문등록의 거래처 추가 - 일반거래처 탭으로 바로"""
        dialog = NewChannelDialog(self)
        dialog.stack.setCurrentIndex(2)   # 일반거래처 탭
        if dialog.exec() != QDialog.Accepted or not dialog.result_channel_id:
            return
        self.reload_channels()
        idx = self.manual_channel.findData(dialog.result_channel_id)
        if idx >= 0:
            self.manual_channel.setCurrentIndex(idx)
        QMessageBox.information(self, "완료", "거래처가 등록되었습니다.")

    def reload_channels(self, for_filter=False):
        channels = db.get_channels()
        online_channels = [c for c in channels if (c["channel_type"] or "온라인채널") == "온라인채널"]

        # 업로드용 채널 콤보: 현재 선택을 유지하고, 최초 로딩(아직 아무것도 선택된 적 없을 때)에만
        # "스마트스토어"를 기본값으로 함 (매번 새로고침될 때마다 선택이 초기화되던 문제 방지)
        current_channel_id = self.channel_combo.currentData()
        self.channel_combo.clear()
        self.channel_combo.addItem("", None)   # 기본은 빈칸 (파일명으로 자동 인식되므로)
        for ch in online_channels:
            self.channel_combo.addItem(ch["name"], ch["id"])
        if current_channel_id is not None:
            idx = self.channel_combo.findData(current_channel_id)
            self.channel_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.channel_combo.setCurrentIndex(0)

        if hasattr(self, "filter_channel"):
            current_filter_id = self.filter_channel.currentData()
            self.filter_channel.clear()
            self.filter_channel.addItem("전체", None)
            for ch in channels:
                self.filter_channel.addItem(ch["name"], ch["id"])
            idx = self.filter_channel.findData(current_filter_id)
            if idx >= 0:
                self.filter_channel.setCurrentIndex(idx)

        if hasattr(self, "manual_channel"):
            # 수동 주문등록은 원래 일반거래처만 대상이었으나,
            # 주문 리스트에서 '수정'을 누르면 온라인 채널 주문도 이 폼으로 불러오기 때문에
            # 채널이 목록에 없으면 저장할 때 채널이 지워지는 문제가 있었음.
            # -> 설정(주문관리 설정 > 수동 주문등록에 온라인 판매채널도 표시)으로 켜고 끌 수 있게 함.
            #    (기본 켜짐. 꺼도 '수정' 중인 주문의 채널은 항상 목록에 넣어줌)
            current_manual_id = self.manual_channel.currentData()
            self.manual_channel.clear()
            self.manual_channel.addItem("", None)   # 기본은 빈칸
            # 매출이 많은 거래처가 위에 오도록 정렬 (같으면 가나다순)
            for s in db.get_suppliers_by_sales():
                self.manual_channel.addItem(s["name"], s["id"])
            if conv_on("manual_show_channels", True):
                supplier_ids = {s["id"] for s in db.get_suppliers_by_sales()}
                first = True
                for ch in channels:
                    if ch["id"] in supplier_ids:
                        continue
                    if (ch["channel_type"] or "온라인채널") != "온라인채널":
                        continue
                    if first:
                        self.manual_channel.insertSeparator(self.manual_channel.count())
                        first = False
                    self.manual_channel.addItem(f"[채널] {ch['name']}", ch["id"])
            if current_manual_id is not None:
                idx = self.manual_channel.findData(current_manual_id)
                self.manual_channel.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                self.manual_channel.setCurrentIndex(0)

    def _set_history_period(self, days):
        """업로드 목록 조회 기간 바로가기 (최근7일 / 지난주 / 이번달)"""
        today = QDate.currentDate()
        if days > 0:                       # 최근 7일
            self.history_date_from.setDate(today.addDays(-(days - 1)))
            self.history_date_to.setDate(today)
        elif days == 0:                    # 이번달
            self.history_date_from.setDate(QDate(today.year(), today.month(), 1))
            self.history_date_to.setDate(today)
        else:                              # 지난주 (월~일)
            this_monday = today.addDays(-(today.dayOfWeek() - 1))
            last_monday = this_monday.addDays(-7)
            self.history_date_from.setDate(last_monday)
            self.history_date_to.setDate(last_monday.addDays(6))
        self.refresh_upload_history()

    def delete_upload_history(self):
        row = self.upload_history_table.currentRow()
        if row < 0 or row >= len(getattr(self, "_upload_ids", [])):
            QMessageBox.warning(self, "알림", "삭제할 업로드 기록을 표에서 선택해주세요.")
            return
        upload_id = self._upload_ids[row]
        filename = self.upload_history_table.item(row, 0).text()
        linked = len(db.get_orders_by_upload(upload_id))

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("⚠️ 업로드 내역 삭제")
        box.setText(f"<b style='font-size:15px; color:#C0392B;'>'{filename}' 업로드 내역</b>"
                    f"<br>이 파일로 등록된 주문: <b>{linked:,}건</b>")
        box.setInformativeText(
            "⚠️ 이 작업은 <b>되돌릴 수 없습니다.</b><br><br>"
            "· <b>[업로드 내역 + 주문 삭제]</b> 주문까지 모두 지웁니다 "
            "(차감됐던 재고는 복원됩니다)<br>"
            "· <b>[업로드 내역만 삭제]</b> 주문은 남기고 업로드 내역만 지웁니다<br><br>"
            "걱정되면 먼저 <b>설정 &gt; 데이터 백업하기</b>로 백업해두세요.")
        del_all = box.addButton("업로드 내역 + 주문 삭제", QMessageBox.DestructiveRole)
        del_hist = box.addButton("업로드 내역만 삭제", QMessageBox.AcceptRole)
        cancel_btn = box.addButton("취소", QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.setEscapeButton(cancel_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (del_all, del_hist):
            return

        delete_orders = (clicked is del_all)
        if delete_orders and linked:
            if not confirm_delete(
                    self, f"주문 {linked:,}건 + 업로드 내역",
                    "삭제된 주문은 복구할 수 없고, 매출·이익 집계에서도 모두 빠집니다.",
                    extra_warning="주문 데이터까지 통째로 지웁니다.",
                    title="🛑 마지막 확인"):
                return
        try:
            total, deleted = db.delete_upload_history(upload_id, delete_orders=delete_orders)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 중 오류가 발생했습니다:\n{e}")
            return
        self._filter_upload_id = None
        self.refresh_upload_history()
        self.refresh()
        notify_data_changed()
        QMessageBox.information(
            self, "완료",
            f"업로드 기록을 삭제했습니다." +
            (f"\n주문 {deleted}건도 함께 삭제했습니다 (재고 복원됨)." if delete_orders
             else f"\n연결됐던 주문 {total}건은 그대로 남아있습니다."))

    def on_upload_history_double_clicked(self, row, column):
        """업로드 파일을 더블클릭하면 그 파일로 등록된 주문만 하단 목록에 표시"""
        if row < 0 or row >= len(getattr(self, "_upload_ids", [])):
            return
        upload_id = self._upload_ids[row]
        self._filter_upload_id = upload_id
        orders = db.get_orders_by_upload(upload_id)
        if not orders:
            QMessageBox.information(
                self, "알림",
                "이 파일로 등록된 주문을 찾지 못했습니다.\n"
                "(이 기능이 생기기 전에 업로드한 파일은 주문과 연결 정보가 없어요.\n"
                " 그 경우 아래 조회필터의 기간·채널로 찾아주세요)")
            self._filter_upload_id = None
            return
        self.refresh()

    def refresh_upload_history(self):
        date_from = self.history_date_from.date().toString("yyyy-MM-dd")
        date_to = self.history_date_to.date().toString("yyyy-MM-dd")
        history = db.get_upload_history(date_from=date_from, date_to=date_to)
        self._upload_ids = [h["id"] for h in history]
        headers = ["파일명", "채널", "업로드 일시", "가져온 건수"]
        rows = [
            (h["filename"], h["channel_name"], h["uploaded_at"], f"{h['row_count']:,}건")
            for h in history
        ]
        fill_table(self.upload_history_table, headers, rows, persist_key="upload_history",
                   sort_state=self._upload_history_sort_state)
        total_rows = sum(h["row_count"] or 0 for h in history)
        self.upload_count_label.setText(
            f"📄 {date_from} ~ {date_to}   |   업로드 {len(history)}건   |   가져온 주문 {total_rows:,}건")

    def _reload_manual_qty_presets(self):
        """수량 목록을 DB에서 다시 읽어옴 (사용자가 직접 설정한 목록)"""
        self.manual_qty_preset.blockSignals(True)
        self.manual_qty_preset.clear()
        for q in db.get_qty_presets("order"):
            self.manual_qty_preset.addItem(f"{q:,}")
        self.manual_qty_preset.addItem("✏️ 수량목록 직접설정")
        self.manual_qty_preset.blockSignals(False)

    def _apply_qty_preset(self, text):
        if "직접설정" in text:
            dialog = QtyPresetEditDialog("order", self)
            if dialog.exec() == QDialog.Accepted:
                self._reload_manual_qty_presets()
            else:
                self.manual_qty_preset.setCurrentIndex(0)
            return
        digits = text.replace(",", "").strip()
        if digits.isdigit():
            self.manual_qty_spin.setValue(int(digits))

    def save_manual_order(self):
        def to_int(s, default=0):
            s = (s or "").strip().replace(",", "")
            if s.lstrip("-").isdigit():
                return int(s)
            return default

        product_name = self.manual_product.text().strip()
        channel_id = self.manual_channel.currentData()
        has_cart = bool(getattr(self, "_multi_cart", []))
        if not product_name and not has_cart:
            QMessageBox.warning(self, "알림", "상품명은 필수입니다.")
            return
        if channel_id is None:
            QMessageBox.warning(self, "알림", "판매 채널을 등록/선택해주세요.")
            return

        qty = self.manual_qty_spin.value()
        sale_price = to_int(self.manual_price.text(), 0)
        # 담긴 품목만 등록하는 경우엔 단일 상품 검증을 건너뜀
        if product_name:
            if qty <= 0:
                QMessageBox.warning(self, "알림", "수량을 입력해주세요.")
                return
            if sale_price <= 0:
                QMessageBox.warning(self, "알림", "판매단가를 입력해주세요.")
                return

        total_text = self.manual_total.text().strip()
        total_amount = to_int(total_text) if total_text else qty * sale_price

        fee_amount = to_int(self.manual_fee.text(), 0)
        # 배송비 = 단가 × 건수
        shipping_fee = to_int(self.manual_shipping.text(), 0) * self.manual_shipping_qty.value()

        settlement_text = self.manual_settlement.text().strip()
        settlement_amount = (
            to_int(settlement_text) if settlement_text
            else total_amount - fee_amount + shipping_fee
        )

        order_no = f"MANUAL-{int(datetime.now().timestamp())}"
        order_date_str = self.manual_date.date().toString("yyyy-MM-dd")
        status_text = self.manual_status.currentText()

        # 일반거래처 주문인데 구매자명이 비어있으면 거래처명으로 채움
        # (그래야 조회필터의 구매자 검색으로 찾을 수 있음)
        buyer_name = self.manual_buyer.text().strip()
        if not buyer_name:
            channel = next((ch for ch in db.get_channels() if ch["id"] == channel_id), None)
            if channel and (channel["channel_type"] or "온라인채널") == "일반업체":
                buyer_name = channel["name"]

        option_text = self.manual_option.text().strip()

        # 복수로 담아둔 품목들을 먼저 등록 (배송비는 첫 건에만 붙임)
        cart = getattr(self, "_multi_cart", [])
        cart_saved = 0
        if cart:
            import time as _ct
            for i, it in enumerate(cart):
                amt = it["qty"] * it["price"]
                ship = shipping_fee if (i == 0 and not product_name) else 0
                try:
                    db.add_order({
                        "channel_id": channel_id,
                        "order_no": f"MANUAL-{int(_ct.time()*1000)+i}",
                        "order_date": order_date_str,
                        "product_name": it["name"],
                        "option_name": it["option_name"],
                        "qty": it["qty"], "sale_price": it["price"],
                        "total_amount": amt, "fee_amount": 0,
                        "shipping_fee": ship,
                        "settlement_amount": amt + ship,
                        "buyer_name": buyer_name, "status": status_text,
                        "memo": self.manual_memo.text().strip(),
                    })
                    cart_saved += 1
                except Exception:
                    pass

        # 수정 모드면 새로 만들지 않고 기존 주문을 고침
        if getattr(self, "editing_order_id", None):
            old = db.get_order_by_id(self.editing_order_id)
            db.update_order(self.editing_order_id, {
                "channel_id": channel_id, "order_date": order_date_str,
                "order_no": old["order_no"] if old else order_no,
                "product_name": product_name, "option_name": option_text,
                "qty": qty, "sale_price": sale_price, "total_amount": total_amount,
                "fee_amount": fee_amount, "shipping_fee": shipping_fee,
                "settlement_amount": settlement_amount, "buyer_name": buyer_name,
                "status": status_text, "memo": self.manual_memo.text().strip(),
            })
            matching.rematch_all_orders()
            self.cancel_order_edit()
            # 수정할 때 임시로 넣었던 [채널] 항목을 걷어내고 거래처 목록을 새로 채움
            # (이걸 안 하면 수동 주문 등록 폼이 수정 직전 상태로 남아 있음)
            try:
                self.reload_channels()
            except Exception:
                pass
            self._clear_manual_form()
            self.refresh()
            notify_data_changed()
            show_save_toast(self)
            QMessageBox.information(self, "완료", "주문을 수정했습니다.")
            return

        if product_name:
            db.add_order({
                "channel_id": channel_id,
                "order_no": order_no,
                "order_date": order_date_str,
                "product_name": product_name,
                "option_name": option_text,
                "qty": qty,
                "sale_price": sale_price,
                "total_amount": total_amount,
                "fee_amount": fee_amount,
                "shipping_fee": shipping_fee,
                "settlement_amount": settlement_amount,
                "buyer_name": buyer_name,
                "status": status_text,
                "memo": self.manual_memo.text().strip(),
            })

        # 수동입력 전용: '결제완료' 선택 시 이미 입금된 것으로 보고 즉시 정산완료 처리
        # (미수금 현황에는 안 잡히게 됨). '미결재'면 그대로 미수금에 남음.
        if status_text == "결제완료" and product_name:
            new_order = db.get_order_by_order_no(order_no)
            if new_order:
                db.mark_orders_settled([(new_order["id"], settlement_amount, order_date_str)])
                db.add_settlement(channel_id, order_date_str, settlement_amount, "수동 결제완료 처리")

        matching.rematch_all_orders()
        notify_data_changed()

        # 입력창 정리 (판매채널은 요청대로 등록 후 비움)
        # 아래에서 입력창을 비우면 배송비 건수가 1로 되돌아가므로,
        # 거래명세표에 쓸 값을 지금 미리 확보해둠
        try:
            doc_shipping_qty = max(1, int(self.manual_shipping_qty.value()))
        except Exception:
            doc_shipping_qty = 1

        self._last_manual_price = sale_price   # 다음 입력 때 판매단가 기본값으로 사용
        self.manual_channel.setCurrentIndex(-1)
        self.manual_product.clear()
        self.manual_option.clear()
        self.manual_qty_spin.setValue(1)
        self.manual_qty_preset.setCurrentIndex(0)
        self.manual_shipping.setText("0")
        self.manual_shipping_qty.setValue(1)
        self.manual_price.setText(str(sale_price))
        self.manual_total.clear()
        self.manual_fee.setText("0")
        self.manual_shipping.setText("0")
        self.manual_shipping_qty.setValue(1)
        self.manual_settlement.clear()
        self.manual_buyer.clear()
        self.manual_memo.clear()

        # 방금 등록한 주문이 조회 기간 밖이면 목록에 안 보여서 "사라졌다"고 오해하게 됨
        # -> 필요한 만큼 조회 기간을 자동으로 넓혀서 바로 확인할 수 있게 함
        self._filter_upload_id = None
        order_qdate = QDate.fromString(order_date_str, "yyyy-MM-dd")
        if order_qdate.isValid():
            if order_qdate < self.date_from.date():
                self.date_from.setDate(order_qdate)
            if order_qdate > self.date_to.date():
                self.date_to.setDate(order_qdate)

        # 체크했으면 서류 출력 (입력칸을 비우기 전에 값을 미리 확보해둠)
        doc_option_name = option_text
        saved_docs = []
        try:
            if self.doc_statement_cb.isChecked():
                p = self._export_statement(channel_id, order_date_str, product_name,
                                            doc_option_name, qty, sale_price, total_amount,
                                            shipping_fee, shipping_qty=doc_shipping_qty)
                if p:
                    saved_docs.append(p)
            if self.doc_invoice_cb.isChecked():
                p = self._export_invoice(product_name, doc_option_name, qty)
                if p:
                    saved_docs.append(p)
        except Exception as e:
            QMessageBox.warning(self, "알림", f"서류를 저장하지 못했습니다:\n{e}")

        extra = ("\n\n저장된 서류:\n" + "\n".join(f"  · {p}" for p in saved_docs)) if saved_docs else ""
        if cart_saved:
            extra = f"\n\n📦 담긴 품목 {cart_saved}건도 함께 등록했습니다." + extra
            self.clear_multi_cart()
        show_save_toast(self)
        QMessageBox.information(
            self, "완료",
            f"주문이 등록되었습니다.\n\n주문일: {order_date_str}\n"
            f"(아래 목록에서 바로 확인하실 수 있어요){extra}")
        self.refresh()
        if self.on_data_changed:
            self.on_data_changed()

    def upload_file(self):
        """주문 파일 업로드 - 여러 파일을 한 번에 고를 수 있고, 채널을 따로 고르지
        않아도 파일명으로 자동 인식함. 처리 결과는 파일 순서대로 정리해서 보여줌"""
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "주문 파일 선택 (여러 개 선택 가능)", _last_dir("order"),
            "엑셀/CSV 파일 (*.xlsx *.xls *.csv)"
        )
        if not filepaths:
            return
        _remember_dir("order", filepaths[0])

        results = []      # (파일명, 상태아이콘, 설명)
        any_success = False
        imported_total = 0
        before_count = len(db.get_orders())
        for filepath in filepaths:
            filename = os.path.basename(filepath)
            ok, detail = self._import_one_file(filepath, filename, len(filepaths) > 1)
            results.append((filename, "✅" if ok else "⚠️", detail))
            any_success = any_success or ok
        imported_total = len(db.get_orders()) - before_count

        if any_success:
            try:
                matching.rematch_all_orders()
                notify_data_changed()
            except Exception as e:
                results.append(("(후속 처리)", "⚠️", f"매칭 중 오류: {e}"))

        self.refresh_upload_history()
        self.refresh()
        if self.on_data_changed:
            self.on_data_changed()

        # 삽입된 순서대로 결과 메시지 표시
        lines = [f"{i}. {icon} {name}\n     → {detail}"
                 for i, (name, icon, detail) in enumerate(results, start=1)]
        success_count = sum(1 for _, icon, _ in results if icon == "✅")
        msg = f"총 {len(filepaths)}개 파일 중 {success_count}개를 불러왔습니다.\n\n" + "\n".join(lines)

        # 등록 건수와 실제 목록에 보이는 건수가 맞는지 검증하고, 다르면 이유를 안내
        if imported_total:
            visible = self.table.rowCount()
            if visible < imported_total:
                msg += (
                    f"\n\n⚠️ 등록 {imported_total}건 중 목록에는 {visible}건만 보입니다.\n"
                    f"조회 필터 때문일 수 있어요:\n"
                    f"   · 기간: {self.date_from.date().toString('yyyy-MM-dd')} ~ "
                    f"{self.date_to.date().toString('yyyy-MM-dd')}\n"
                    f"   · 채널: {self.filter_channel.currentText()}\n"
                    f"   · 구매자 검색: {self.buyer_search_input.text() or '(없음)'}\n\n"
                    "'🔄 필터 초기화'를 누르거나 기간을 넓혀서 다시 조회해보세요."
                )
        QMessageBox.information(self, "업로드 결과", msg)

    def _import_one_file(self, filepath, filename, batch_mode):
        """파일 1개를 읽어서 주문으로 저장. 반환: (성공여부, 설명문구)
        batch_mode=True(여러 파일 처리 중)면 파일마다 확인창을 띄우지 않고 자동 진행"""
        try:
            rows, mapping, unmatched, columns, _order_total, detected_channel = importer.parse_order_file(filepath)
        except Exception as e:
            return False, f"파일을 읽지 못했습니다 ({e})"

        # 필수 필드가 매칭 안 되면 수동 매칭 다이얼로그 표시
        required = ["order_no", "product_name", "total_amount"]
        if any(f in unmatched for f in required):
            dialog = ColumnMappingDialog(columns, mapping, self)
            if dialog.exec() != QDialog.Accepted:
                return False, "컬럼 매칭을 취소했습니다"
            try:
                rows, mapping, unmatched, columns, _order_total, detected_channel = importer.parse_order_file(
                    filepath, manual_mapping=dialog.get_mapping())
            except Exception as e:
                return False, f"파일을 읽지 못했습니다 ({e})"

        if not rows:
            return False, "인식된 주문 데이터가 없습니다 (파일 형식 확인 필요)"

        # 채널 결정: 파일명으로 자동 인식된 채널을 우선 사용.
        # 인식이 안 되면 그때만 현재 선택된 채널을 쓰고, 그것도 없으면 사용자에게 물어봄
        channel_name = detected_channel
        if not channel_name:
            channel_name = self.channel_combo.currentText().strip()
            if not channel_name:
                names = [self.channel_combo.itemText(i) for i in range(self.channel_combo.count())]
                picked, ok = QInputDialog.getItem(
                    self, "채널 선택",
                    f"'{filename}' 은(는) 파일명으로 채널을 알 수 없습니다.\n어느 채널의 주문인가요?",
                    names, 0, False)
                if not ok:
                    return False, "채널을 선택하지 않아 건너뛰었습니다"
                channel_name = picked

        channel_id = db.get_channel_id_by_name(channel_name)
        if channel_id is None:
            return False, f"'{channel_name}' 채널을 찾을 수 없습니다"

        for r in rows:
            r["channel_id"] = channel_id

        # 업로드한 주문이 조회필터에 바로 보이도록 필터 범위를 자동으로 넓혀줌
        upload_dates = [r["order_date"][:10] for r in rows if r.get("order_date")]
        if upload_dates:
            min_qdate = QDate.fromString(min(upload_dates), "yyyy-MM-dd")
            max_qdate = QDate.fromString(max(upload_dates), "yyyy-MM-dd")
            if min_qdate.isValid() and min_qdate < self.date_from.date():
                self.date_from.setDate(min_qdate)
            if max_qdate.isValid() and max_qdate > self.date_to.date():
                self.date_to.setDate(max_qdate)
        self.filter_channel.setCurrentIndex(0)  # 전체
        self.buyer_search_input.clear()

        # 파일 안에 똑같은 주문이 여러 줄 들어있으면 먼저 확인받음
        # (소분 발송으로 일부러 나눈 것일 수도, 파일이 중복된 것일 수도 있어서)
        rows = self._check_duplicate_rows(rows)
        if rows is None:
            return False, "사용자가 업로드를 취소했습니다"

        # 이미 등록된 주문번호는 걸러내고 새 주문만 등록
        # (같은 파일을 다시 올려도 새로 추가된 건만 들어감)
        total_rows = len(rows)
        rows, skipped = db.filter_new_orders(rows)
        if not rows:
            return False, f"이미 등록된 주문뿐입니다 ({total_rows}건 모두 중복)"

        try:
            upload_id = db.add_upload_history_returning_id(filename, channel_id, len(rows))
            for r in rows:
                r["upload_id"] = upload_id   # 나중에 파일별로 주문을 다시 찾을 수 있게 연결
            db.bulk_add_orders(rows)
        except Exception as e:
            return False, f"주문 저장 중 오류 ({e})"

        if skipped:
            return True, f"{channel_name} · 새 주문 {len(rows)}건 등록 (중복 {skipped}건 제외)"
        return True, f"{channel_name} · {len(rows)}건 등록"

    def _auto_hyphen_search(self, text):
        """전화번호를 숫자만 입력해도 자동으로 하이픈을 넣어줌
        (이름이나 짧은 뒷자리 검색은 그대로 두어 검색에 지장이 없게 함)"""
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits or len(digits) != len(text.replace("-", "").replace(" ", "")):
            return  # 숫자가 아닌 글자가 섞였으면(이름 등) 건드리지 않음
        formatted = format_phone(digits)
        if formatted != text:
            self.buyer_search_input.blockSignals(True)
            self.buyer_search_input.setText(formatted)
            self.buyer_search_input.blockSignals(False)

    def open_orders_settings(self):
        """주문관리 설정 - 서류 자동출력 기본값"""
        dialog = QDialog(self)
        dialog.setWindowTitle("주문관리 설정")
        dialog.resize(460, 320)
        v = QVBoxLayout(dialog)
        t = QLabel("⚙️ 주문관리 설정")
        t.setStyleSheet("font-size: 15px; font-weight: bold;")
        v.addWidget(t)
        note = QLabel("💡 수동 주문등록에서 서류 출력 체크를 처음부터 켜둘지 정합니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        v.addWidget(note)
        cb1 = QCheckBox("거래명세표 출력을 기본으로 켜기")
        cb1.setChecked(self.doc_statement_cb.isChecked())
        v.addWidget(cb1)
        cb2 = QCheckBox("송장요청서 출력을 기본으로 켜기")
        cb2.setChecked(self.doc_invoice_cb.isChecked())
        v.addWidget(cb2)
        v.addStretch()
        row = QHBoxLayout()
        cb3 = QCheckBox("수동 주문등록 칸을 항상 펼쳐두기")
        cb3.setChecked(_qsettings.value("order/manual_expanded", "false") == "true")
        v.addWidget(cb3)
        cb4 = QCheckBox("수동 주문등록에 '복수선택' 버튼 표시")
        cb4.setChecked(_qsettings.value("order/multi_pick", "false") == "true")
        v.addWidget(cb4)
        cb5 = QCheckBox("수동 주문등록 거래처 칸에 온라인 판매채널도 함께 표시")
        cb5.setToolTip("주문 리스트에서 '수정'을 눌러 온라인 채널 주문을 고칠 때 "
                       "채널을 그대로 선택할 수 있게 합니다")
        cb5.setChecked(conv_on("manual_show_channels", True))
        v.addWidget(cb5)
        cb5_note = QLabel("    └ 켜면 거래처 목록 아래에 [채널] 표시로 함께 나옵니다. "
                          "꺼도 '수정' 중인 주문의 채널은 자동으로 표시됩니다.")
        cb5_note.setWordWrap(True)
        cb5_note.setStyleSheet("color:#888; font-size:11px;")
        v.addWidget(cb5_note)
        v.addStretch()
        ok = QPushButton("💾 저장")
        ok.clicked.connect(dialog.accept)
        row.addWidget(ok)
        cancel = QPushButton("취소")
        cancel.clicked.connect(dialog.reject)
        row.addWidget(cancel)
        v.addLayout(row)
        if dialog.exec() == QDialog.Accepted:
            self.doc_statement_cb.setChecked(cb1.isChecked())
            self.doc_invoice_cb.setChecked(cb2.isChecked())
            _qsettings.setValue("order/manual_expanded", "true" if cb3.isChecked() else "false")
            _qsettings.setValue("order/multi_pick", "true" if cb4.isChecked() else "false")
            _qsettings.setValue("conv/manual_show_channels",
                                "true" if cb5.isChecked() else "false")
            self.reload_channels()
            # 바로 반영
            self.manual_box.setChecked(cb3.isChecked())
            self.multi_pick_btn.setVisible(cb4.isChecked())

    def _set_order_period(self, days_back):
        """조회 기간 바로가기 (오늘 / 최근 7일)"""
        self._filter_upload_id = None
        self.date_from.setDate(QDate.currentDate().addDays(-days_back))
        self.date_to.setDate(QDate.currentDate())
        self.refresh()

    def clear_upload_filter(self):
        """업로드 파일별 보기를 해제하고 일반 조회로 돌아감"""
        self._filter_upload_id = None
        self.refresh()

    def reset_filters(self):
        self._filter_upload_id = None
        self.filter_channel.setCurrentIndex(0)  # 전체
        self.date_from.setDate(QDate.currentDate().addDays(-6))
        self.date_to.setDate(QDate.currentDate())
        self.buyer_search_input.clear()
        self.refresh()

    def refresh(self):
        channel_id = self.filter_channel.currentData()
        date_from_qdate = self.date_from.date()
        date_to_qdate = self.date_to.date()

        if date_to_qdate < date_from_qdate:
            QMessageBox.warning(
                self, "알림",
                f"종료일({date_to_qdate.toString('yyyy-MM-dd')})이 "
                f"시작일({date_from_qdate.toString('yyyy-MM-dd')})보다 빠릅니다.\n"
                "그래서 조회 결과가 비어있게 나와요. 날짜를 다시 확인해주시거나 "
                "'🔄 필터 초기화' 버튼을 눌러주세요."
            )

        date_from = date_from_qdate.toString("yyyy-MM-dd")
        date_to = date_to_qdate.toString("yyyy-MM-dd")
        buyer_search = self.buyer_search_input.text().strip()
        # 업로드 파일 목록에서 더블클릭한 경우엔 그 파일의 주문만 보여줌
        upload_filter = getattr(self, "_filter_upload_id", None)
        if upload_filter:
            orders = db.get_orders_by_upload(upload_filter)
        elif buyer_search:
            # 사람을 찾는 검색이므로 날짜 범위에 갇히지 않고 전체 기간에서 조회
            orders = db.get_orders(channel_id=channel_id, buyer_search=buyer_search)
        else:
            orders = db.get_orders(channel_id=channel_id, date_from=date_from, date_to=date_to)

        headers = ["선택", "채널", "주문번호", "주문일", "상품명", "옵션", "수량",
                   "판매단가", "결제금액", "수수료", "정산금액", "구매자", "상태", "정산상태"]

        display_rows = []
        for o in orders:
            display_rows.append((
                "", o["channel_name"], o["order_no"], o["order_date"], o["product_name"],
                o["option_name"], o["qty"], fmt_won(o["sale_price"]), fmt_won(o["total_amount"]),
                fmt_won(o["fee_amount"]), fmt_won(o["settlement_amount"]), o["buyer_name"], o["status"],
                "✅ 완료" if o["is_settled"] else "미정산",
            ))
        # 조회 결과와 전체 보유 건수를 함께 보여줌
        # (필터에 걸려 안 보이는 것을 "데이터가 사라졌다"고 오해하지 않도록)
        try:
            total_all = db.get_data_counts().get("주문", 0)
        except Exception:
            total_all = len(orders)
        total_amount = sum(o["total_amount"] or 0 for o in orders)
        if upload_filter:
            scope = "선택한 업로드 파일"
        elif buyer_search:
            scope = f"검색 '{buyer_search}' (전체 기간)"
        else:
            scope = f"{date_from} ~ {date_to}"
        hint = ""
        if not upload_filter and not buyer_search and total_all > len(orders):
            hint = f"   ← 전체 보관 {total_all:,}건 중 이 기간 것만 표시 (기간을 넓히면 더 보여요)"
        self.order_count_label.setText(
            f"📋 {scope}   |   {len(orders):,}건   |   합계 {fmt_won(total_amount)}{hint}")

        display_rows, orders = apply_table_sort(display_rows, orders, self._sort_state)
        self._order_ids = [o["id"] for o in orders]

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(orders))

        for r, values in enumerate(display_rows):
            checkbox_container, _ = make_checkbox_cell()
            self.table.setCellWidget(r, 0, checkbox_container)

            for c, val in enumerate(values):
                if c == 0:
                    continue
                text = str(val) if val is not None else ""
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if looks_numeric(text):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)

        header = self.table.horizontalHeader()
        header.blockSignals(True)
        self.table.resizeColumnsToContents()
        header.blockSignals(False)
        self.table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        restore_column_widths(self.table, "orders")

    def get_checked_order_ids(self):
        checked = []
        for r in range(self.table.rowCount()):
            if is_row_checked(self.table, r):
                checked.append(self._order_ids[r])
        return checked

    def set_all_order_checked(self, checked: bool):
        for r in range(self.table.rowCount()):
            set_row_checked(self.table, r, checked)

    def on_order_double_clicked(self, row, column):
        if column == 0 or row < 0 or row >= len(self._order_ids):
            return
        oid = self._order_ids[row]
        menu = QMenu(self)
        detail_action = menu.addAction("🔍 상세 보기")
        edit_action = menu.addAction("✏️ 수정")
        return_action = menu.addAction("↩️ 반품 처리")
        delete_action = menu.addAction("🗑️ 삭제")
        chosen = menu.exec(QCursor.pos())
        if chosen == return_action:
            self.process_return(oid)
        elif chosen == detail_action:
            order = next((o for o in db.get_orders() if o["id"] == oid), None)
            if order:
                OrderDetailDialog(order, self).exec()
        elif chosen == edit_action:
            self._open_edit_dialog(oid)
        elif chosen == delete_action:
            self._delete_orders([oid])

    def edit_checked_order(self):
        checked = self.get_checked_order_ids()
        if len(checked) != 1:
            QMessageBox.warning(self, "알림", "수정은 한 번에 한 건만 가능합니다.\n체크박스에서 1개만 선택해주세요.")
            return
        self._open_edit_dialog(checked[0])

    def _check_duplicate_rows(self, rows):
        """파일 안에서 완전히 똑같은 주문 줄을 찾아 사용자에게 확인받음.
        반환: 정리된 rows (취소하면 None)"""
        groups = {}
        for r in rows:
            key = (str(r.get("order_no") or ""), str(r.get("product_name") or ""),
                   str(r.get("option_name") or ""), int(r.get("qty") or 0),
                   int(r.get("total_amount") or 0))
            if not key[0]:
                continue
            groups.setdefault(key, []).append(r)

        dups = [{"key": k, "rows": v} for k, v in groups.items() if len(v) > 1]
        if not dups:
            return rows

        dialog = DuplicateOrderCheckDialog(dups, self)
        if dialog.exec() != QDialog.Accepted:
            return None

        dedupe = dialog.dedupe_keys()
        if not dedupe:
            return rows

        cleaned, seen = [], set()
        for r in rows:
            key = (str(r.get("order_no") or ""), str(r.get("product_name") or ""),
                   str(r.get("option_name") or ""), int(r.get("qty") or 0),
                   int(r.get("total_amount") or 0))
            if key in dedupe:
                if key in seen:
                    continue      # 같은 줄은 한 번만 남김
                seen.add(key)
            cleaned.append(r)
        return cleaned

    def _open_edit_dialog(self, order_id):
        """별도 창 대신 위쪽 '수동 주문 등록' 폼에 불러와서 수정하게 함"""
        order = db.get_order_by_id(order_id)
        if not order:
            return
        self.manual_box.setChecked(True)   # 폼이 접혀 있으면 펴줌
        self.editing_order_id = order_id

        def g(key):
            try:
                return order[key]
            except (IndexError, KeyError):
                return None

        # 온라인 채널 주문을 '수정'으로 불러온 경우, 그 채널이 콤보에 없으면
        # 저장할 때 채널이 지워져 버리므로 그 자리에서 목록에 넣어줌
        ch_id = g("channel_id")
        idx = self.manual_channel.findData(ch_id)
        if idx < 0 and ch_id:
            ch_name = g("channel_name")
            if not ch_name:
                try:
                    ch_name = next((c["name"] for c in db.get_channels() if c["id"] == ch_id), None)
                except Exception:
                    ch_name = None
            if ch_name:
                self.manual_channel.addItem(f"[채널] {ch_name}", ch_id)
                idx = self.manual_channel.findData(ch_id)
        self.manual_channel.setCurrentIndex(idx if idx >= 0 else 0)
        qd = QDate.fromString((g("order_date") or "")[:10], "yyyy-MM-dd")
        if qd.isValid():
            self.manual_date.setDate(qd)
        self.manual_product.setText(g("product_name") or "")
        self.manual_option.setText(g("option_name") or "")
        self.manual_qty_spin.setValue(int(g("qty") or 1))
        self.manual_price.setText(str(g("sale_price") or 0))
        self.manual_buyer.setText(g("buyer_name") or "")
        status_idx = self.manual_status.findText(g("status") or "")
        if status_idx >= 0:
            self.manual_status.setCurrentIndex(status_idx)
        self.manual_total.setText(str(g("total_amount") or 0))
        self.manual_fee.setText(str(g("fee_amount") or 0))
        self.manual_shipping.setText(str(g("shipping_fee") or 0))
        self.manual_shipping_qty.setValue(1)
        self.manual_settlement.setText(str(g("settlement_amount") or 0))
        self.manual_memo.setText(g("memo") or "")

        self.manual_save_btn.setText("💾 주문 수정")
        self.manual_cancel_btn.setVisible(True)
        self.manual_box.setTitle("✏️ 주문 수정 중 (아래에서 고친 뒤 '주문 수정'을 누르세요)")

    def cancel_order_edit(self):
        """수정 모드를 끝내고 등록 모드로 되돌림"""
        self.editing_order_id = None
        self.manual_save_btn.setText("➕ 주문 등록")
        self.manual_cancel_btn.setVisible(False)
        self.manual_box.setTitle("🧾 수동 주문 등록 (파일 없이 직접 입력)")
        try:
            self.reload_channels()   # 수정용으로 끼워넣었던 채널 항목 정리
        except Exception:
            pass
        self._clear_manual_form()

    def _clear_manual_form(self):
        self.manual_channel.setCurrentIndex(0)
        self.manual_product.clear()
        self.manual_option.clear()
        self.manual_qty_spin.setValue(1)
        self.manual_qty_preset.setCurrentIndex(0)
        self.manual_price.setText("0")
        self.manual_buyer.clear()
        self.manual_total.clear()
        self.manual_fee.setText("0")
        self.manual_shipping.setText("0")
        self.manual_shipping_qty.setValue(1)
        self.manual_settlement.clear()
        self.manual_memo.clear()

    def delete_checked_orders(self):
        checked = self.get_checked_order_ids()
        if not checked:
            QMessageBox.warning(self, "알림", "삭제할 주문을 체크박스에서 선택해주세요.")
            return
        self._delete_orders(checked)

    def _delete_orders(self, ids):
        if confirm_delete(
                self, f"주문 {len(ids):,}건",
                "삭제한 주문은 매출·이익·정산 집계에서 모두 빠집니다.",
                double_check=len(ids) >= 10):
            try:
                for oid in ids:
                    db.delete_order(oid)
            except Exception as e:
                QMessageBox.critical(self, "오류", f"삭제 중 오류가 발생했습니다:\n{e}")
            finally:
                self.refresh()
                if self.on_data_changed:
                    self.on_data_changed()
                notify_data_changed()

    def reassign_checked_orders_channel(self):
        checked = self.get_checked_order_ids()
        if not checked:
            QMessageBox.warning(self, "알림", "채널을 변경할 주문을 체크박스에서 선택해주세요.")
            return

        channels = db.get_channels()
        if not channels:
            return
        names = [c["name"] for c in channels]
        target_name, ok = QInputDialog.getItem(
            self, "채널 일괄변경", f"{len(checked)}건의 주문을 어느 채널로 변경할까요?",
            names, 0, False
        )
        if not ok:
            return
        target_id = next((c["id"] for c in channels if c["name"] == target_name), None)
        if target_id is None:
            return
        db.bulk_update_order_channel(checked, target_id)
        matching.rematch_all_orders()
        notify_data_changed()
        self.refresh()
        QMessageBox.information(self, "완료", f"{len(checked)}건의 채널을 '{target_name}'(으)로 변경했습니다.")

    def clear_all(self):
        if confirm_delete(
                self, "등록된 모든 주문 데이터",
                "지금까지 업로드·입력한 주문이 전부 사라지고, 매출·이익 집계도 모두 0이 됩니다.",
                extra_warning="주문 전체를 통째로 지웁니다.",
                double_check=True):
            db.delete_all_orders()
            self.refresh()
            if self.on_data_changed:
                self.on_data_changed()
            notify_data_changed()

    def backfill_contact_info(self):
        """예전에 올린 주문에 수취인·주소·연락처만 보완 (주문번호로 매칭, 중복 생성 없음)"""
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "받는분 정보를 읽어올 주문 파일 선택 (여러 개 가능)", _last_dir("order"),
            "엑셀/CSV 파일 (*.xlsx *.xls *.csv)")
        if not filepaths:
            return
        _remember_dir("order", filepaths[0])

        total_updated = 0
        results = []
        for filepath in filepaths:
            name = os.path.basename(filepath)
            try:
                rows, _, _, _, _ = importer.parse_order_file(filepath)
            except Exception as e:
                results.append(f"⚠️ {name} → 읽기 실패 ({e})")
                continue
            try:
                updated = db.backfill_order_contact_info(rows)
            except Exception as e:
                results.append(f"⚠️ {name} → 갱신 실패 ({e})")
                continue
            total_updated += updated
            results.append(f"✅ {name} → {updated}건 보완")

        self.refresh()
        notify_data_changed()
        QMessageBox.information(
            self, "완료",
            f"총 {total_updated}건의 주문에 받는분 정보를 채웠습니다.\n\n" + "\n".join(results)
            + ("\n\n(이미 정보가 있는 주문은 건드리지 않았습니다)" if total_updated else "")
        )

    def _build_company_info(self, channel_id, order_date_str, shipping_fee):
        """거래명세표에 들어갈 공급자/공급받는자 정보를 만듦"""
        from datetime import datetime as _dt
        me = db.get_my_company_info()
        ch = next((x for x in db.get_channels() if x["id"] == channel_id), None)

        def g(row, key):
            try:
                return row[key] or ""
            except (IndexError, KeyError, TypeError):
                return ""

        try:
            d = _dt.strptime(order_date_str[:10], "%Y-%m-%d")
            date_label = f"{d.year}년 {d.month}월 {d.day}일"
        except Exception:
            date_label = order_date_str

        unpaid = 0
        try:
            for r in db.get_channel_unsettled_summary():
                if r["channel_id"] == channel_id:
                    unpaid = r["unsettled"] or 0
                    break
        except Exception:
            pass

        return {
            "date": date_label,
            "unpaid": unpaid,
            "bank_info": me.get("bank_info", ""),
            "seller": {
                "biznum": me.get("biznum", ""), "name": me.get("name", STORE_NAME),
                "ceo": me.get("ceo", ""), "address": me.get("address", ""),
                "business_type": me.get("business_type", ""),
                "business_item": me.get("business_item", ""),
            },
            "buyer": {
                "biznum": g(ch, "business_number"), "name": g(ch, "name"),
                # 대표자는 거래처관리의 '대표자 이름'(ceo)을 우선 사용.
                # 예전 데이터는 manager 칸에 대표자를 넣던 때가 있어 그것도 대비
                "ceo": g(ch, "ceo") or g(ch, "manager"),
                "address": g(ch, "address") or "",
                "business_type": g(ch, "business_type_ch") or "",
                "business_item": g(ch, "business_item_ch") or "",
            },
        }

    def open_doc_settings(self):
        """서류 출력 체크 기본값을 정해두는 창"""
        dlg = QDialog(self)
        dlg.setWindowTitle("서류 출력 기본 설정")
        dlg.resize(400, 220)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("💡 주문등록 화면을 열 때 아래 항목이 기본으로 체크됩니다."))
        cb1 = QCheckBox("📄 거래명세표 출력을 기본으로 체크")
        cb1.setChecked(conv_on("doc_statement", False))
        cb2 = QCheckBox("🚚 송장요청서 출력을 기본으로 체크")
        cb2.setChecked(conv_on("doc_invoice", False))
        v.addWidget(cb1); v.addWidget(cb2); v.addStretch()
        row = QHBoxLayout()
        ok = QPushButton("💾 저장")
        def _save():
            _qsettings.setValue("conv/doc_statement", "true" if cb1.isChecked() else "false")
            _qsettings.setValue("conv/doc_invoice", "true" if cb2.isChecked() else "false")
            self.doc_statement_cb.setChecked(cb1.isChecked())
            self.doc_invoice_cb.setChecked(cb2.isChecked())
            dlg.accept()
        ok.clicked.connect(_save)
        row.addWidget(ok)
        cancel = QPushButton("취소"); cancel.clicked.connect(dlg.reject)
        row.addWidget(cancel)
        v.addLayout(row)
        dlg.exec()

    def _export_statement(self, channel_id, order_date_str, product_name, option_name,
                           qty, sale_price, total_amount, shipping_fee, shipping_qty=None):
        import documents
        info = self._build_company_info(channel_id, order_date_str, shipping_fee)
        info["copy_label"] = "(공급받는자 보관용)"

        month = day = ""
        try:
            month, day = int(order_date_str[5:7]), int(order_date_str[8:10])
        except Exception:
            pass
        items = []
        if product_name:
            items.append({"month": month, "day": day, "name": product_name,
                          "spec": option_name, "qty": qty, "price": sale_price,
                          "amount": total_amount})
        # 복수로 담은 품목들도 명세표에 함께 표시
        for it in getattr(self, "_multi_cart", []):
            items.append({"month": month, "day": day, "name": it["name"],
                          "spec": it["option_name"], "qty": it["qty"],
                          "price": it["price"], "amount": it["qty"] * it["price"]})
        if shipping_fee:
            # 배송비는 '단가 × 건수'로 입력받으므로 명세표에도 그 건수를 그대로 표시
            # 폼이 초기화되기 전에 넘겨받은 건수를 우선 사용
            if shipping_qty:
                ship_qty = max(1, int(shipping_qty))
            else:
                try:
                    ship_qty = max(1, int(self.manual_shipping_qty.value()))
                except Exception:
                    ship_qty = 1
            ship_unit = int(round(shipping_fee / ship_qty)) if ship_qty else shipping_fee
            items.append({"month": month, "day": day, "name": "배송비", "spec": "",
                          "qty": ship_qty, "price": ship_unit, "amount": shipping_fee})
        # items 안에 배송비가 이미 들어있으므로 다시 더하지 않음 (예전엔 이중 계산됐음)
        total = sum(i["amount"] for i in items)

        mode = self.doc_statement_format.currentData()
        base_name = f"{info['buyer']['name'] or '거래처'}_거래명세표_{order_date_str}"

        if mode == "both":
            # 저장 폴더만 고르고 엑셀·그림 두 개를 함께 만듦
            folder = ask_directory(self, "거래명세표를 저장할 폴더 선택", "statement")
            if not folder:
                return None
            p1 = documents.export_statement_excel(
                os.path.join(folder, base_name + ".xlsx"), info, items, total)
            p2 = documents.export_statement_image(
                os.path.join(folder, base_name + ".png"), info, items, total)
            return f"{p1}\n  · {p2}"

        is_excel = mode == "excel"
        ext, filt = (".xlsx", "Excel 파일 (*.xlsx)") if is_excel else (".png", "그림 파일 (*.png)")
        path = ask_save_file(self, "거래명세표 저장", base_name + ext, filt, "statement")
        if not path:
            return None
        if is_excel:
            return documents.export_statement_excel(path, info, items, total)
        return documents.export_statement_image(path, info, items, total)

    def _export_invoice(self, product_name, option_name, qty):
        import documents
        dialog = ShipmentRequestDialog(
            default_product=f"{product_name} {option_name}".strip(),
            default_qty=qty,
            default_receiver=self.manual_buyer.text().strip(),
            parent=self)
        if dialog.exec() != QDialog.Accepted or not dialog.rows:
            return None

        default = f"송장요청서_{QDate.currentDate().toString('yyMMdd')}.xlsx"
        path = ask_save_file(self, "송장요청서 저장", default, "Excel 파일 (*.xlsx)", "invoice")
        if not path:
            return None
        result = documents.export_invoice_request(path, dialog.rows)
        try:
            db.save_shipment_history(dialog.rows)   # 다음에 골라 쓸 수 있게 기록
        except Exception:
            pass
        return result

    def return_checked_order(self):
        checked = self.get_checked_order_ids()
        if len(checked) != 1:
            QMessageBox.warning(self, "알림", "반품할 주문 1건만 체크해주세요.")
            return
        self.process_return(checked[0])

    def process_return(self, order_id):
        """구매자 반품 처리 - 주문상태를 '반품'으로 바꾸고 재고를 되돌림"""
        order = next((o for o in db.get_orders() if o["id"] == order_id), None)
        if not order:
            return
        if (order["status"] or "") == "반품":
            QMessageBox.information(self, "알림", "이미 반품 처리된 주문입니다.")
            return

        dialog = ReturnDialog(order, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            db.return_order_partial(order_id, dialog.return_qty, dialog.reason)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"반품 처리 중 오류가 발생했습니다:\n{e}")
            return
        matching.rematch_all_orders()
        show_save_toast(self)
        self.refresh()
        notify_data_changed()
        left = (order["qty"] or 0) - dialog.return_qty
        msg = (f"{dialog.return_qty}개를 반품 처리했습니다.\n"
               f"(재고 {dialog.return_qty}개가 되돌아왔습니다)")
        if left > 0:
            msg += f"\n남은 주문 수량: {left}개"
        QMessageBox.information(self, "완료", msg)

    def apply_default_fee_rates(self):
        count = db.apply_default_fee_rates()
        self.refresh()
        notify_data_changed()
        if count:
            QMessageBox.information(self, "완료", f"{count}건의 수수료를 채널별 수수료율로 계산해서 채웠습니다.")
        else:
            QMessageBox.information(
                self, "알림",
                "적용할 대상이 없습니다.\n(수수료가 0원이고, 그 주문의 채널+매칭된 품목 조합에 수수료율이 "
                "설정되어 있어야 적용됩니다 - 설정 > 채널별 수수료율 적용에서 먼저 등록해주세요)"
            )


# ---------------------------------------------------------------------------
# 품목관리 탭
# ---------------------------------------------------------------------------
class CostHistoryDialog(QDialog):
    """품목 매입가(원가) 변동 이력.
    입고 등록으로 원가가 자동 갱신된 것도, 품목관리에서 직접 고친 것도 모두 남습니다."""

    def __init__(self, parent=None, preselect_product_id=None):
        super().__init__(parent)
        self.setWindowTitle("매입가(원가) 변동 이력")
        self.resize(900, 540)

        layout = QVBoxLayout(self)
        title = QLabel("💲 매입가(원가) 변동 이력")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        note = QLabel("💡 원가가 실제로 달라졌을 때만 기록됩니다. "
                      "입고를 등록하면 원가가 최신 매입단가로 갱신되는데, 그것도 여기에 남아요.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        layout.addWidget(note)

        row = QHBoxLayout()
        self.product_combo = QComboBox()
        self.product_combo.setFixedWidth(280)
        self.product_combo.addItem("전체 품목", None)
        for pr in db.get_products():
            label = f"{pr['name']} {pr['option_name'] or ''}".strip()
            self.product_combo.addItem(label, pr["id"])
        if preselect_product_id is not None:
            idx = self.product_combo.findData(preselect_product_id)
            if idx >= 0:
                self.product_combo.setCurrentIndex(idx)
        self.product_combo.currentIndexChanged.connect(self.refresh)
        row.addWidget(tight_pair("품목:", self.product_combo))
        btn = QPushButton("조회")
        btn.clicked.connect(self.refresh)
        row.addWidget(btn)
        row.addStretch()
        export_btn = QPushButton("📄 엑셀로 내보내기")
        export_btn.clicked.connect(self.export_excel)
        row.addWidget(export_btn)
        layout.addLayout(row)

        self.summary = QLabel("")
        self.summary.setStyleSheet("padding:8px 12px; background:#EAF2F8;"
                                   "border-radius:5px; color:#1A5276;")
        layout.addWidget(self.summary)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.refresh()

    def _fmt_cost(self, v):
        """원가는 소수점 한 자리까지 보여줌 (314.5원처럼)"""
        v = float(v or 0)
        return f"{v:,.1f}원" if abs(v - round(v)) > 0.001 else f"{int(round(v)):,}원"

    def refresh(self):
        pid = self.product_combo.currentData()
        self._rows = db.get_cost_history(pid)
        rows = []
        for h in self._rows:
            old_c = float(h["old_cost"] or 0)
            new_c = float(h["new_cost"] or 0)
            diff = new_c - old_c
            pct = (diff / old_c * 100) if old_c else 0
            arrow = "▲ 인상" if diff > 0 else "▼ 인하"
            rows.append((
                (h["changed_at"] or "")[:19],
                f"{h['product_name'] or '(삭제된 품목)'} {h['option_name'] or ''}".strip(),
                self._fmt_cost(old_c), self._fmt_cost(new_c),
                f"{arrow} {self._fmt_cost(abs(diff))}",
                f"{pct:+.1f}%" if old_c else "-",
                h["source"] or "",
            ))
        fill_table(self.table,
                   ["변경일시", "품목", "이전 원가", "변경 원가", "변동", "변동률", "변경 경로"],
                   rows, persist_key="cost_history")

        # 변동 행에 색 입히기 (인상=빨강 / 인하=파랑)
        for r, h in enumerate(self._rows):
            diff = float(h["new_cost"] or 0) - float(h["old_cost"] or 0)
            item = self.table.item(r, 4)
            if item:
                item.setForeground(QColor("#C0392B" if diff > 0 else "#2471A3"))
                f = item.font(); f.setBold(True); item.setFont(f)

        if self._rows:
            ups = sum(1 for h in self._rows
                      if float(h["new_cost"] or 0) > float(h["old_cost"] or 0))
            self.summary.setText(
                f"총 {len(self._rows):,}건  |  인상 {ups:,}건  |  인하 {len(self._rows) - ups:,}건")
        else:
            self.summary.setText("아직 원가 변동 기록이 없습니다. "
                                 "이후 원가가 바뀌면 여기에 쌓입니다.")

    def export_excel(self):
        import pandas as pd
        if not self._rows:
            QMessageBox.information(self, "알림", "내보낼 이력이 없습니다.")
            return
        data = [{
            "변경일시": (h["changed_at"] or "")[:19],
            "SKU": h["sku"] or "",
            "품목": f"{h['product_name'] or ''} {h['option_name'] or ''}".strip(),
            "이전 원가": float(h["old_cost"] or 0),
            "변경 원가": float(h["new_cost"] or 0),
            "변동액": float(h["new_cost"] or 0) - float(h["old_cost"] or 0),
            "변경 경로": h["source"] or "",
        } for h in self._rows]
        filepath = ask_save_file(self, "엑셀로 저장", "매입가변동이력.xlsx",
                                 "Excel 파일 (*.xlsx)", "product")
        if filepath:
            pd.DataFrame(data).to_excel(filepath, index=False)
            QMessageBox.information(self, "완료", "엑셀 파일로 저장되었습니다.")


class StockAdjustHistoryDialog(QDialog):
    """품목별 재고 조정 이력"""

    def __init__(self, parent=None, preselect_product_id=None):
        super().__init__(parent)
        self.setWindowTitle("재고조정 이력")
        self.resize(880, 520)

        layout = QVBoxLayout(self)
        title = QLabel("🔧 재고조정 이력")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        row = QHBoxLayout()
        self.product_combo = QComboBox()
        self.product_combo.setFixedWidth(260)
        self.product_combo.addItem("전체 품목", None)
        for p in db.get_products():
            label = f"{p['name']} {p['option_name'] or ''}".strip()
            self.product_combo.addItem(label, p["id"])
        # 품목관리에서 특정 품목을 선택한 채로 열었으면 그 품목이 미리 골라져 있게 함
        if preselect_product_id is not None:
            idx = self.product_combo.findData(preselect_product_id)
            if idx >= 0:
                self.product_combo.setCurrentIndex(idx)
        self.product_combo.currentIndexChanged.connect(self.refresh)
        row.addWidget(tight_pair("품목:", self.product_combo))
        refresh_btn = QPushButton("조회")
        refresh_btn.clicked.connect(self.refresh)
        row.addWidget(refresh_btn)
        row.addStretch()
        layout.addLayout(row)

        self.summary = QLabel("")
        self.summary.setStyleSheet(
            "padding: 8px; background: #EAF2F8; font-weight: bold; border-radius: 6px;")
        layout.addWidget(self.summary)

        self.table = QTableWidget()
        enlarge_row_numbers(self.table)
        layout.addWidget(self.table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.refresh()

    def refresh(self):
        pid = self.product_combo.currentData()
        rows = db.get_stock_adjustments(product_id=pid, limit=500)
        plus = sum(r["change_qty"] for r in rows if (r["change_qty"] or 0) > 0)
        minus = -sum(r["change_qty"] for r in rows if (r["change_qty"] or 0) < 0)
        self.summary.setText(
            f"조정 {len(rows)}건   |   증가 +{plus:,}개   |   감소 −{minus:,}개   |   순증감 {plus - minus:+,}개")
        fill_table(self.table, ["조정일", "상품명(대분류)", "옵션(소분류)", "변동수량", "사유", "메모"],
                   [(r["adjust_date"], r["product_name"] or "", r["option_name"] or "",
                     f"{r['change_qty']:+,}개", r["reason"] or "", r["memo"] or "")
                    for r in rows], persist_key="stock_adjust_history")


class BundleListDialog(QDialog):
    """등록된 조합(세트) 품목 목록 + 기간별 출고(판매) 내역"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("조합(세트) 리스트")
        self.resize(950, 620)

        layout = QVBoxLayout(self)
        title = QLabel("🧩 조합(세트) 품목 목록")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        note = QLabel("💡 조합 품목이 팔리면 아래 구성품 재고가 각각 차감됩니다. "
                       "조합 품목 자체는 재고를 갖지 않습니다.")
        note.setStyleSheet("color: #666;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.bundle_table = QTableWidget()
        self.bundle_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.bundle_table)

        del_row = QHBoxLayout()
        del_btn = QPushButton("🗑️ 선택한 조합 해제")
        del_btn.setToolTip("조합 설정만 해제합니다 (품목 자체는 남습니다)")
        del_btn.setStyleSheet("color: red;")
        del_btn.clicked.connect(self.delete_selected_bundle)
        del_row.addWidget(del_btn)
        del_row.addStretch()
        layout.addLayout(del_row)

        layout.addWidget(QLabel("📦 조합 출고(판매) 내역"))
        filter_row = QHBoxLayout()
        self.date_from = make_date_edit()
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        filter_row.addWidget(tight_pair("시작일:", self.date_from))
        self.date_to = make_date_edit()
        self.date_to.setDate(QDate.currentDate())
        filter_row.addWidget(tight_pair("종료일:", self.date_to))
        filter_row.addSpacing(20)
        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh_shipments)
        filter_row.addWidget(search_btn)
        all_btn = QPushButton("전체기간")
        all_btn.clicked.connect(self._set_all_period)
        filter_row.addWidget(all_btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self.ship_summary = QLabel("")
        self.ship_summary.setStyleSheet(
            "padding: 8px; background: #EAF2F8; font-weight: bold; border-radius: 6px;")
        layout.addWidget(self.ship_summary)

        self.ship_table = QTableWidget()
        layout.addWidget(self.ship_table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._bundle_ids = []
        self.refresh()

    def _set_all_period(self):
        self.date_from.setDate(QDate(2000, 1, 1))
        self.date_to.setDate(QDate.currentDate())
        self.refresh_shipments()

    def refresh(self):
        products = {p["id"]: p for p in db.get_products()}
        bundle_ids = sorted(db.get_all_bundle_ids())
        self._bundle_ids = bundle_ids
        rows = []
        for bid in bundle_ids:
            p = products.get(bid)
            if not p:
                continue
            comps = db.get_bundle_components(bid)
            comp_text = " + ".join(
                f"{(x['component_option'] or x['component_name'])}"
                f"×{x['qty'] or 1} (재고 {x['component_stock'] or 0:,})" for x in comps)
            # 구성품 재고로 만들 수 있는 최대 세트 수
            makeable = min(
                [int((x["component_stock"] or 0) // (x["qty"] or 1)) for x in comps], default=0)
            rows.append((f"{p['name']} {p['option_name'] or ''}".strip(),
                         comp_text, fmt_price(p["cost_price"]), fmt_price(p["sale_price"]),
                         f"{makeable:,}세트"))
        fill_table(self.bundle_table,
                   ["조합 품목", "구성품 (수량/현재고)", "원가합계", "판매가", "제작가능"],
                   rows, persist_key="bundle_list")
        fit_table_height(self.bundle_table, max_rows=7)
        self.refresh_shipments()

    def refresh_shipments(self):
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        shipments = db.get_bundle_shipment_history(date_from, date_to)
        total_qty = sum(s["qty"] for s in shipments)
        self.ship_summary.setText(
            f"{date_from} ~ {date_to}   |   조합 출고 {len(shipments)}건   |   총 {total_qty:,}세트")
        fill_table(self.ship_table,
                   ["출고일", "채널", "주문번호", "조합 품목", "세트수", "차감된 구성품", "구매자"],
                   [(s["date"], s["channel_name"], s["order_no"], s["bundle_label"],
                     f"{s['qty']:,}", s["components"], s["buyer_name"]) for s in shipments],
                   persist_key="bundle_shipments")

    def delete_selected_bundle(self):
        row = self.bundle_table.currentRow()
        if row < 0 or row >= len(self._bundle_ids):
            QMessageBox.warning(self, "알림", "해제할 조합을 선택해주세요.")
            return
        bid = self._bundle_ids[row]
        if confirm_delete(
                self, "이 품목의 조합(세트) 설정",
                "품목 자체는 남습니다. 이후 판매되면 구성품이 아니라 이 품목의 재고가 차감됩니다.",
                title="⚠️ 조합 해제 확인"):
            db.delete_bundle(bid)
            notify_data_changed()
            self.refresh()


class ProductsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("📦 품목 관리")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        # 엑셀로 대량 업로드/다운로드
        io_row = QHBoxLayout()
        import_btn = QPushButton("📥 엑셀 업로드 (대량 등록)")
        import_btn.clicked.connect(self.import_from_excel)
        io_row.addWidget(import_btn)
        export_btn = QPushButton("📤 엑셀로 다운로드")
        export_btn.clicked.connect(self.export_to_excel)
        io_row.addWidget(export_btn)
        io_row.addStretch()
        layout.addLayout(io_row)

        self.editing_id = None  # 수정 모드일 때 해당 품목 id

        form_box = QGroupBox("품목 등록")
        form = QFormLayout(form_box)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self.sku_input = QLineEdit()
        self.sku_input.setFixedWidth(200)
        self.name_input = QLineEdit()
        self.name_input.setFixedWidth(400)
        self.option_input = QLineEdit()
        self.option_input.setFixedWidth(400)
        self.cost_input = QLineEdit()
        self.cost_input.setFixedWidth(150)
        self.cost_input.setPlaceholderText("소수점 한 자리까지 (예: 314.5)")
        self.price_input = QLineEdit()
        self.price_input.setFixedWidth(150)
        self.stock_input = QLineEdit()
        self.stock_input.setFixedWidth(150)
        self.memo_input = QLineEdit()
        self.memo_input.setFixedWidth(400)
        form.addRow("SKU/코드", self.sku_input)
        form.addRow("상품명(대분류) *", self.name_input)
        form.addRow("옵션(소분류)", self.option_input)
        cost_row = QWidget()
        cost_row_layout = QHBoxLayout(cost_row)
        cost_row_layout.setContentsMargins(0, 0, 0, 0)
        cost_row_layout.addWidget(self.cost_input)
        self.supply_input = QLineEdit()
        self.supply_input.setFixedWidth(110)
        self.supply_input.setPlaceholderText("공급가액")
        self.vat_total_input = QLineEdit()
        self.vat_total_input.setFixedWidth(110)
        self.vat_total_input.setPlaceholderText("합계(VAT포함)")
        cost_row_layout.addWidget(QLabel("공급가액"))
        cost_row_layout.addWidget(self.supply_input)
        cost_row_layout.addWidget(QLabel("↔ 합계"))
        cost_row_layout.addWidget(self.vat_total_input)
        cost_row_layout.addStretch()
        self._vat_calc_busy = False
        self.supply_input.textEdited.connect(self._on_supply_edited)
        self.vat_total_input.textEdited.connect(self._on_vat_total_edited)
        self.cost_input.textEdited.connect(self._on_cost_edited)
        form.addRow("원가", cost_row)
        vat_hint = QLabel("    └ 공급가액을 넣으면 합계(×1.1)가, 합계를 넣으면 공급가액(÷1.1)이 "
                          "자동 계산됩니다. 원가에는 공급가액이 들어갑니다.")
        vat_hint.setStyleSheet("color:#888; font-size:11px;")
        vat_hint.setWordWrap(True)
        form.addRow("", vat_hint)
        form.addRow("판매가", self.price_input)
        form.addRow("재고수량", self.stock_input)
        form.addRow("메모", self.memo_input)

        # 등록 버튼 (수정 모드일 때는 "수정 저장"으로 바뀜)
        self.save_btn = QPushButton("등록")
        self.save_btn.clicked.connect(self.save_product)
        form.addRow(self.save_btn)

        self.cancel_edit_btn = QPushButton("편집 취소")
        self.cancel_edit_btn.clicked.connect(self.cancel_edit)
        self.cancel_edit_btn.hide()
        form.addRow(self.cancel_edit_btn)

        # 품목 등록 폼(왼쪽) + 재고 현황 요약(오른쪽)을 나란히 배치해서
        # 폼 오른쪽에 남던 빈 공간을 활용
        form_row = QWidget()
        form_row_layout = QHBoxLayout(form_row)
        form_row_layout.setContentsMargins(0, 0, 0, 0)
        form_row_layout.addWidget(form_box)

        self.stock_summary_box = QGroupBox("📦 현재 재고 현황")
        stock_summary_layout = QVBoxLayout(self.stock_summary_box)
        stock_summary_layout.setSpacing(10)

        # 상단: 총 재고 가액을 크게 강조
        self.stock_value_label = QLabel("")
        self.stock_value_label.setAlignment(Qt.AlignCenter)
        self.stock_value_label.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #667eea, stop:1 #764ba2);
                color: white; border-radius: 10px; padding: 14px;
                font-size: 15px; font-weight: bold;
            }
        """)
        stock_summary_layout.addWidget(self.stock_value_label)

        # 중간: 지표 카드 4개 (2x2)
        cards_grid = QGridLayout()
        cards_grid.setSpacing(8)
        self._stock_cards = {}
        card_defs = [
            ("items", "등록 품목", "#5DADE2"),
            ("qty", "총 재고 수량", "#48C9B0"),
            ("low", "재고 부족(5개↓)", "#EC7063"),
            ("warn", "주의(6~30개)", "#58D68D"),
        ]
        for i, (key, title, color) in enumerate(card_defs):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{ background-color: white; border: 1px solid #E5E7EB;
                          border-left: 5px solid {color}; border-radius: 8px; }}
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet("color: #6B7280; font-size: 11px; border: none;")
            v = QLabel("-")
            v.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold; border: none;")
            cl.addWidget(t)
            cl.addWidget(v)
            cards_grid.addWidget(card, i // 2, i % 2)
            self._stock_cards[key] = v
        stock_summary_layout.addLayout(cards_grid)

        # 하단: 품절 경고 + 색상 범례
        self.stock_soldout_label = QLabel("")
        self.stock_soldout_label.setStyleSheet(
            "background-color: #FEF3C7; color: #92400E; border-radius: 6px; padding: 8px; font-size: 12px;")
        self.stock_soldout_label.setWordWrap(True)
        stock_summary_layout.addWidget(self.stock_soldout_label)

        stock_summary_layout.addStretch()
        legend = QLabel("🟩 재고 30개 이하    🟥 재고 5개 이하")
        legend.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        stock_summary_layout.addWidget(legend)
        form_row_layout.addWidget(self.stock_summary_box, stretch=1)

        layout.addWidget(form_row)

        # 등록 버튼 밑에 체크박스 선택 항목에 대한 수정/삭제/기타 메뉴
        action_box = QGroupBox("선택 항목 관리 (표 왼쪽 체크박스로 선택)")
        action_layout = QHBoxLayout(action_box)

        edit_btn = QPushButton("✏️ 수정")
        edit_btn.clicked.connect(self.edit_checked)
        action_layout.addWidget(edit_btn)

        delete_btn = QPushButton("🗑️ 삭제")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(self.delete_checked)
        action_layout.addWidget(delete_btn)

        bundle_btn = QPushButton("🧩 조합")
        bundle_btn.setToolTip("2개 이상 체크하면 조합(세트) 품목을 만듭니다.\n"
                               "첫 번째 품목이 기준이 되고 나머지 옵션명이 괄호로 붙습니다.\n"
                               "조합 품목이 팔리면 구성품 재고가 각각 차감됩니다.")
        bundle_btn.clicked.connect(self.make_bundle)
        action_layout.addWidget(bundle_btn)

        stock_adj_btn = QPushButton("🔧 재고 조정/이력")
        stock_adj_btn.setToolTip("재고를 직접 조정하고, 지금까지의 조정 이력도 함께 볼 수 있어요")
        stock_adj_btn.clicked.connect(self.open_stock_adjust)
        action_layout.addWidget(stock_adj_btn)

        cost_hist_btn = QPushButton("💲 원가 변동 이력")
        cost_hist_btn.setToolTip("매입가(원가)가 언제 얼마에서 얼마로 바뀌었는지, "
                                 "어디서 바뀌었는지 볼 수 있어요")
        cost_hist_btn.clicked.connect(self.open_cost_history)
        action_layout.addWidget(cost_hist_btn)

        rematch_btn = QPushButton("🔗 매칭 다시하기")
        rematch_btn.setToolTip("등록된 주문을 현재 품목 기준으로 다시 매칭하고 재고를 새로 계산합니다")
        rematch_btn.clicked.connect(self.rematch_all)
        action_layout.addWidget(rematch_btn)

        fix_fee_btn = QPushButton("🩹 수수료 음수 바로잡기")
        fix_fee_btn.setToolTip("마켓 파일에서 수수료가 음수로 들어온 주문을 양수로 정리합니다")
        fix_fee_btn.clicked.connect(self.fix_negative_fees)
        action_layout.addWidget(fix_fee_btn)

        bundle_list_btn = QPushButton("📜 조합 리스트")
        bundle_list_btn.setToolTip("등록된 조합(세트) 품목과 구성품, 그리고 기간별 출고 내역을 봅니다")
        bundle_list_btn.clicked.connect(self.open_bundle_list)
        action_layout.addWidget(bundle_list_btn)

        check_all_btn = QPushButton("전체 선택")
        check_all_btn.clicked.connect(lambda: self.set_all_checked(True))
        action_layout.addWidget(check_all_btn)

        uncheck_all_btn = QPushButton("전체 해제")
        uncheck_all_btn.clicked.connect(lambda: self.set_all_checked(False))
        action_layout.addWidget(uncheck_all_btn)

        layout.addWidget(action_box)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_row_double_clicked)
        enable_persistent_column_widths(self.table, "products")
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh, exclude_columns=(0,))
        layout.addWidget(self.table)

        # 재고 조정 내역 (접어둘 수 있음)

        self.refresh()



    def export_to_excel(self):
        import pandas as pd
        products = db.get_products()
        if not products:
            QMessageBox.information(self, "알림", "내보낼 품목이 없습니다.")
            return
        df = pd.DataFrame([{
            "SKU": p["sku"], "상품명(대분류)": p["name"], "옵션(소분류)": p["option_name"], "원가": p["cost_price"],
            "판매가": p["sale_price"], "재고수량": p["stock_qty"], "메모": p["memo"],
        } for p in products])
        filepath = ask_save_file(self, "엑셀로 저장", f"품목목록_{date.today()}.xlsx",
                                 "Excel 파일 (*.xlsx)", "product")
        if filepath:
            df.to_excel(filepath, index=False)
            QMessageBox.information(self, "완료", f"{len(products)}개 품목을 엑셀로 저장했습니다.")

    def import_from_excel(self):
        import pandas as pd
        filepath = ask_open_file(self, "품목 엑셀 파일 선택",
                                 "엑셀/CSV 파일 (*.xlsx *.xls *.csv)", "product")
        if not filepath:
            return

        try:
            if filepath.lower().endswith(".csv"):
                try:
                    df = pd.read_csv(filepath, dtype=str, encoding="cp949")
                except UnicodeDecodeError:
                    df = pd.read_csv(filepath, dtype=str, encoding="utf-8-sig")
            else:
                df = pd.read_excel(filepath, dtype=str)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일을 읽는 중 오류가 발생했습니다:\n{e}")
            return

        try:
            # 컬럼명 유연하게 매칭 (대소문자/공백 무시, 비슷한 이름 허용)
            col_aliases = {
                "sku": ["SKU", "sku", "코드", "품목코드"],
                "name": ["상품명(대분류)", "상품명", "품목명", "이름", "name"],
                "option_name": ["옵션(소분류)", "옵션", "옵션명", "소분류", "option"],
                "cost_price": ["원가", "매입가", "cost"],
                "sale_price": ["판매가", "판매단가", "price"],
                "stock_qty": ["재고수량", "재고", "수량", "stock"],
                "memo": ["메모", "비고", "memo"],
            }
            columns = [str(c).strip() for c in df.columns]

            def find_col(aliases):
                for alias in aliases:
                    if alias in columns:
                        return alias
                for alias in aliases:
                    for col in columns:
                        if alias in col:
                            return col
                return None

            mapping = {k: find_col(v) for k, v in col_aliases.items()}
            if not mapping["name"]:
                QMessageBox.warning(
                    self, "알림",
                    "상품명 컬럼을 찾을 수 없습니다.\n"
                    "엑셀 파일에 'SKU / 상품명(대분류) / 옵션(소분류) / 원가 / 판매가 / 재고수량 / 메모' 형식의 "
                    "헤더가 있는지 확인해주세요. (엑셀 다운로드 버튼으로 양식을 먼저 받아보실 수 있어요)"
                )
                return

            def to_int(val, default=0):
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    return default
                s = str(val).strip().replace(",", "")
                return int(s) if s.lstrip("-").isdigit() else default

            def clean_str(val):
                if val is None:
                    return ""
                if isinstance(val, float) and pd.isna(val):
                    return ""
                s = str(val).strip()
                return "" if s.lower() == "nan" else s

            existing_keys = {
                (p["name"].strip().lower(), (p["option_name"] or "").strip().lower())
                for p in db.get_products()
            }
            seen_in_file = set()
            count = 0
            skipped = 0
            for _, row in df.iterrows():
                name = clean_str(row.get(mapping["name"])) if mapping["name"] else ""
                if not name:
                    continue
                option_name = clean_str(row.get(mapping["option_name"])) if mapping["option_name"] else ""
                key = (name.lower(), option_name.lower())
                if key in existing_keys or key in seen_in_file:
                    skipped += 1
                    continue
                seen_in_file.add(key)
                sku = clean_str(row.get(mapping["sku"])) if mapping["sku"] else ""
                memo = clean_str(row.get(mapping["memo"])) if mapping["memo"] else ""
                cost_price = to_int(row.get(mapping["cost_price"])) if mapping["cost_price"] else 0
                sale_price = to_int(row.get(mapping["sale_price"])) if mapping["sale_price"] else 0
                stock_qty = to_int(row.get(mapping["stock_qty"])) if mapping["stock_qty"] else 0
                db.add_product(sku, name, cost_price, sale_price, stock_qty, memo, option_name=option_name)
                count += 1

            matching.rematch_all_orders()
            notify_data_changed()
            self.refresh()
            msg = f"{count}개 품목을 등록했습니다."
            if skipped:
                msg += f"\n이미 등록되어 있던 {skipped}개는 중복이라 건너뛰었습니다."
            QMessageBox.information(self, "완료", msg)
        except Exception as e:
            # 어떤 예상치 못한 오류가 나더라도 반드시 안내창이 뜨도록 함
            # (이전엔 여기서 예외가 나면 "무반응"처럼 보이는 문제가 있었음)
            QMessageBox.critical(
                self, "오류",
                f"품목 등록 중 예상치 못한 오류가 발생했습니다:\n{e}\n\n"
                "파일 형식을 확인해 주시거나, 문제가 계속되면 알려주세요."
            )

    # ---------- 등록/수정 ----------
    # ----- 공급가액 / 합계금액(부가세 포함) 자동 계산 -----
    @staticmethod
    def _fmt_money1(v):
        """소수점 한 자리까지만 표시하고, 정수면 소수점을 떼어냄"""
        return f"{v:.1f}".rstrip("0").rstrip(".") if v else "0"

    def _on_supply_edited(self, text):
        """공급가액을 입력하면 합계(×1.1)와 원가를 채움"""
        if getattr(self, "_vat_calc_busy", False):
            return
        self._vat_calc_busy = True
        try:
            supply = to_float(text, 0)
            self.vat_total_input.setText(self._fmt_money1(round(supply * 1.1, 1)))
            # 매입세액은 나중에 공제받으므로 원가에는 공급가액을 넣음
            self.cost_input.setText(self._fmt_money1(round(supply, 1)))
        finally:
            self._vat_calc_busy = False

    def _on_vat_total_edited(self, text):
        """합계(부가세 포함)를 입력하면 공급가액(÷1.1)과 원가를 채움"""
        if getattr(self, "_vat_calc_busy", False):
            return
        self._vat_calc_busy = True
        try:
            total = to_float(text, 0)
            supply = round(total / 1.1, 1) if total else 0
            self.supply_input.setText(self._fmt_money1(supply))
            self.cost_input.setText(self._fmt_money1(supply))
        finally:
            self._vat_calc_busy = False

    def _on_cost_edited(self, text):
        """원가를 직접 고치면 공급가액·합계 칸도 맞춰줌"""
        if getattr(self, "_vat_calc_busy", False):
            return
        self._vat_calc_busy = True
        try:
            supply = to_float(text, 0)
            self.supply_input.setText(self._fmt_money1(supply))
            self.vat_total_input.setText(self._fmt_money1(round(supply * 1.1, 1)))
        finally:
            self._vat_calc_busy = False

    def save_product(self):
        name = self.name_input.text().strip()
        option_name = self.option_input.text().strip()
        if not name:
            QMessageBox.warning(self, "알림", "상품명은 필수입니다.")
            return

        # 중복 검사: 상품명(대분류) + 옵션(소분류) 조합이 같으면 중복으로 취급
        duplicate = next(
            (p for p in db.get_products()
             if p["name"].strip().lower() == name.lower()
             and (p["option_name"] or "").strip().lower() == option_name.lower()
             and p["id"] != self.editing_id),
            None
        )
        if duplicate:
            QMessageBox.warning(
                self, "중복된 상품",
                f"이미 등록된 상품(옵션 조합)입니다: '{duplicate['name']}' / '{duplicate['option_name'] or ''}' "
                f"(ID {duplicate['id']})\n"
                "다른 이름/옵션을 사용하시거나, 기존 항목을 목록에서 더블클릭해서 수정해주세요."
            )
            return

        def to_int(s):
            s = s.strip().replace(",", "")
            return int(s) if s.isdigit() else 0

        args = (
            self.sku_input.text().strip(), name,
            to_float(self.cost_input.text()), to_int(self.price_input.text()),
            to_int(self.stock_input.text()), self.memo_input.text().strip()
        )

        if self.editing_id is not None:
            db.update_product(self.editing_id, *args, option_name=option_name)
            self.cancel_edit()
        else:
            db.add_product(*args, option_name=option_name)
            self._clear_form()

        matching.rematch_all_orders()
        notify_data_changed()
        self.refresh()

    def _clear_form(self):
        for w in (self.sku_input, self.name_input, self.option_input, self.cost_input,
                  self.price_input, self.stock_input, self.memo_input):
            w.clear()

    def _load_product_into_form(self, product):
        self.sku_input.setText(product["sku"] or "")
        self.name_input.setText(product["name"] or "")
        self.option_input.setText(product["option_name"] or "")
        self.cost_input.setText(str(product["cost_price"] or 0))
        self.price_input.setText(str(product["sale_price"] or 0))
        self.stock_input.setText(str(product["stock_qty"] or 0))
        self.memo_input.setText(product["memo"] or "")

    def start_edit(self, pid):
        products = {p["id"]: p for p in db.get_products()}
        product = products.get(pid)
        if not product:
            return
        self.editing_id = pid
        self._load_product_into_form(product)
        self.save_btn.setText("💾 수정 저장")
        self.cancel_edit_btn.show()

    def cancel_edit(self):
        self.editing_id = None
        self._clear_form()
        self.save_btn.setText("등록")
        self.cancel_edit_btn.hide()

    # ---------- 표 관련 ----------
    def refresh(self):
        if self.editing_id is not None:
            self.cancel_edit()  # 탭을 벗어났다가 돌아오면 편집 중이던 폼을 초기화

        products = db.get_products()
        profit_summary = db.get_product_profit_summary()
        bundle_ids = db.get_all_bundle_ids()   # 조합(세트) 품목은 이름 앞에 🧩 표시

        # 오른쪽 재고 현황 요약 갱신
        total_items = len(products)
        total_qty = sum(p["stock_qty"] or 0 for p in products)
        total_value = sum((p["cost_price"] or 0) * (p["stock_qty"] or 0) for p in products)
        low5 = [p for p in products if (p["stock_qty"] or 0) <= 5]
        low30 = [p for p in products if 5 < (p["stock_qty"] or 0) <= 30]
        soldout = [p for p in products if (p["stock_qty"] or 0) <= 0]

        self.stock_value_label.setText(f"💰 총 재고 가액<br><span style='font-size:22px;'>{fmt_won(total_value)}</span>")
        self._stock_cards["items"].setText(f"{total_items:,}")
        self._stock_cards["qty"].setText(f"{total_qty:,}")
        self._stock_cards["low"].setText(f"{len(low5)}")
        self._stock_cards["warn"].setText(f"{len(low30)}")

        if soldout:
            names = ", ".join(f"{p['name']} {p['option_name'] or ''}".strip() for p in soldout[:4])
            more = f" 외 {len(soldout) - 4}건" if len(soldout) > 4 else ""
            self.stock_soldout_label.setText(f"⚠️ 품절 {len(soldout)}개 품목 : {names}{more}")
            self.stock_soldout_label.show()
        else:
            self.stock_soldout_label.setText("✅ 품절된 품목이 없습니다")
            self.stock_soldout_label.setStyleSheet(
                "background-color: #D1FAE5; color: #065F46; border-radius: 6px; padding: 8px; font-size: 12px;")

        headers = ["선택", "ID", "SKU", "상품명(대분류)", "옵션(소분류)", "원가", "판매가", "재고", "메모",
                   "판매수량", "매출", "수수료", "원가합계"]

        # 정렬을 위해 표시용 값(체크박스 자리는 더미 "")과 원본 product를 함께 구성
        display_rows = []
        for p in products:
            ps = profit_summary.get(p["id"])
            sold_qty = ps["sold_qty"] if ps else 0
            total_sales = ps["total_sales"] if ps else 0
            total_fee = ps["total_fee"] if ps else 0
            total_cost = ps["total_cost"] if ps else 0
            profit = ps["profit"] if ps else 0
            display_rows.append((
                "", p["id"], p["sku"],
                ("🧩 " if p["id"] in bundle_ids else "") + (p["name"] or ""),
                p["option_name"], fmt_price(p["cost_price"]),
                fmt_won(p["sale_price"]), p["stock_qty"], p["memo"],
                f"{sold_qty:,}개", fmt_won(total_sales), fmt_won(total_fee),
                fmt_won(total_cost),
            ))

        display_rows, products = apply_table_sort(display_rows, products, self._sort_state)
        self._ids = [p["id"] for p in products]
        profit_list = [profit_summary.get(p["id"]) for p in products]

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(products))

        for r, (values, ps) in enumerate(zip(display_rows, profit_list)):
            checkbox_container, _ = make_checkbox_cell()
            self.table.setCellWidget(r, 0, checkbox_container)

            stock_qty = values[7] or 0
            for c, val in enumerate(values):
                if c == 0:
                    continue  # 체크박스 컬럼 (위젯이라 아이템 없음)
                text = str(val) if val is not None else ""
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if looks_numeric(text):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                # 재고 컬럼(7번)은 한눈에 들어오도록 굵은 글씨로 표시
                if c == 7:
                    bold_font = item.font()
                    bold_font.setBold(True)
                    item.setFont(bold_font)
                # 재고가 적은 품목은 행 전체에 색을 채워서 눈에 띄게 함
                # (5개 이하 = 빨강 / 30개 이하 = 녹색)
                if conv_on("low_stock_color"):
                    if stock_qty <= 5:
                        item.setBackground(QColor("#F5B7B1"))
                    elif stock_qty <= 30:
                        item.setBackground(QColor("#ABEBC6"))
                self.table.setItem(r, c, item)

        header = self.table.horizontalHeader()
        header.blockSignals(True)
        self.table.resizeColumnsToContents()
        header.blockSignals(False)
        self.table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        restore_column_widths(self.table, "products")

    def get_checked_ids(self):
        checked = []
        for r in range(self.table.rowCount()):
            if is_row_checked(self.table, r):
                checked.append(self._ids[r])
        return checked

    def set_all_checked(self, checked: bool):
        for r in range(self.table.rowCount()):
            set_row_checked(self.table, r, checked)

    # ---------- 더블클릭 메뉴 ----------
    def on_row_double_clicked(self, row, column):
        if column == 0 or row < 0 or row >= len(self._ids):
            return
        pid = self._ids[row]
        menu = QMenu(self)
        edit_action = menu.addAction("✏️ 수정")
        delete_action = menu.addAction("🗑️ 삭제")
        history_action = menu.addAction("📦 입출고 내역")
        chosen = menu.exec(QCursor.pos())

        if chosen == edit_action:
            self.start_edit(pid)
        elif chosen == delete_action:
            self._delete_ids([pid])
        elif chosen == history_action:
            product = next((p for p in db.get_products() if p["id"] == pid), None)
            if product:
                dialog = ProductStockHistoryDialog(product, self)
                dialog.exec()

    # ---------- 선택 항목 액션 ----------
    def edit_checked(self):
        checked = self.get_checked_ids()
        if len(checked) != 1:
            QMessageBox.warning(self, "알림", "수정은 한 번에 한 항목만 가능합니다.\n체크박스에서 1개만 선택해주세요.")
            return
        self.start_edit(checked[0])

    def delete_checked(self):
        checked = self.get_checked_ids()
        if not checked:
            QMessageBox.warning(self, "알림", "삭제할 항목을 체크박스에서 선택해주세요.")
            return
        self._delete_ids(checked)

    def open_stock_adjust_history(self):
        StockAdjustHistoryDialog(self).exec()
        self.refresh()

    def open_stock_adjust(self):
        checked = self.get_checked_ids()
        preselect = checked[0] if len(checked) == 1 else None
        StockAdjustHistoryDialog(self, preselect_product_id=preselect).exec()

    def rematch_all(self):
        """등록된 주문을 지금 품목 기준으로 전부 다시 매칭하고 재고를 다시 계산.
        품목을 새로 만들거나 옵션명을 고친 뒤에 눌러주면 됨"""
        if QMessageBox.question(
                self, "매칭 다시하기",
                "등록된 모든 주문을 지금 품목 기준으로 다시 매칭합니다.\n"
                "재고도 주문 내역에 맞춰 다시 계산됩니다.\n\n"
                "진행할까요?") != QMessageBox.Yes:
            return
        try:
            matched, unmatched = matching.rematch_all_orders()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"매칭 중 오류가 발생했습니다:\n{e}")
            return
        synced = ""
        try:
            db.sync_stock_for_all_orders()
            synced = "\n재고도 다시 계산했습니다."
        except Exception:
            synced = "\n(재고 재계산은 건너뛰었습니다)"
        notify_data_changed()
        self.refresh()
        QMessageBox.information(
            self, "완료",
            f"매칭 완료: {matched:,}건 매칭, {unmatched:,}건은 맞는 품목을 찾지 못했습니다."
            + synced)

    def fix_negative_fees(self):
        """수수료가 음수로 저장된 주문을 양수로 바로잡음"""
        cnt, total = db.count_negative_fees()
        if not cnt:
            QMessageBox.information(self, "확인", "수수료가 음수인 주문은 없습니다.")
            return
        if QMessageBox.question(
                self, "수수료 바로잡기",
                f"수수료가 음수로 저장된 주문이 {cnt:,}건 있습니다.\n"
                f"(합계 {fmt_won(total)})\n\n"
                "마켓 파일은 수수료를 차감 항목이라 음수로 적는데, 그대로 저장되면\n"
                "이익이 실제보다 많게 계산됩니다.\n\n"
                "이 주문들의 수수료를 양수로 바꿀까요?") != QMessageBox.Yes:
            return
        fixed = db.fix_negative_fees()
        notify_data_changed()
        self.refresh()
        QMessageBox.information(self, "완료",
                                f"{fixed:,}건의 수수료를 양수로 바로잡았습니다.\n"
                                "리포트의 이익 금액이 다시 계산됩니다.")

    def open_cost_history(self):
        """선택한 품목이 있으면 그 품목의 원가 변동 이력을 바로 보여줌"""
        checked = self.get_checked_ids()
        preselect = checked[0] if len(checked) == 1 else None
        CostHistoryDialog(self, preselect_product_id=preselect).exec()
        self.refresh()

    def open_bundle_list(self):
        BundleListDialog(self).exec()
        self.refresh()

    def make_bundle(self):
        """체크된 2개 이상 품목을 묶어 조합(세트) 품목을 만듦"""
        checked = self.get_checked_ids()
        if len(checked) < 2:
            QMessageBox.warning(
                self, "알림",
                "조합할 품목을 2개 이상 체크해주세요.\n"
                "(맨 처음 체크한 품목이 기준이 되고, 나머지 옵션명이 괄호로 붙습니다)")
            return

        products = {p["id"]: p for p in db.get_products()}
        def label(pid):
            p = products[pid]
            return f"{p['name']} {p['option_name'] or ''}".strip()

        # 어떤 품목을 기준으로 삼을지 직접 고르게 함
        # (기준 품목의 이름·옵션에 나머지 품목 이름이 괄호로 덧붙습니다)
        choices = [label(pid) for pid in checked]
        picked, ok = QInputDialog.getItem(
            self, "기준 상품 선택",
            "조합 품목의 '기준'이 될 상품을 골라주세요.\n"
            "(기준 상품의 옵션명 뒤에 나머지 품목 이름이 괄호로 붙습니다)\n"
            "예: 컴팩트릴 20M + 가이드  →  컴팩트릴 20M(가이드)",
            choices, 0, False)
        if not ok:
            return
        base_id = checked[choices.index(picked)]
        ordered = [base_id] + [pid for pid in checked if pid != base_id]

        preview_lines = "\n".join(
            f"   {'①(기준)' if i == 0 else f'　{i+1}'} {label(pid)}" for i, pid in enumerate(ordered))
        reply = QMessageBox.question(
            self, "조합 품목 만들기",
            f"아래 {len(ordered)}개 품목을 묶어 조합(세트) 품목을 만들까요?\n\n{preview_lines}\n\n"
            "· 조합 품목은 자기 재고를 갖지 않고, 팔리면 위 구성품 재고가 각각 차감됩니다.\n"
            "· 원가는 구성품 원가의 합으로 자동 계산됩니다."
        )
        if reply != QMessageBox.Yes:
            return

        # 조합 이름(옵션명)을 직접 정할 수 있게 함 - 기본값은 "옵션+옵션" 형태
        products_all = {p["id"]: p for p in db.get_products()}
        def opt_of(pid):
            p = products_all[pid]
            return (p["option_name"] or p["name"] or "").strip()
        default_option = "+".join(opt_of(pid) for pid in ordered)
        new_option, ok = QInputDialog.getText(
            self, "조합 이름 정하기",
            "조합 품목의 옵션명을 정해주세요.\n"
            "(마켓 주문의 옵션명과 비슷하게 적을수록 자동 매칭이 잘 됩니다)",
            text=default_option)
        if not ok or not new_option.strip():
            return

        try:
            bundle_id, name = db.create_bundle_product(ordered, option_name=new_option.strip())
        except Exception as e:
            QMessageBox.critical(self, "오류", f"조합 품목을 만들지 못했습니다:\n{e}")
            return

        matching.rematch_all_orders()
        notify_data_changed()
        self.refresh()
        QMessageBox.information(
            self, "완료",
            f"조합 품목 '{name}' 을(를) 만들었습니다.\n\n"
            "마켓 주문의 옵션명이 이 이름과 맞으면 자동으로 매칭되고,\n"
            "판매될 때마다 구성품 재고가 대신 차감됩니다.")

    def duplicate_checked(self):
        checked = self.get_checked_ids()
        if not checked:
            QMessageBox.warning(self, "알림", "복제할 항목을 체크박스에서 선택해주세요.")
            return
        self._duplicate_ids(checked)

    def adjust_stock_checked(self):
        checked = self.get_checked_ids()
        if len(checked) != 1:
            QMessageBox.warning(self, "알림", "재고 조정은 한 번에 한 품목만 가능합니다.\n체크박스에서 1개만 선택해주세요.")
            return
        product = next((p for p in db.get_products() if p["id"] == checked[0]), None)
        if not product:
            return
        dialog = StockAdjustDialog(product, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _delete_ids(self, ids):
        if confirm_delete(
                self, f"품목 {len(ids):,}개",
                "품목에 쌓인 재고·원가 정보가 함께 사라지고, 연결돼 있던 주문은 원가 미반영 상태가 됩니다.",
                double_check=len(ids) >= 5):
            try:
                for pid in ids:
                    db.delete_product(pid)
                matching.rematch_all_orders()
                notify_data_changed()
            except Exception as e:
                QMessageBox.critical(
                    self, "오류",
                    f"삭제 중 오류가 발생했습니다:\n{e}\n\n"
                    "(삭제 자체는 이미 반영됐을 수 있습니다 - 새로고침해서 확인해주세요)"
                )
            finally:
                self.refresh()

    def _duplicate_ids(self, ids):
        products = {p["id"]: p for p in db.get_products()}
        for pid in ids:
            p = products.get(pid)
            if p:
                db.add_product(p["sku"], p["name"] + " (복사본)", p["cost_price"],
                                p["sale_price"], p["stock_qty"], p["memo"], option_name=p["option_name"])
        notify_data_changed()
        self.refresh()


# ---------------------------------------------------------------------------
# 정산/지출 관리 탭
# ---------------------------------------------------------------------------
class SettlementDetailDialog(QDialog):
    """채널 정산 입금 리스트에서 더블클릭하면 뜨는 상세보기"""

    def __init__(self, settlement, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"정산입금 상세 - {settlement['channel_name']}")
        self.resize(420, 300)

        layout = QVBoxLayout(self)
        title = QLabel(f"💰 {settlement['channel_name']} 정산입금 상세")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        info = QFormLayout()
        info.addRow("채널/거래처", QLabel(settlement["channel_name"] or ""))
        info.addRow("입금일", QLabel(settlement["settle_date"] or ""))
        info.addRow("입금액", QLabel(fmt_won(settlement["amount"])))
        info.addRow("입금방법", QLabel(settlement["payment_method"] or "현금"))
        if settlement["payment_method"] == "통장":
            bank_display = settlement["bank_name"] or settlement["bank_account_name"] or ""
            info.addRow("입금 통장", QLabel(bank_display))
        info.addRow("메모", QLabel(settlement["memo"] or ""))
        # 해당 채널의 누적 정산 총액 및 미수금
        try:
            ch_id = settlement["channel_id"]
            total_settled = sum(s["amount"] for s in db.get_settlements()
                                if s["channel_id"] == ch_id)
            unsettled_list = [r for r in db.get_channel_unsettled_summary()
                              if r["channel_id"] == ch_id]
            unsettled = unsettled_list[0]["unsettled"] if unsettled_list else 0
            info.addRow("──────────", QLabel(""))
            lbl = QLabel(fmt_won(total_settled))
            lbl.setStyleSheet("font-weight: bold; color: #1A5276;")
            info.addRow("정산 총 입금액(누계)", lbl)
            lbl2 = QLabel(fmt_won(unsettled))
            lbl2.setStyleSheet("font-weight: bold; color: #C0392B;")
            info.addRow("현재 미수금", lbl2)
        except Exception:
            pass
        layout.addLayout(info)

        layout.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class SettlementTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)

        # 왼쪽: 지출 관리 (상단: 매입 지출 / 하단: 경비 지출)
        expense_col = QVBoxLayout()
        expense_title = QLabel("💸 지출 관리")
        expense_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        expense_col.addWidget(expense_title)

        # 지출 리스트는 기본적으로 이번 달 것만 보여줌 (월 단위로 관리하는 게 편해서)
        month_row = QHBoxLayout()
        self.expense_month = make_date_edit()
        self.expense_month.setDisplayFormat("yyyy-MM")
        self.expense_month.setDate(QDate.currentDate())
        self.expense_month.setFixedWidth(120)
        month_row.addWidget(tight_pair("조회 월:", self.expense_month))
        month_search_btn = QPushButton("조회")
        month_search_btn.clicked.connect(self.refresh)
        month_row.addWidget(month_search_btn)
        prev_month_btn = QPushButton("◀ 이전달")
        prev_month_btn.clicked.connect(lambda: self._shift_expense_month(-1))
        month_row.addWidget(prev_month_btn)
        next_month_btn = QPushButton("다음달 ▶")
        next_month_btn.clicked.connect(lambda: self._shift_expense_month(1))
        month_row.addWidget(next_month_btn)
        month_row.addStretch()
        expense_col.addLayout(month_row)

        # ---------- 상단: 매입 지출 (거래처 결제) ----------
        purchase_pay_box = QGroupBox("📦 매입 지출 등록 (입고/매입 대금 결제)")
        purchase_pay_layout = QVBoxLayout(purchase_pay_box)
        pp_form = QFormLayout()
        pp_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self.pp_supplier_id = None  # 선택된 거래처 id (드롭다운 대신 선택버튼으로 지정)
        self.pp_supplier_display = QLineEdit()
        self.pp_supplier_display.setReadOnly(True)
        self.pp_supplier_display.setPlaceholderText("오른쪽 '거래처 선택' 버튼으로 골라주세요")
        self.pp_supplier_display.setFixedWidth(220)
        pp_supplier_row = QWidget()
        pp_supplier_row_layout = QHBoxLayout(pp_supplier_row)
        pp_supplier_row_layout.setContentsMargins(0, 0, 0, 0)
        pp_supplier_row_layout.addWidget(self.pp_supplier_display)
        pp_pick_supplier_btn = QPushButton("📋 거래처 선택")
        pp_pick_supplier_btn.clicked.connect(self.pick_pp_supplier)
        pp_supplier_row_layout.addWidget(pp_pick_supplier_btn)
        pp_add_supplier_btn = QPushButton("➕ 새 거래처")
        pp_add_supplier_btn.clicked.connect(self.add_pp_supplier)
        pp_supplier_row_layout.addWidget(pp_add_supplier_btn)
        pp_supplier_row_layout.addStretch()
        pp_form.addRow("거래처 *", pp_supplier_row)

        self.pp_method_combo = QComboBox()
        self.pp_method_combo.addItems(["통장", "카드", "현금"])
        self.pp_method_combo.setFixedWidth(90)
        self.pp_method_combo.currentTextChanged.connect(self._on_pp_method_changed)
        self.pp_bank_combo = QComboBox()
        self.pp_bank_combo.setFixedWidth(200)
        self.pp_card_combo = QComboBox()
        self.pp_card_combo.setFixedWidth(200)
        pp_bank_row = QWidget()
        pp_bank_row_layout = QHBoxLayout(pp_bank_row)
        pp_bank_row_layout.setContentsMargins(0, 0, 0, 0)
        pp_bank_row_layout.addWidget(self.pp_method_combo)
        pp_bank_row_layout.addWidget(self.pp_bank_combo)
        pp_bank_row_layout.addWidget(self.pp_card_combo)
        pp_manage_bank_btn = QPushButton("🏦 통장 관리")
        pp_manage_bank_btn.clicked.connect(self.open_bank_management)
        pp_bank_row_layout.addWidget(pp_manage_bank_btn)
        pp_manage_card_btn = QPushButton("💳 카드 관리")
        pp_manage_card_btn.clicked.connect(self.open_card_management)
        pp_bank_row_layout.addWidget(pp_manage_card_btn)
        pp_bank_row_layout.addStretch()
        pp_form.addRow("결제방법", pp_bank_row)

        self.pp_date = make_date_edit()
        self.pp_date.setDate(QDate.currentDate())
        pp_form.addRow("결제일", self.pp_date)

        self.pp_amount = QLineEdit()
        self.pp_amount.setFixedWidth(200)
        self.pp_amount.textChanged.connect(lambda _: self._calc_pp_discount())
        pp_amount_row = QWidget()
        pp_amount_row_layout = QHBoxLayout(pp_amount_row)
        pp_amount_row_layout.setContentsMargins(0, 0, 0, 0)
        pp_amount_row_layout.addWidget(self.pp_amount)
        for preset in (1000, 10000, 100000):
            preset_btn = QPushButton(f"+{preset:,}")
            preset_btn.setFixedWidth(60)
            preset_btn.clicked.connect(lambda checked, a=preset: self._add_quick_amount(self.pp_amount, a))
            pp_amount_row_layout.addWidget(preset_btn)
        self.pp_amount.textChanged.connect(self._apply_purchase_discount)
        self.pp_discount_input = QLineEdit()
        self.pp_discount_input.setFixedWidth(70)
        self.pp_discount_input.setPlaceholderText("예: 3")
        self.pp_discount_input.textChanged.connect(self._apply_purchase_discount)
        pp_amount_row_layout.addWidget(QLabel("  할인율(%)"))
        pp_amount_row_layout.addWidget(self.pp_discount_input)
        self.pp_discount_hint = QLabel("")
        self.pp_discount_hint.setStyleSheet("color: #1A5276;")
        pp_amount_row_layout.addWidget(self.pp_discount_hint)

        pp_unpaid_btn = QPushButton("📋 미결제 내역")
        pp_unpaid_btn.setToolTip("선택된 거래처의 미결제 입고건을 보고 금액을 고를 수 있어요")
        pp_unpaid_btn.clicked.connect(self.pick_unpaid_amount)
        pp_amount_row_layout.addWidget(pp_unpaid_btn)
        pp_amount_row_layout.addStretch()
        pp_form.addRow("결제금액", pp_amount_row)

        # 공급가액 기준 할인(일부 거래처에서 3~5% 깎아주는 경우) 처리
        self.pp_discount_rate = QLineEdit("0")
        self.pp_discount_rate.setFixedWidth(70)
        self.pp_discount_rate.setPlaceholderText("예: 3")
        self.pp_discount_rate.textChanged.connect(self._calc_pp_discount)
        self.pp_discount_label = QLabel("")
        self.pp_discount_label.setStyleSheet("color: #1A5276;")
        disc_row = QWidget()
        disc_layout = QHBoxLayout(disc_row)
        disc_layout.setContentsMargins(0, 0, 0, 0)
        disc_layout.addWidget(self.pp_discount_rate)
        disc_layout.addWidget(QLabel("%"))
        disc_layout.addWidget(self.pp_discount_label)
        disc_layout.addStretch()
        pp_form.addRow("할인율(공급가액 기준)", disc_row)

        self.pp_memo = QLineEdit()
        self.pp_memo.setFixedWidth(280)
        pp_form.addRow("메모", self.pp_memo)
        purchase_pay_layout.addLayout(pp_form)

        pp_save_btn = QPushButton("➕ 매입 지출 등록")
        pp_save_btn.clicked.connect(self.save_purchase_payment)
        purchase_pay_layout.addWidget(pp_save_btn)

        pp_action_row = QHBoxLayout()
        pp_delete_btn = QPushButton("🗑️ 선택 삭제")
        pp_delete_btn.setStyleSheet("color: red;")
        pp_delete_btn.clicked.connect(self.delete_checked_purchase_payments)
        pp_action_row.addWidget(pp_delete_btn)
        pp_action_row.addStretch()
        purchase_pay_layout.addLayout(pp_action_row)

        self.pp_table = QTableWidget()
        self.pp_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pp_table.setMinimumHeight(140)
        purchase_pay_layout.addWidget(self.pp_table)

        expense_col.addWidget(purchase_pay_box)

        # ---------- 하단: 경비 지출 (광고비/포장비 등 일반 경비) ----------
        self.exp_editing_id = None  # 수정 모드일 때 해당 지출 id

        exp_form_box = QGroupBox("💸 경비 지출 등록 (광고비/포장비 등 일반 경비)")
        exp_form = QFormLayout(exp_form_box)
        exp_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self.exp_date = make_date_edit()
        self.exp_date.setDate(QDate.currentDate())
        self.exp_category = QComboBox()
        self._reload_expense_categories()
        self.exp_category.currentTextChanged.connect(self._fill_last_expense_amount)
        exp_category_row = QWidget()
        exp_category_row_layout = QHBoxLayout(exp_category_row)
        exp_category_row_layout.setContentsMargins(0, 0, 0, 0)
        exp_category_row_layout.addWidget(self.exp_category, stretch=1)
        add_category_btn = QPushButton("➕")
        add_category_btn.setToolTip("새 지출 항목 추가")
        add_category_btn.setFixedWidth(30)
        add_category_btn.clicked.connect(self.add_expense_category)
        exp_category_row_layout.addWidget(add_category_btn)
        remove_category_btn = QPushButton("🗑️")
        remove_category_btn.setToolTip("선택된 지출 항목 삭제")
        remove_category_btn.setFixedWidth(30)
        remove_category_btn.clicked.connect(self.remove_expense_category)
        exp_category_row_layout.addWidget(remove_category_btn)

        self.exp_amount = QLineEdit()
        self.exp_amount.setFixedWidth(200)
        exp_amount_row = QWidget()
        exp_amount_row_layout = QHBoxLayout(exp_amount_row)
        exp_amount_row_layout.setContentsMargins(0, 0, 0, 0)
        exp_amount_row_layout.addWidget(self.exp_amount)
        for preset in (1000, 10000, 100000):
            preset_btn = QPushButton(f"+{preset:,}")
            preset_btn.setFixedWidth(60)
            preset_btn.clicked.connect(lambda checked, a=preset: self._add_quick_amount(self.exp_amount, a))
            exp_amount_row_layout.addWidget(preset_btn)
        exp_amount_row_layout.addStretch()

        self.exp_bank_combo = QComboBox()
        self.exp_bank_combo.setFixedWidth(200)
        self.exp_memo = QLineEdit()
        self.exp_memo.setFixedWidth(280)
        # 지출방법: 통장/카드/현금 - 고른 것에 따라 통장 목록 또는 카드 목록이 나옴
        self.exp_method_combo = QComboBox()
        self.exp_method_combo.addItems(["통장", "카드", "현금"])
        self.exp_method_combo.setFixedWidth(90)
        self.exp_method_combo.currentTextChanged.connect(self._on_exp_method_changed)
        self.exp_card_combo = QComboBox()
        self.exp_card_combo.setFixedWidth(200)
        exp_method_row = QWidget()
        exp_method_layout = QHBoxLayout(exp_method_row)
        exp_method_layout.setContentsMargins(0, 0, 0, 0)
        exp_method_layout.addWidget(self.exp_method_combo)
        exp_method_layout.addWidget(self.exp_bank_combo)
        exp_method_layout.addWidget(self.exp_card_combo)
        manage_card_btn = QPushButton("💳 카드 관리")
        manage_card_btn.clicked.connect(self.open_card_management)
        exp_method_layout.addWidget(manage_card_btn)
        exp_method_layout.addStretch()

        exp_form.addRow("날짜", self.exp_date)
        exp_form.addRow("항목", exp_category_row)
        exp_form.addRow("금액", exp_amount_row)
        exp_form.addRow("지출방법", exp_method_row)
        exp_form.addRow("메모", self.exp_memo)

        self.exp_save_btn = QPushButton("등록")
        self.exp_save_btn.clicked.connect(self.save_expense)
        exp_form.addRow(self.exp_save_btn)

        self.exp_cancel_btn = QPushButton("편집 취소")
        self.exp_cancel_btn.clicked.connect(self.cancel_expense_edit)
        self.exp_cancel_btn.hide()
        exp_form.addRow(self.exp_cancel_btn)

        expense_col.addWidget(exp_form_box)

        exp_action_box = QGroupBox("선택 항목 관리 (표 왼쪽 체크박스로 선택)")
        exp_action_layout = QHBoxLayout(exp_action_box)
        exp_edit_btn = QPushButton("✏️ 수정")
        exp_edit_btn.clicked.connect(self.edit_checked_expense)
        exp_action_layout.addWidget(exp_edit_btn)
        exp_delete_btn = QPushButton("🗑️ 삭제")
        exp_delete_btn.setStyleSheet("color: red;")
        exp_delete_btn.clicked.connect(self.delete_checked_expenses)
        exp_action_layout.addWidget(exp_delete_btn)
        expense_col.addWidget(exp_action_box)

        self.exp_table = QTableWidget()
        self.exp_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.exp_table.cellDoubleClicked.connect(self.on_expense_double_clicked)
        enable_persistent_column_widths(self.exp_table, "expenses")
        self._exp_sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.exp_table, self._exp_sort_state, self.refresh, exclude_columns=(0,))
        expense_col.addWidget(self.exp_table, stretch=1)   # 좌우 표 높이를 같이 늘어나게

        self.pp_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        enable_persistent_column_widths(self.pp_table, "purchase_payments")
        self._pp_sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.pp_table, self._pp_sort_state, self.refresh, exclude_columns=(0,))
        self.reload_pp_suppliers()

        # 오른쪽: 정산 입금 관리
        settle_col = QVBoxLayout()
        settle_title_row = QHBoxLayout()
        settle_title = QLabel("💰 채널 정산 입금 관리")
        settle_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        settle_title_row.addWidget(settle_title)
        settle_title_row.addStretch()
        settle_upload_hist_btn = QPushButton("📋 업로드 이력")
        settle_upload_hist_btn.setToolTip("정산 파일 업로드 내역을 확인합니다")
        settle_upload_hist_btn.clicked.connect(self.show_settlement_upload_history)
        settle_title_row.addWidget(settle_upload_hist_btn)
        settle_col.addLayout(settle_title_row)

        upload_settlement_box = QGroupBox("📥 정산내역 파일 업로드 (마켓에서 다운받은 정산 파일)")
        upload_settlement_layout = QVBoxLayout(upload_settlement_box)
        upload_settlement_note = QLabel(
            "💡 주문번호, 구매자명, 상품명 중 하나라도 일치하는 주문을 찾아 '정산완료' 처리해요.\n"
            "매칭되면 채널별 입금액에도 자동으로 합산됩니다."
        )
        upload_settlement_note.setWordWrap(True)
        upload_settlement_note.setStyleSheet("color: #666;")
        upload_settlement_layout.addWidget(upload_settlement_note)
        upload_settlement_btn = QPushButton("📥 정산내역 파일 선택해서 업로드")
        upload_settlement_btn.clicked.connect(self.upload_settlement_file)
        upload_settlement_layout.addWidget(upload_settlement_btn)
        settle_col.addWidget(upload_settlement_box)

        status_box = QGroupBox("📊 채널별 정산 상태 요약")
        status_layout = QVBoxLayout(status_box)
        self.settlement_status_table = QTableWidget()
        self._settlement_status_sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.settlement_status_table, self._settlement_status_sort_state, self.refresh)
        self.settlement_status_table.setMinimumHeight(140)
        self.settlement_status_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.settlement_status_table.cellDoubleClicked.connect(self.on_status_double_clicked)
        status_layout.addWidget(self.settlement_status_table)
        settle_col.addWidget(status_box)

        settle_form_box = QGroupBox("정산 입금 수동 등록 (파일이 없을 때)")
        settle_form = QFormLayout(settle_form_box)
        settle_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self.settle_channel_id = None  # 선택된 채널/거래처 id (드롭다운 대신 선택버튼)
        self.settle_channel_display = QLineEdit()
        self.settle_channel_display.setReadOnly(True)
        self.settle_channel_display.setPlaceholderText("오른쪽 '채널/거래처 선택' 버튼으로 골라주세요")
        self.settle_channel_display.setFixedWidth(220)
        settle_channel_row = QWidget()
        settle_channel_row_layout = QHBoxLayout(settle_channel_row)
        settle_channel_row_layout.setContentsMargins(0, 0, 0, 0)
        settle_channel_row_layout.addWidget(self.settle_channel_display)
        settle_pick_btn = QPushButton("📋 채널/거래처 선택")
        settle_pick_btn.clicked.connect(self.pick_settle_channel)
        settle_channel_row_layout.addWidget(settle_pick_btn)
        settle_channel_row_layout.addStretch()
        self.settle_date = make_date_edit()
        self.settle_date.setDate(QDate.currentDate())
        self.settle_amount = QLineEdit()
        self.settle_amount.setFixedWidth(200)
        settle_amount_row = QWidget()
        settle_amount_row_layout = QHBoxLayout(settle_amount_row)
        settle_amount_row_layout.setContentsMargins(0, 0, 0, 0)
        settle_amount_row_layout.addWidget(self.settle_amount)
        for preset in (1000, 10000, 100000):
            preset_btn = QPushButton(f"+{preset:,}")
            preset_btn.setFixedWidth(60)
            preset_btn.clicked.connect(lambda checked, a=preset: self._add_quick_amount(self.settle_amount, a))
            settle_amount_row_layout.addWidget(preset_btn)
        settle_unpaid_btn = QPushButton("📋 미수금 내역")
        settle_unpaid_btn.setToolTip("선택된 채널/거래처의 미수금(미결제 주문)을 보고 금액을 고를 수 있어요")
        settle_unpaid_btn.clicked.connect(self.pick_unsettled_amount)
        settle_amount_row_layout.addWidget(settle_unpaid_btn)
        settle_amount_row_layout.addStretch()

        self.settle_method = QComboBox()
        self.settle_method.addItems(["통장"])   # 마켓 정산은 통장으로만 입금됨
        self.settle_method.setToolTip("정산금은 통장으로만 입금됩니다")
        self.settle_method.currentTextChanged.connect(self._toggle_settle_bank_visibility)

        self.settle_bank_combo = QComboBox()
        self.settle_bank_row = QWidget()
        settle_bank_row_layout = QHBoxLayout(self.settle_bank_row)
        settle_bank_row_layout.setContentsMargins(0, 0, 0, 0)
        settle_bank_row_layout.addWidget(self.settle_bank_combo, stretch=1)
        settle_manage_bank_btn = QPushButton("🏦 통장 관리")
        settle_manage_bank_btn.clicked.connect(self.open_bank_management)
        settle_bank_row_layout.addWidget(settle_manage_bank_btn)

        self.settle_memo = QLineEdit()
        self.settle_memo.setFixedWidth(280)
        settle_form.addRow("채널/거래처 *", settle_channel_row)
        settle_form.addRow("입금일", self.settle_date)
        settle_form.addRow("입금액", settle_amount_row)
        settle_form.addRow("입금방법", self.settle_method)
        settle_form.addRow("입금 통장", self.settle_bank_row)
        settle_form.addRow("메모", self.settle_memo)
        settle_add_btn = QPushButton("등록")
        settle_add_btn.clicked.connect(self.add_settlement)
        settle_form.addRow(settle_add_btn)
        settle_col.addWidget(settle_form_box)

        # 정산 입금 내역 조회기간 (기본: 이번달)
        st_ctrl = QHBoxLayout()
        _t = QDate.currentDate()
        self.settle_date_from = make_date_edit()
        self.settle_date_from.setDate(QDate(_t.year(), _t.month(), 1))
        self.settle_date_to = make_date_edit()
        self.settle_date_to.setDate(_t)
        st_ctrl.addWidget(tight_pair("시작일:", self.settle_date_from))
        st_ctrl.addWidget(tight_pair("종료일:", self.settle_date_to))
        st_btn = QPushButton("조회")
        st_btn.clicked.connect(self.refresh)
        st_ctrl.addWidget(st_btn)
        for _label, _fn in (("이번달", self._settle_this_month),
                            ("지난달", self._settle_last_month),
                            ("올해", self._settle_this_year),
                            ("전체", self._settle_all)):
            _b = QPushButton(_label)
            _b.clicked.connect(_fn)
            st_ctrl.addWidget(_b)
        st_ctrl.addStretch()
        settle_col.addLayout(st_ctrl)

        self.settle_table = QTableWidget()
        self.settle_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.settle_table.cellDoubleClicked.connect(self.on_settlement_double_clicked)
        self._settle_sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.settle_table, self._settle_sort_state, self.refresh)
        settle_col.addWidget(self.settle_table, stretch=1)

        # 좌우 폭을 같게 맞춰서 화면이 한쪽으로 쏠리지 않게 함
        layout.addLayout(expense_col, stretch=1)
        layout.addLayout(settle_col, stretch=1)

        self.reload_bank_accounts()
        self.reload_cards()
        self._on_exp_method_changed(self.exp_method_combo.currentText())
        self._on_pp_method_changed(self.pp_method_combo.currentText())
        self._toggle_settle_bank_visibility(self.settle_method.currentText())
        self.refresh()

    # ---------- 매입 지출 (거래처 결제) ----------
    def reload_pp_suppliers(self):
        """거래처는 이제 드롭다운이 아니라 선택 버튼으로 고르므로 별도 갱신 불필요."""
        return

    def reload_settle_channels(self):
        """채널/거래처는 이제 드롭다운이 아니라 선택 버튼으로 고르므로 별도 갱신 불필요.
        (전역 새로고침에서 호출되는 자리를 유지하기 위해 남겨둠)"""
        return

    def pick_settle_channel(self):
        dialog = ChannelPickerDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_channel:
            self.settle_channel_id = dialog.selected_channel["id"]
            self.settle_channel_display.setText(dialog.selected_channel["name"])
            # 그 채널에 지정해둔 정산 통장이 있으면 자동으로 골라줌
            bank_id = db.get_channel_settle_bank(self.settle_channel_id)
            if bank_id:
                idx = self.settle_bank_combo.findData(bank_id)
                if idx >= 0:
                    self.settle_bank_combo.setCurrentIndex(idx)

    def reload_bank_accounts(self):
        for combo in (self.pp_bank_combo, self.exp_bank_combo, self.settle_bank_combo):
            current = combo.currentData()
            combo.clear()
            combo.addItem("(선택 안 함)", None)
            for a in db.get_bank_accounts():
                display_name = a["bank_name"] or a["name"]
                combo.addItem(display_name, a["id"])
            if current:
                idx = combo.findData(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def reload_cards(self):
        for combo in (self.exp_card_combo, self.pp_card_combo):
            current = combo.currentData()
            combo.clear()
            combo.addItem("(선택 안 함)", None)
            for card in db.get_cards():
                label = f"{card['name']}" + (f" ({card['card_company']})" if card["card_company"] else "")
                combo.addItem(label, card["id"])
            if current:
                idx = combo.findData(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def _on_exp_method_changed(self, method):
        """지출방법에 따라 통장 목록 / 카드 목록 중 알맞은 것만 보여줌"""
        self.exp_bank_combo.setVisible(method == "통장")
        self.exp_card_combo.setVisible(method == "카드")

    def _on_pp_method_changed(self, method):
        self.pp_bank_combo.setVisible(method == "통장")
        self.pp_card_combo.setVisible(method == "카드")

    def open_card_management(self):
        CardManagementDialog(self).exec()
        self.reload_cards()
        self.refresh()

    def _toggle_settle_bank_visibility(self, method_text):
        self.settle_bank_row.setEnabled(method_text == "통장")

    def pick_pp_supplier(self):
        dialog = SupplierPickerDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_supplier:
            self.pp_supplier_id = dialog.selected_supplier["id"]
            self.pp_supplier_display.setText(dialog.selected_supplier["name"])

    def add_pp_supplier(self):
        dialog = NewChannelDialog(self)
        dialog.stack.setCurrentIndex(2)  # 일반 거래업체 상세입력으로 바로 이동
        if dialog.exec() == QDialog.Accepted and dialog.result_channel_id:
            self.pp_supplier_id = dialog.result_channel_id
            supplier = next((s for s in db.get_suppliers() if s["id"] == dialog.result_channel_id), None)
            if supplier:
                self.pp_supplier_display.setText(supplier["name"])

    def _calc_pp_discount(self):
        """결제금액 칸에 적은 금액을 '공급가액'으로 보고, 할인율만큼 깎은
        실제 송금액을 미리 보여줌 (매입채무는 할인 전 공급가액만큼 없어짐)"""
        supply = to_int(self.pp_amount.text(), 0)
        rate = to_float(self.pp_discount_rate.text(), 0)
        if supply <= 0 or rate <= 0:
            self.pp_discount_label.setText("")
            return
        discount = round(supply * rate / 100)
        self.pp_discount_label.setText(
            f"할인 {discount:,}원  →  실제 송금액 {supply - discount:,}원 "
            f"(매입채무는 {supply:,}원 차감)")

    def _apply_purchase_discount(self):
        """공급가액 기준 할인율을 넣으면 실제 결제할 금액을 계산해서 보여줌.
        (일부 거래처가 3~5% 깎아주는 경우 대응 - 결제금액은 할인 후 금액으로 등록되고,
         메모에 '공급가 OOO원 / 할인 O% (OOO원)' 형태로 남습니다)"""
        if not hasattr(self, "pp_discount_hint"):
            return
        base = to_int(self.pp_amount.text(), 0)
        try:
            rate = float(self.pp_discount_input.text().strip() or 0)
        except ValueError:
            rate = 0
        if base <= 0 or rate <= 0:
            self.pp_discount_hint.setText("")
            self._pp_discount_info = None
            return
        discount = round(base * rate / 100)
        payable = base - discount
        self.pp_discount_hint.setText(f"→ 실제 결제 {payable:,}원 (할인 {discount:,}원)")
        self._pp_discount_info = (base, rate, discount, payable)

    def pick_unpaid_amount(self):
        supplier_id = self.pp_supplier_id
        if supplier_id is None:
            QMessageBox.warning(self, "알림", "먼저 거래처를 선택해주세요.")
            return
        supplier_name = self.pp_supplier_display.text()
        dialog = UnpaidPurchaseAmountPickerDialog(supplier_id, supplier_name, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_amount is not None:
            self.pp_amount.setText(str(dialog.selected_amount))

    def pick_unsettled_amount(self):
        channel_id = self.settle_channel_id
        if channel_id is None:
            QMessageBox.warning(self, "알림", "먼저 채널/거래처를 선택해주세요.")
            return
        channel_name = self.settle_channel_display.text()
        dialog = UnsettledOrderAmountPickerDialog(channel_id, channel_name, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_amount is not None:
            self.settle_amount.setText(str(dialog.selected_amount))

    def on_status_double_clicked(self, row, column):
        """채널 정산상태 요약에서 채널을 더블클릭하면 그 채널의 거래원장 상세를 보여줌"""
        ids = getattr(self, "_status_channel_ids", [])
        if row < 0 or row >= len(ids):
            return
        channel_id, channel_name = ids[row]
        ReceivableDetailDialog(channel_id, channel_name, self).exec()

    def show_settlement_upload_history(self):
        """정산 파일 업로드 이력 창"""
        dialog = QDialog(self)
        dialog.setWindowTitle("정산 파일 업로드 이력")
        dialog.resize(820, 430)
        layout = QVBoxLayout(dialog)
        t = QLabel("📋 정산 파일 업로드 이력")
        t.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(t)
        note = QLabel("💡 삭제할 때 '업로드 내역만 지울지', '이 파일로 등록된 정산 입금 내역까지 "
                      "함께 지울지' 고를 수 있어요.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        layout.addWidget(note)

        table = QTableWidget()
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        hist = []

        def _load():
            nonlocal hist
            try:
                hist = db.get_settlement_uploads()
                rows = []
                for h in hist:
                    linked_cnt, linked_amt = db.get_settlement_upload_linked_count(h["id"])
                    rows.append((
                        h["filename"], h["channel_name"] or "", h["uploaded_at"],
                        f"{h['row_count'] or 0}건",
                        f"{h['file_total']:,}원" if h["file_total"] else "-",
                        f"{linked_cnt}건" if linked_cnt else "-",
                        fmt_won(linked_amt) if linked_cnt else "-",
                    ))
                fill_table(table,
                           ["파일명", "채널", "업로드 일시", "건수", "파일 정산합계",
                            "연결된 정산내역", "정산 입금액"],
                           rows)
            except Exception as e:
                hist = []
                fill_table(table, ["오류"], [(str(e),)])

        _load()
        layout.addWidget(table)

        def _delete_selected():
            r = table.currentRow()
            if r < 0 or r >= len(hist):
                QMessageBox.warning(dialog, "알림", "삭제할 업로드 내역을 선택해주세요.")
                return
            row = hist[r]
            linked_cnt, linked_amt = db.get_settlement_upload_linked_count(row["id"])

            box = QMessageBox(dialog)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("⚠️ 정산 업로드 내역 삭제")
            box.setText(f"<b style='font-size:15px; color:#C0392B;'>'{row['filename']}'</b><br>"
                        f"이 파일로 등록된 정산 입금 내역: "
                        f"<b>{linked_cnt:,}건 / {fmt_won(linked_amt)}</b>")
            box.setInformativeText(
                "⚠️ 이 작업은 <b>되돌릴 수 없습니다.</b><br><br>"
                "· <b>[업로드 내역만 삭제]</b> 이력만 지우고, 등록된 정산 입금 내역은 그대로 둡니다<br>"
                "· <b>[업로드 내역 + 정산내역 삭제]</b> 이 파일로 만들어진 정산 입금 내역까지 지웁니다 "
                "(통장으로 입금 처리했던 금액은 잔액에서 되돌립니다)<br><br>"
                + ("<span style='color:#C0392B;'>연결된 정산내역이 없어서 '정산내역까지 삭제'를 "
                   "골라도 이력만 지워집니다.</span><br><br>" if not linked_cnt else "")
                + "걱정되면 먼저 <b>설정 &gt; 데이터 백업하기</b>로 백업해두세요.")

            del_hist = box.addButton("업로드 내역만 삭제", QMessageBox.AcceptRole)
            del_all = box.addButton("업로드 내역 + 정산내역 삭제", QMessageBox.DestructiveRole)
            cancel_btn = box.addButton("취소", QMessageBox.RejectRole)
            box.setDefaultButton(cancel_btn)
            box.setEscapeButton(cancel_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked not in (del_hist, del_all):
                return

            delete_settlements = (clicked is del_all)
            if delete_settlements and linked_cnt:
                if not confirm_delete(
                        dialog, f"정산 입금 내역 {linked_cnt:,}건 ({fmt_won(linked_amt)})",
                        "삭제하면 통장 잔액에서 그만큼 다시 빠지고, 정산 현황/월별결산에서도 제외됩니다.",
                        extra_warning="입금으로 잡아둔 금액까지 통째로 지웁니다.",
                        title="🛑 마지막 확인"):
                    return
            try:
                deleted, reverted = db.delete_settlement_upload(
                    row["id"], delete_settlements=delete_settlements)
            except Exception as e:
                QMessageBox.critical(dialog, "오류", f"삭제 중 오류가 발생했습니다:\n{e}")
                return

            _load()
            self.refresh()
            notify_data_changed()
            if delete_settlements and deleted:
                QMessageBox.information(
                    dialog, "완료",
                    f"업로드 내역과 정산 입금 내역 {deleted:,}건을 삭제했습니다.\n"
                    f"통장 잔액에서 {fmt_won(reverted)}을 되돌렸습니다.")
            else:
                QMessageBox.information(dialog, "완료", "업로드 내역만 삭제했습니다.")

        btn_row = QHBoxLayout()
        del_btn = QPushButton("🗑️ 선택 삭제")
        del_btn.setToolTip("업로드 내역만 지울지, 연결된 정산내역까지 지울지 선택할 수 있어요")
        del_btn.clicked.connect(_delete_selected)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dialog.exec()

    def _settle_set_range(self, d_from, d_to):
        self.settle_date_from.setDate(d_from)
        self.settle_date_to.setDate(d_to)
        self.refresh()

    def _settle_this_month(self):
        t = QDate.currentDate()
        self._settle_set_range(QDate(t.year(), t.month(), 1), t)

    def _settle_last_month(self):
        t = QDate.currentDate()
        end = QDate(t.year(), t.month(), 1).addDays(-1)
        self._settle_set_range(QDate(end.year(), end.month(), 1), end)

    def _settle_this_year(self):
        t = QDate.currentDate()
        self._settle_set_range(QDate(t.year(), 1, 1), t)

    def _settle_all(self):
        self._settle_set_range(QDate(2000, 1, 1), QDate.currentDate())

    def on_settlement_double_clicked(self, row, column):
        if row < 0 or row >= len(self._settlements):
            return
        dialog = SettlementDetailDialog(self._settlements[row], self)
        dialog.exec()

    def open_bank_management(self):
        dialog = BankAccountManagementDialog(self)
        dialog.exec()
        self.reload_bank_accounts()
        self.refresh()

    def save_purchase_payment(self):
        supplier_id = self.pp_supplier_id
        if supplier_id is None:
            QMessageBox.warning(self, "알림", "거래처를 선택하거나 등록해주세요.")
            return
        amount_text = self.pp_amount.text().strip().replace(",", "")
        if not amount_text.isdigit() or int(amount_text) <= 0:
            QMessageBox.warning(self, "알림", "결제금액을 올바르게 입력해주세요.")
            return
        amount = int(amount_text)
        method = self.pp_method_combo.currentText()
        bank_account_id = self.pp_bank_combo.currentData() if method == "통장" else None
        card_id = self.pp_card_combo.currentData() if method == "카드" else None
        if method == "통장" and not bank_account_id:
            QMessageBox.warning(self, "알림", "결제방법이 '통장'이면 통장을 선택해주세요.")
            return
        if method == "카드" and not card_id:
            QMessageBox.warning(self, "알림", "결제방법이 '카드'면 카드를 선택해주세요.")
            return

        try:
            rate = to_float(self.pp_discount_rate.text(), 0)
            discount = round(amount * rate / 100) if rate > 0 else 0
            actual_paid = amount - discount     # 실제로 나간 돈
            db.add_purchase_payment(
                supplier_id, self.pp_date.date().toString("yyyy-MM-dd"),
                actual_paid, bank_account_id, self.pp_memo.text().strip(),
                payment_method=method, card_id=card_id,
                supply_amount=amount, discount_rate=rate, discount_amount=discount,
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"매입 지출 등록 중 오류가 발생했습니다:\n{e}")
            return
        finally:
            self.pp_amount.clear()
            self.pp_memo.clear()
            self.pp_discount_input.clear()
            self.pp_discount_hint.setText("")
            self._pp_discount_info = None
            self.pp_discount_rate.setText("0")
            self.pp_discount_label.setText("")
            self.pp_supplier_id = None       # 등록 후 다시 빈칸으로
            self.pp_supplier_display.clear()
            self.pp_bank_combo.setCurrentIndex(0)
            self.reload_bank_accounts()
            self.refresh()
            notify_data_changed()
        QMessageBox.information(self, "완료", "매입 지출이 등록되었습니다. 오래된 입고건부터 자동으로 충당됐어요.")

    def get_checked_pp_ids(self):
        checked = []
        for r in range(self.pp_table.rowCount()):
            if is_row_checked(self.pp_table, r):
                checked.append(self._pp_ids[r])
        return checked

    def delete_checked_purchase_payments(self):
        checked = self.get_checked_pp_ids()
        if not checked:
            QMessageBox.warning(self, "알림", "삭제할 항목을 체크박스에서 선택해주세요.")
            return
        if confirm_delete(
                self, f"매입 지출 기록 {len(checked):,}건",
                "통장 잔액은 복원되지만, 이미 입고건에 충당된 지급액은 자동으로 되돌아가지 않아요. "
                "필요하면 입고관리에서 직접 조정해주세요.",
                double_check=len(checked) >= 10):
            try:
                for pid in checked:
                    db.delete_purchase_payment(pid)
            except Exception as e:
                QMessageBox.critical(self, "오류", f"삭제 중 오류가 발생했습니다:\n{e}")
            finally:
                self.reload_bank_accounts()
                self.refresh()
                notify_data_changed()

    # ---------- 지출: 등록/수정 ----------
    def _add_quick_amount(self, line_edit, amount):
        """금액 프리셋 버튼 - 클릭할 때마다 현재 입력된 금액에 더해짐"""
        current = line_edit.text().strip().replace(",", "")
        current_val = int(current) if current.lstrip("-").isdigit() else 0
        line_edit.setText(str(current_val + amount))

    def _fill_last_expense_amount(self, category):
        """지출 항목을 선택하면 그 항목으로 마지막에 지출했던 금액을 자동으로 채워줌"""
        if self.exp_editing_id is not None or category == "(선택 안 함)" or not category:
            return  # 수정 중이거나 플레이스홀더 선택시엔 건드리지 않음
        last_amount = db.get_last_expense_amount(category)
        if last_amount is not None:
            self.exp_amount.setText(str(last_amount))

    def _reload_expense_categories(self):
        current = self.exp_category.currentText() if self.exp_category.count() else None
        self.exp_category.clear()
        self.exp_category.addItem("(선택 안 함)")
        self.exp_category.addItems(db.get_expense_categories())
        if current and current != "(선택 안 함)":
            idx = self.exp_category.findText(current)
            if idx >= 0:
                self.exp_category.setCurrentIndex(idx)
        else:
            self.exp_category.setCurrentIndex(0)

    def add_expense_category(self):
        name, ok = QInputDialog.getText(self, "지출 항목 추가", "새 항목명을 입력하세요:")
        name = name.strip()
        if ok and name:
            db.add_expense_category(name)
            self._reload_expense_categories()
            idx = self.exp_category.findText(name)
            if idx >= 0:
                self.exp_category.setCurrentIndex(idx)

    def remove_expense_category(self):
        name = self.exp_category.currentText()
        if not name:
            return
        if confirm_delete(
                self, f"지출 항목 '{name}'",
                "목록에서만 빠지고, 이미 등록된 지출 내역의 항목명은 그대로 유지됩니다."):
            db.delete_expense_category(name)
            self._reload_expense_categories()

    def save_expense(self):
        amount = self.exp_amount.text().strip().replace(",", "")
        if not amount.lstrip("-").isdigit():
            QMessageBox.warning(self, "알림", "금액은 숫자로 입력해 주세요.")
            return
        date_str = self.exp_date.date().toString("yyyy-MM-dd")
        category = self.exp_category.currentText()
        if not category or category == "(선택 안 함)":
            QMessageBox.warning(self, "알림", "지출 항목을 선택해주세요.")
            return
        memo = self.exp_memo.text().strip()
        method = self.exp_method_combo.currentText()
        bank_account_id = self.exp_bank_combo.currentData() if method == "통장" else None
        card_id = self.exp_card_combo.currentData() if method == "카드" else None
        if method == "통장" and not bank_account_id:
            QMessageBox.warning(self, "알림", "지출방법이 '통장'이면 통장을 선택해주세요.")
            return
        if method == "카드" and not card_id:
            QMessageBox.warning(self, "알림", "지출방법이 '카드'면 카드를 선택해주세요.")
            return

        if self.exp_editing_id is not None:
            db.update_expense(self.exp_editing_id, date_str, category, int(amount), memo,
                              bank_account_id, payment_method=method, card_id=card_id)
            self.cancel_expense_edit()
        else:
            db.add_expense(date_str, category, int(amount), memo, bank_account_id,
                           payment_method=method, card_id=card_id)
            self.exp_amount.clear()
            self.exp_memo.clear()
            self.exp_bank_combo.setCurrentIndex(0)
            self.exp_category.setCurrentIndex(0)  # 다시 (선택 안 함)으로

        self.reload_bank_accounts()
        self.refresh()
        notify_data_changed()

    def start_expense_edit(self, eid):
        expenses = {e["id"]: e for e in db.get_expenses()}
        e = expenses.get(eid)
        if not e:
            return
        self.exp_editing_id = eid
        y, m, d = [int(x) for x in e["date"].split("-")]
        self.exp_date.setDate(QDate(y, m, d))
        idx = self.exp_category.findText(e["category"])
        if idx >= 0:
            self.exp_category.setCurrentIndex(idx)
        self.exp_amount.setText(str(e["amount"]))
        self.exp_memo.setText(e["memo"] or "")
        bank_idx = self.exp_bank_combo.findData(e["bank_account_id"])
        self.exp_bank_combo.setCurrentIndex(bank_idx if bank_idx >= 0 else 0)
        self.exp_save_btn.setText("💾 수정 저장")
        self.exp_cancel_btn.show()

    def cancel_expense_edit(self):
        self.exp_editing_id = None
        self.exp_amount.clear()
        self.exp_memo.clear()
        self.exp_bank_combo.setCurrentIndex(0)
        self.exp_save_btn.setText("등록")
        self.exp_cancel_btn.hide()

    # ---------- 지출: 표/체크박스 ----------
    def get_checked_expense_ids(self):
        checked = []
        for r in range(self.exp_table.rowCount()):
            if is_row_checked(self.exp_table, r):
                checked.append(self._expense_ids[r])
        return checked

    def on_expense_double_clicked(self, row, column):
        if column == 0 or row < 0 or row >= len(self._expense_ids):
            return
        eid = self._expense_ids[row]
        menu = QMenu(self)
        edit_action = menu.addAction("✏️ 수정")
        delete_action = menu.addAction("🗑️ 삭제")
        chosen = menu.exec(QCursor.pos())
        if chosen == edit_action:
            self.start_expense_edit(eid)
        elif chosen == delete_action:
            self._delete_expenses([eid])

    def edit_checked_expense(self):
        checked = self.get_checked_expense_ids()
        if len(checked) != 1:
            QMessageBox.warning(self, "알림", "수정은 한 번에 한 항목만 가능합니다.\n체크박스에서 1개만 선택해주세요.")
            return
        self.start_expense_edit(checked[0])

    def delete_checked_expenses(self):
        checked = self.get_checked_expense_ids()
        if not checked:
            QMessageBox.warning(self, "알림", "삭제할 항목을 체크박스에서 선택해주세요.")
            return
        self._delete_expenses(checked)

    def _delete_expenses(self, ids):
        if confirm_delete(
                self, f"지출 내역 {len(ids):,}건",
                "통장에서 나간 것으로 처리했던 금액은 통장 잔액으로 되돌아옵니다.",
                double_check=len(ids) >= 10):
            try:
                for eid in ids:
                    db.delete_expense(eid)
                if self.exp_editing_id in ids:
                    self.cancel_expense_edit()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"삭제 중 오류가 발생했습니다:\n{e}")
            finally:
                self.refresh()
                notify_data_changed()

    # ---------- 정산 입금 ----------
    def upload_settlement_file(self):
        filepath = ask_open_file(self, "정산내역 파일 선택",
                                 "엑셀/CSV 파일 (*.xlsx *.xls *.csv)", "settlement")
        if not filepath:
            return

        try:
            (rows, mapping, unmatched, columns, file_total,
             settle_style) = importer.parse_settlement_file(filepath)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일을 읽는 중 오류가 발생했습니다:\n{e}")
            return

        if not rows:
            QMessageBox.warning(self, "알림", "인식된 정산 데이터가 없습니다. 파일 형식을 확인해주세요.")
            return

        unsettled = db.get_unsettled_orders_for_matching()
        matches = []  # (order_id, settle_amount, settle_date)
        matched_by_no = 0
        matched_by_name = 0
        failed = 0
        matched_order_ids = set()

        # 배송비 줄은 '상품주문번호'가 주문과 달라서 따로 모아, 주문번호로 묶어 처리함
        # (스마트스토어 정산파일은 상품주문 / 배송비가 다른 줄로 나옴)
        shipping_rows = [r for r in rows if r.get("is_shipping")]
        rows = [r for r in rows if not r.get("is_shipping")]
        shipping_by_order = {}
        for sr in shipping_rows:
            key = (sr.get("parent_order_no") or "").strip()
            if key:
                shipping_by_order[key] = shipping_by_order.get(key, 0) + (sr["settle_amount"] or 0)
        shipping_total = sum(r["settle_amount"] or 0 for r in shipping_rows)
        shipping_applied = 0

        for row in rows:
            order_no = row["order_no"].strip()
            parent_no = (row.get("parent_order_no") or "").strip()
            matched_order = None

            # 1순위: 주문번호 완전일치
            if order_no:
                candidate = next((o for o in unsettled if o["order_no"] == order_no
                                   and o["id"] not in matched_order_ids), None)
                if candidate:
                    matched_order = candidate
                    matched_by_no += 1

            # 1-2순위: 상품주문번호로 못 찾으면 주문번호로 다시 찾음
            if not matched_order and parent_no and parent_no != order_no:
                candidate = next((o for o in unsettled if o["order_no"] == parent_no
                                   and o["id"] not in matched_order_ids), None)
                if candidate:
                    matched_order = candidate
                    matched_by_no += 1

            # 2순위: 구매자명 + 상품명 일치 (둘 다 있어야 함)
            if not matched_order and row["buyer_name"] and row["product_name"]:
                buyer_norm = row["buyer_name"].strip()
                product_norm = row["product_name"].strip().lower()
                candidate = next(
                    (o for o in unsettled if o["id"] not in matched_order_ids
                     and (o["buyer_name"] or "").strip() == buyer_norm
                     and product_norm in (o["product_name"] or "").lower()),
                    None
                )
                if candidate:
                    matched_order = candidate
                    matched_by_name += 1

            if matched_order:
                matched_order_ids.add(matched_order["id"])
                settle_amount = row["settle_amount"] or matched_order["settlement_amount"] or 0
                # 같은 주문번호로 들어온 배송비 정산액을 함께 더해줌
                # (예전엔 배송비 줄이 통째로 빠져서 실제 입금액보다 적게 잡혔음)
                for key in (parent_no, order_no):
                    if key and key in shipping_by_order:
                        add = shipping_by_order.pop(key)
                        settle_amount += add
                        shipping_applied += add
                        break
                settle_date = row["settle_date"] or date.today().strftime("%Y-%m-%d")
                matches.append((matched_order["id"], settle_amount, settle_date))
            else:
                failed += 1

        by_channel = {}
        if matches:
            db.mark_orders_settled(matches)
            # 채널별로 합산해서 정산입금 내역에도 반영 (리포트의 '정산 현황'과 일관성 유지)
            unsettled_map = {o["id"]: o for o in unsettled}
            for oid, amt, sdate in matches:
                order_info = unsettled_map.get(oid)
                ch_id = order_info["channel_id"] if order_info else None
                if ch_id:
                    by_channel[ch_id] = by_channel.get(ch_id, 0) + amt

        # 어느 주문에도 붙이지 못한 배송비가 남아있으면, 금액이 사라지지 않도록
        # 매칭된 채널의 정산액에 그대로 더해줌
        leftover_shipping = sum(shipping_by_order.values())
        if leftover_shipping and by_channel:
            main_ch = max(by_channel, key=by_channel.get)
            by_channel[main_ch] += leftover_shipping
            leftover_shipping = 0

        # 마켓에 따라 파일 합계와 실제 입금액이 다를 수 있어(쿠팡 주정산 70% 등)
        # 통장에 넣을 금액을 확인/조정할 수 있게 함
        calc_total = sum(by_channel.values()) + leftover_shipping
        deduct_amount, deduct_name, make_expense = 0, "", False
        # 스마트스토어처럼 파일에 적힌 금액이 곧 입금액인 정산파일은
        # 배송비까지 이미 들어있으므로 묻지 않고 그대로 처리함.
        # 쿠팡처럼 지급비율(70%)과 공제(광고비)가 있는 파일만 확인창을 띄움
        if calc_total and settle_style == "partial":
            dlg = SettlementDepositDialog(calc_total, parent=self)
            if dlg.exec() == QDialog.Accepted:
                actual, deduct_amount, deduct_name, make_expense = dlg.result()
                gap = actual - calc_total
                if gap:
                    # 채널이 여럿이면 금액이 가장 큰 채널에서 차액을 조정
                    if by_channel:
                        main_ch = max(by_channel, key=by_channel.get)
                        by_channel[main_ch] += gap
                    else:
                        leftover_shipping += gap

        # 정산 파일 업로드 이력을 "먼저" 만들어서 id를 확보한 뒤,
        # 이 업로드로 생기는 정산 입금 내역에 그 id를 붙여둠.
        # (나중에 업로드 내역을 지울 때 '정산내역까지 함께 삭제'를 고를 수 있게 하기 위함)
        upload_id = None
        try:
            upload_id = db.add_settlement_upload(
                os.path.basename(filepath),
                list(by_channel.keys())[0] if by_channel else None,
                len(rows), file_total)
        except Exception:
            upload_id = None

        for ch_id, total in by_channel.items():
            # 채널별로 지정된 정산 통장에 자동 입금 처리
            bank_id = db.get_channel_settle_bank(ch_id)
            db.add_settlement(
                ch_id, date.today().strftime("%Y-%m-%d"), total,
                "정산내역 파일 자동매칭",
                payment_method="통장" if bank_id else "현금",
                bank_account_id=bank_id,
                settlement_upload_id=upload_id)

        # 정산에서 미리 빠진 공제금액(광고비 등)을 지출로도 남김
        if make_expense and deduct_amount > 0:
            try:
                if deduct_name not in db.get_expense_categories():
                    db.add_expense_category(deduct_name)
                db.add_expense(
                    date.today().strftime("%Y-%m-%d"), deduct_name, deduct_amount,
                    memo="정산 공제분 (정산내역 파일 업로드)",
                    payment_method="정산공제")
            except Exception:
                pass

        self.refresh()
        notify_data_changed()

        # 정산 검증: 파일 정산금액 합계 vs 장부 매칭금액 합계
        matched_total = sum(amt for _, amt, _ in matches)
        diff = file_total - matched_total
        diff_pct = abs(diff / file_total * 100) if file_total else 0
        if diff_pct >= 1:
            diff_icon = "🔴"
        elif diff_pct > 0:
            diff_icon = "🟡"
        else:
            diff_icon = "✅"

        verify_msg = (
            f"\n\n📊 정산 검증\n"
            f"  파일 정산금액 합계: {file_total:,}원\n"
            f"  장부 매칭금액 합계: {matched_total:,}원\n"
            f"  차액: {diff:+,}원  {diff_icon}"
        )
        if shipping_total:
            verify_msg += (
                f"\n\n🚚 배송비 정산 (수수료 제외 순액)\n"
                f"  파일의 배송비 줄: {len(shipping_rows)}건 / {shipping_total:,}원\n"
                f"  주문에 반영된 금액: {shipping_applied:,}원"
                + (f"\n  주문을 못 찾아 채널 정산에 합산: {leftover_shipping:,}원"
                   if leftover_shipping else ""))
        if diff != 0:
            verify_msg += (
                f"\n  (차액 원인: 미매칭 {failed}건, "
                f"쿠팡 70%/30% 분할 등)")

        QMessageBox.information(
            self, "완료",
            f"정산 매칭 완료: 주문번호로 {matched_by_no}건, 구매자+상품명으로 {matched_by_name}건 "
            f"매칭되어 정산완료 처리했습니다."
            + (f"\n🚚 배송비 {len(shipping_rows)}건({shipping_total:,}원)도 함께 반영했습니다."
               if shipping_total else "")
            + (f"\n⚠️ {failed}건은 매칭되는 주문을 찾지 못했습니다." if failed else "")
            + verify_msg
        )

    def add_settlement(self):
        amount = self.settle_amount.text().strip().replace(",", "")
        if not amount.isdigit():
            QMessageBox.warning(self, "알림", "금액은 숫자로 입력해 주세요.")
            return
        channel_id = self.settle_channel_id
        if channel_id is None:
            QMessageBox.warning(self, "알림", "채널/거래처를 선택해주세요.")
            return
        method = self.settle_method.currentText()
        bank_account_id = self.settle_bank_combo.currentData() if method == "통장" else None
        if method == "통장" and not bank_account_id:
            QMessageBox.warning(self, "알림", "입금방법을 '통장'으로 선택했으면 통장도 골라주세요.")
            return
        settle_date_str = self.settle_date.date().toString("yyyy-MM-dd")
        db.add_settlement(
            channel_id, settle_date_str, int(amount),
            self.settle_memo.text().strip(),
            payment_method=method,
            bank_account_id=bank_account_id,
        )

        # 입금을 받았으면 그만큼 미수금 주문도 '정산완료'로 바꿔줌.
        # (예전엔 입금만 기록되고 주문은 미수금으로 남아서,
        #  이미 받은 돈인데 미수금 내역에 계속 떠 있었음)
        try:
            unsettled = [o for o in db.get_orders(channel_id=channel_id)
                         if not o["is_settled"]]
            unsettled.sort(key=lambda o: (o["order_date"] or "", o["id"]))
            remain = int(amount)
            matches = []
            for o in unsettled:
                amt = o["settlement_amount"] or 0
                if amt <= 0 or amt > remain:
                    continue
                matches.append((o["id"], amt, settle_date_str))
                remain -= amt
                if remain <= 0:
                    break
            if matches:
                covered = int(amount) - remain
                if QMessageBox.question(
                        self, "미수금 정산 처리",
                        f"입금 {fmt_won(int(amount))} 중 {fmt_won(covered)} 만큼\n"
                        f"미수금 주문 {len(matches)}건과 금액이 맞습니다.\n\n"
                        "이 주문들을 '정산완료'로 바꿀까요?\n"
                        "(바꾸면 미수금 내역에서 사라집니다)") == QMessageBox.Yes:
                    db.mark_orders_settled(matches)
        except Exception:
            pass

        show_save_toast(self)
        self.settle_amount.clear()
        self.settle_memo.clear()
        self.settle_channel_id = None
        self.settle_channel_display.clear()
        self.settle_bank_combo.setCurrentIndex(0)
        self.reload_bank_accounts()
        self.refresh()
        notify_data_changed()

    def _shift_expense_month(self, months):
        self.expense_month.setDate(self.expense_month.date().addMonths(months))
        self.refresh()

    def refresh(self):
        ym = self.expense_month.date().toString("yyyy-MM")
        expenses = db.get_expenses(year_month=ym)

        headers = ["선택", "날짜", "항목", "금액", "지출방법", "메모"]
        exp_display_rows = []
        for e in expenses:
            method = e["payment_method"] or "통장"
            if method == "통장":
                method_label = f"통장 - {e['bank_account_name']}" if e["bank_account_name"] else "통장"
            elif method == "카드":
                method_label = f"카드 - {e['card_name']}" if e["card_name"] else "카드"
            else:
                method_label = "현금"
            exp_display_rows.append((
                "", e["date"], e["category"], fmt_won(e["amount"]), method_label, e["memo"],
            ))
        exp_display_rows, expenses = apply_table_sort(exp_display_rows, expenses, self._exp_sort_state)
        self._expense_ids = [e["id"] for e in expenses]

        self.exp_table.setColumnCount(len(headers))
        self.exp_table.setHorizontalHeaderLabels(headers)
        self.exp_table.setRowCount(len(expenses))
        for r, values in enumerate(exp_display_rows):
            checkbox_container, _ = make_checkbox_cell()
            self.exp_table.setCellWidget(r, 0, checkbox_container)

            for c, val in enumerate(values):
                if c == 0:
                    continue
                text = str(val) if val is not None else ""
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if looks_numeric(text):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.exp_table.setItem(r, c, item)
        exp_header = self.exp_table.horizontalHeader()
        exp_header.blockSignals(True)
        self.exp_table.resizeColumnsToContents()
        exp_header.blockSignals(False)
        self.exp_table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)
        self.exp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.exp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        restore_column_widths(self.exp_table, "expenses")

        payments = db.get_purchase_payments(year_month=ym)
        headers_pp = ["선택", "결제일", "거래처", "결제금액", "결제방법", "메모"]
        pp_display_rows = []
        for p in payments:
            method = p["payment_method"] or "통장"
            if method == "통장":
                method_label = f"통장 - {p['bank_account_name']}" if p["bank_account_name"] else "통장"
            elif method == "카드":
                method_label = f"카드 - {p['card_name']}" if p["card_name"] else "카드"
            else:
                method_label = "현금"
            pp_display_rows.append((
                "", p["payment_date"], p["supplier_name"], fmt_won(p["amount"]),
                method_label, p["memo"],
            ))
        pp_display_rows, payments = apply_table_sort(pp_display_rows, payments, self._pp_sort_state)
        self._pp_ids = [p["id"] for p in payments]

        self.pp_table.setColumnCount(len(headers_pp))
        self.pp_table.setHorizontalHeaderLabels(headers_pp)
        self.pp_table.setRowCount(len(payments))
        for r, values in enumerate(pp_display_rows):
            checkbox_container, _ = make_checkbox_cell()
            self.pp_table.setCellWidget(r, 0, checkbox_container)
            for c, val in enumerate(values):
                if c == 0:
                    continue
                text = str(val) if val is not None else ""
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if looks_numeric(text):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.pp_table.setItem(r, c, item)
        pp_header = self.pp_table.horizontalHeader()
        pp_header.blockSignals(True)
        self.pp_table.resizeColumnsToContents()
        pp_header.blockSignals(False)
        self.pp_table.horizontalHeader().setStyleSheet(YELLOW_HEADER_STYLE)
        self.pp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.pp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        restore_column_widths(self.pp_table, "purchase_payments")

        settlements = db.get_settlements()
        # 채널별 현재 미수 잔액을 기준으로, 각 행 이후(최신→과거) 순으로 입금액을
        # 역산해서 입금 당시의 잔액을 계산
        current_unsettled = {r["channel_id"]: (r["unsettled"] or 0)
                             for r in db.get_channel_unsettled_summary()}
        # settlements는 최신순이므로 순서대로 역산
        running = dict(current_unsettled)
        st_from = self.settle_date_from.date().toString("yyyy-MM-dd")
        st_to = self.settle_date_to.date().toString("yyyy-MM-dd")
        settle_rows = []
        settle_ids = []
        for s in settlements:
            method = s["payment_method"] or "현금"
            method_label = s["bank_name"] or s["bank_account_name"] or "통장" if method == "통장" else "현금"
            ch_id = s["channel_id"]
            bal_after = running.get(ch_id, 0)   # 이 입금 후 잔액
            running[ch_id] = bal_after + (s["amount"] or 0)  # 입금 전 잔액(과거로 이동)
            # 잔액 역산은 전체 내역으로 하되, 화면에는 고른 기간만 보여줌
            d10 = (s["settle_date"] or "")[:10]
            if d10 and (d10 < st_from or d10 > st_to):
                continue
            settle_ids.append(s)
            settle_rows.append((
                s["channel_name"], s["settle_date"], method_label,
                fmt_won(s["amount"]), fmt_won(bal_after), s["memo"],
            ))
        self._settlements = fill_table(
            self.settle_table, ["업체명", "입금일", "입금방법", "입금액", "잔액(미수)", "메모"],
            settle_rows,
            persist_key="settlements", sort_state=self._settle_sort_state, id_list=settle_ids
        ) or settle_ids

        status_rows = [r for r in db.get_settlement_status_counts() if (r["settled_count"] or 0) + (r["unsettled_count"] or 0)]
        self._status_channel_ids = fill_table(
            self.settlement_status_table,
            ["채널", "정산완료", "미정산", "정산완료금액", "미정산금액"],
            [(r["channel_name"], f"{r['settled_count'] or 0}건", f"{r['unsettled_count'] or 0}건",
              fmt_won(r["settled_amount_total"]), fmt_won(r["unsettled_amount_total"]))
             for r in status_rows],
            persist_key="settlement_status_summary", sort_state=self._settlement_status_sort_state,
            id_list=[(r["channel_id"], r["channel_name"]) for r in status_rows]
        ) or [(r["channel_id"], r["channel_name"]) for r in status_rows]


# ---------------------------------------------------------------------------
# 리포트 탭
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 기간(일/월/년) 상세 내역 다이얼로그
# ---------------------------------------------------------------------------
class ProfitDetailDialog(QDialog):
    PERIOD_LABEL = {"day": "일별", "month": "월별", "year": "년도별"}

    def __init__(self, period_key, period, parent=None):
        super().__init__(parent)
        label = self.PERIOD_LABEL.get(period, "")
        self.setWindowTitle(f"{period_key} 상세내역 ({label})")
        self.resize(950, 600)

        layout = QVBoxLayout(self)
        title = QLabel(f"📅 {period_key} 주문 상세")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        rows = db.get_profit_detail(period_key, period)
        total_sales = sum((r["total_amount"] or 0) for r in rows)
        total_fee = sum((r["fee_amount"] or 0) for r in rows)
        total_profit = sum((r["profit"] or 0) for r in rows)
        unmatched = sum(1 for r in rows if r["matched_product_id"] is None)

        summary = QLabel(
            f"주문건수: {len(rows)}건   |   매출: {fmt_won(total_sales)}   |   "
            f"수수료: {fmt_won(total_fee)}   |   이익: {fmt_won(total_profit)}"
            + (f"   |   ⚠️ 품목 미매칭 {unmatched}건 (원가 0으로 계산됨)" if unmatched else "")
        )
        summary.setStyleSheet("padding: 6px; background: #f0f0f0;")
        layout.addWidget(summary)

        table = QTableWidget()
        headers = ["채널", "주문번호", "주문일", "상품명", "옵션", "수량",
                   "결제금액", "수수료", "매칭품목", "원가", "이익", "상태"]
        table_rows = [
            (r["channel_name"], r["order_no"], r["order_date"], r["product_name"], r["option_name"],
             r["qty"], fmt_won(r["total_amount"]), fmt_won(r["fee_amount"]),
             r["matched_product_name"] or "(미매칭)", fmt_won((r["cost_price"] or 0) * r["qty"]),
             fmt_won(r["profit"]), r["status"])
            for r in rows
        ]
        fill_table(table, headers, table_rows)
        layout.addWidget(table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# ---------------------------------------------------------------------------
# 리포트 - 서브탭 1: 기간별 이익 (일별/월별/년도별 + 더블클릭 상세)
# ---------------------------------------------------------------------------
class PeriodProfitTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        control_row = QHBoxLayout()
        control_row.addWidget(QLabel("보기 단위:"))
        self.period_combo = QComboBox()
        self.period_combo.addItem("일별", "day")
        self.period_combo.addItem("월별", "month")
        self.period_combo.addItem("년도별", "year")
        self.period_combo.currentIndexChanged.connect(self.refresh)
        control_row.addWidget(self.period_combo)

        self.date_from = make_date_edit()
        # 기본값: 이번달 1일 ~ 오늘
        self.date_from.setDate(QDate(QDate.currentDate().year(),
                                     QDate.currentDate().month(), 1))
        control_row.addWidget(tight_pair("시작일:", self.date_from))
        self.date_to = make_date_edit()
        self.date_to.setDate(QDate.currentDate())
        control_row.addWidget(tight_pair("종료일:", self.date_to))
        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh)
        control_row.addWidget(search_btn)
        this_week_btn = QPushButton("이번주")
        this_week_btn.clicked.connect(self._set_this_week)
        control_row.addWidget(this_week_btn)
        this_month_btn = QPushButton("이번달")
        this_month_btn.clicked.connect(self._set_this_month)
        control_row.addWidget(this_month_btn)
        last_month_btn = QPushButton("지난달")
        last_month_btn.clicked.connect(self._set_last_month)
        control_row.addWidget(last_month_btn)
        control_row.addStretch()

        export_btn = QPushButton("📄 엑셀로 내보내기")
        export_btn.clicked.connect(self.export_excel)
        control_row.addWidget(export_btn)
        layout.addLayout(control_row)

        note = QLabel("💡 행을 더블클릭하면 해당 기간의 주문 상세내역을 볼 수 있어요. "
                      "품목관리에 원가가 등록·매칭된 주문만 이익 계산에 반영됩니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_double_clicked)
        layout.addWidget(self.table)

        self._period_keys = []
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        enlarge_row_numbers(self.table)
        self.refresh()

    def current_period(self):
        return self.period_combo.currentData()

    def refresh(self):
        period = self.current_period()
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        rows = db.get_profit_by_period(period, date_from=date_from, date_to=date_to)
        period_keys = [r["period_key"] for r in rows]

        DAY_KO = ["(월)", "(화)", "(수)", "(목)", "(금)", "(토)", "(일)"]

        def fmt_period(key):
            if period != "day":
                return key
            try:
                d = QDate.fromString(key, "yyyy-MM-dd")
                return f"{key}  {DAY_KO[d.dayOfWeek() - 1]}"
            except Exception:
                return key

        headers = ["기간", "주문건수", "매출", "수수료", "원가", "배송비순수익", "이익", "이익률", "원가 미반영"]
        def fmt_rate(profit, sales):
            if not sales:
                return ""
            return f"{profit / sales * 100:.1f}%"

        table_rows = [
            (fmt_period(r["period_key"]), r["order_count"], fmt_won(r["total_sales"]),
             fmt_won(r["total_fee"]), fmt_won(r["total_cost"]),
             fmt_won(r["shipping_net"]), fmt_won(r["profit"]),
             fmt_rate(r["profit"] or 0, r["total_sales"] or 0),
             f"{r['unmatched_count']}건" if r["unmatched_count"] else "")
            for r in rows
        ]
        self._period_keys = fill_table(self.table, headers, table_rows, persist_key="period_profit",
                                        sort_state=self._sort_state, id_list=period_keys)
        # 리스트 하단에 합계 행 추가 (정렬 이후에 붙이므로 항상 맨 아래에 위치)
        if rows:
            total_count = sum(r["order_count"] or 0 for r in rows)
            total_sales = sum(r["total_sales"] or 0 for r in rows)
            total_fee = sum(r["total_fee"] or 0 for r in rows)
            total_cost = sum(r["total_cost"] or 0 for r in rows)
            total_ship = sum(r["shipping_net"] or 0 for r in rows)
            total_profit = sum(r["profit"] or 0 for r in rows)
            total_unmatched = sum(r["unmatched_count"] or 0 for r in rows)
            last = self.table.rowCount()
            self.table.insertRow(last)
            summary_values = ["■ 합계", f"{total_count:,}", fmt_won(total_sales), fmt_won(total_fee),
                              fmt_won(total_cost), fmt_won(total_ship), fmt_won(total_profit),
                              fmt_rate(total_profit, total_sales),
                              f"{total_unmatched}건" if total_unmatched else ""]
            for c, val in enumerate(summary_values):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setFont(QFont("", -1, QFont.Bold))
                item.setBackground(QColor("#EAF2F8"))
                if looks_numeric(str(val)):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(last, c, item)
            # 합계 행은 기간 키가 없으므로 더블클릭 대상에서 제외되도록 None을 채워둠
            self._period_keys = list(self._period_keys or []) + [None]

        # 요청하신 대로 컬럼 폭을 여유있게, 주문건수는 가운데 정렬로
        self.table.setColumnWidth(0, 160)  # 기간
        self.table.setColumnWidth(1, 90)   # 주문건수
        self.table.setColumnWidth(2, 140)  # 매출
        self.table.setColumnWidth(3, 110)  # 수수료
        self.table.setColumnWidth(4, 120)  # 원가
        self.table.setColumnWidth(5, 120)  # 배송비순수익
        self.table.setColumnWidth(6, 120)  # 이익
        self.table.setColumnWidth(7, 80)   # 이익률
        self.table.setColumnWidth(8, 100)  # 원가 미반영
        for r in range(self.table.rowCount()):
            for col in (0, 1, 7):
                it = self.table.item(r, col)
                if it:
                    it.setTextAlignment(Qt.AlignCenter)

    def _set_this_week(self):
        today = QDate.currentDate()
        self.date_from.setDate(today.addDays(-today.dayOfWeek() + 1))
        self.date_to.setDate(today)
        self.refresh()

    def _set_this_month(self):
        today = QDate.currentDate()
        self.date_from.setDate(QDate(today.year(), today.month(), 1))
        self.date_to.setDate(today)
        self.refresh()

    def _set_last_month(self):
        today = QDate.currentDate()
        first_this = QDate(today.year(), today.month(), 1)
        last_end = first_this.addDays(-1)
        self.date_from.setDate(QDate(last_end.year(), last_end.month(), 1))
        self.date_to.setDate(last_end)
        self.refresh()

    def on_double_clicked(self, row, column):
        if row < 0 or row >= len(self._period_keys):
            return
        period_key = self._period_keys[row]
        if period_key is None:   # 합계 행은 상세 조회 대상이 아님
            return
        dialog = ProfitDetailDialog(period_key, self.current_period(), self)
        dialog.exec()

    def export_excel(self):
        import pandas as pd
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        rows = db.get_profit_by_period(self.current_period(), date_from=date_from, date_to=date_to)
        if not rows:
            QMessageBox.information(self, "알림", "내보낼 데이터가 없습니다.")
            return
        df = pd.DataFrame([dict(r) for r in rows])
        filepath = ask_save_file(self, "엑셀로 저장", f"이익리포트_{date.today()}.xlsx",
                                 "Excel 파일 (*.xlsx)", "report")
        if filepath:
            df.to_excel(filepath, index=False)
            QMessageBox.information(self, "완료", "엑셀 파일로 저장되었습니다.")


# ---------------------------------------------------------------------------
# 리포트 - 서브탭 2: 채널별 비교 (막대그래프)
# ---------------------------------------------------------------------------
class ChannelCompareTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        control_row = QHBoxLayout()
        self.period_combo = make_period_combo()
        self.period_combo.currentIndexChanged.connect(self.refresh)
        control_row.addWidget(tight_pair("조회 기간:", self.period_combo))
        control_row.addStretch()
        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        control_row.addWidget(refresh_btn)
        layout.addLayout(control_row)

        chart_row = QHBoxLayout()
        self.amount_chart_box = QGroupBox("채널별 매출 · 원가 · 이익")
        self.amount_chart_layout = QVBoxLayout(self.amount_chart_box)
        chart_row.addWidget(self.amount_chart_box, stretch=3)

        self.margin_chart_box = QGroupBox("채널별 수익률(%)")
        self.margin_chart_layout = QVBoxLayout(self.margin_chart_box)
        chart_row.addWidget(self.margin_chart_box, stretch=2)
        layout.addLayout(chart_row)

        self.table = QTableWidget()
        layout.addWidget(self.table, stretch=2)

        self._amount_canvas = None
        self._margin_canvas = None
        self.refresh()

    def refresh(self):
        preset = self.period_combo.currentData()
        date_from, date_to = compute_period_range(preset)

        channel_rows = [r for r in db.get_channel_profit_summary(date_from, date_to)
                         if r["order_count"]]

        categories = [r["channel_name"] for r in channel_rows]
        sales = [r["total_sales"] or 0 for r in channel_rows]
        costs = [r["total_cost"] or 0 for r in channel_rows]
        profits = [r["profit"] or 0 for r in channel_rows]
        margins = [r["profit_margin"] or 0 for r in channel_rows]

        amount_series = {"매출": sales, "원가": costs, "이익": profits}
        new_amount_canvas = charts.bar_chart_canvas(categories, amount_series, ylabel="금액(원)") \
            if categories else charts.empty_message_canvas("해당 기간에 데이터가 없습니다")
        if self._amount_canvas is not None:
            self.amount_chart_layout.removeWidget(self._amount_canvas)
            self._amount_canvas.setParent(None)
        self.amount_chart_layout.addWidget(new_amount_canvas)
        self._amount_canvas = new_amount_canvas

        new_margin_canvas = charts.bar_chart_canvas(categories, {"수익률": margins}, ylabel="%") \
            if categories else charts.empty_message_canvas("데이터가 없습니다")
        if self._margin_canvas is not None:
            self.margin_chart_layout.removeWidget(self._margin_canvas)
            self._margin_canvas.setParent(None)
        self.margin_chart_layout.addWidget(new_margin_canvas)
        self._margin_canvas = new_margin_canvas

        headers = ["채널", "주문건수", "매출", "수수료", "원가", "이익", "수익률"]
        table_rows = [
            (r["channel_name"], r["order_count"], fmt_won(r["total_sales"]),
             fmt_won(r["total_fee"]), fmt_won(r["total_cost"]), fmt_won(r["profit"]),
             f"{r['profit_margin']}%")
            for r in channel_rows
        ]
        fill_table(self.table, headers, table_rows, persist_key="channel_compare")


# ---------------------------------------------------------------------------
# 리포트 - 서브탭 3: 상품별 판매 순위 (막대그래프)
# ---------------------------------------------------------------------------
class ProductRankingTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        control_row = QHBoxLayout()
        self.period_combo = make_period_combo("this_month")   # 기본값: 이번달
        self.period_combo.currentIndexChanged.connect(self.refresh)
        control_row.addWidget(tight_pair("조회 기간:", self.period_combo))

        self.limit_combo = QComboBox()
        for n in (5, 10, 20):
            self.limit_combo.addItem(f"상위 {n}개", n)
        self.limit_combo.currentIndexChanged.connect(self.refresh)
        control_row.addWidget(tight_pair("순위 개수:", self.limit_combo))
        control_row.addStretch()
        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        control_row.addWidget(refresh_btn)
        layout.addLayout(control_row)

        note = QLabel("💡 품목관리에서 원가가 등록되고 주문과 매칭된 상품만 순위에 표시됩니다.")
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        self.chart_box = QGroupBox("매출 상위 품목")
        self.chart_layout = QVBoxLayout(self.chart_box)
        layout.addWidget(self.chart_box, stretch=3)

        self.table = QTableWidget()
        layout.addWidget(self.table, stretch=2)

        self._canvas = None
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        enlarge_row_numbers(self.table)
        self.refresh()

    def refresh(self):
        limit = self.limit_combo.currentData() or 10
        preset = self.period_combo.currentData()
        date_from, date_to = compute_period_range(preset)
        rows = db.get_product_ranking(limit, date_from, date_to)

        categories = [f"{r['product_name']} {r['option_name']}".strip() if r["option_name"] else r["product_name"]
                      for r in rows]
        series = {"매출": [r["total_sales"] or 0 for r in rows],
                  "이익": [r["profit"] or 0 for r in rows]}
        new_canvas = charts.bar_chart_canvas(categories, series, ylabel="금액(원)") if categories \
            else charts.empty_message_canvas("해당 기간에 매칭된 판매 품목이 없습니다")
        if self._canvas is not None:
            self.chart_layout.removeWidget(self._canvas)
            self._canvas.setParent(None)
        self.chart_layout.addWidget(new_canvas)
        self._canvas = new_canvas

        headers = ["상품명(대분류)", "옵션(소분류)", "판매수량", "매출", "이익"]
        table_rows = [
            (r["product_name"], r["option_name"] or "", r["sold_qty"], fmt_won(r["total_sales"]), fmt_won(r["profit"]))
            for r in rows
        ]
        fill_table(self.table, headers, table_rows, persist_key="product_ranking", sort_state=self._sort_state)


# ---------------------------------------------------------------------------
# 리포트 - 서브탭 4: 월별 추이 (꺾은선 그래프, 채널별)
# ---------------------------------------------------------------------------
TREND_PERIOD_PRESETS = [
    ("최근 3개월", 3),
    ("최근 6개월", 6),
    ("최근 12개월", 12),
    ("올해", "this_year"),
    ("전체 기간", "all"),
]


def compute_trend_range(preset_value):
    today = QDate.currentDate()
    if preset_value == "this_year":
        return QDate(today.year(), 1, 1).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
    if preset_value == "all":
        return None, None
    months = int(preset_value)
    start = today.addMonths(-months + 1)
    start = QDate(start.year(), start.month(), 1)
    return start.toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")


class CustomerDetailDialog(QDialog):
    """고객 상세 - 수취인/주문횟수/상품·수량·금액/연락처/주소"""

    def __init__(self, group, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"고객 상세 - {group['name']}")
        self.resize(920, 560)

        layout = QVBoxLayout(self)
        title = QLabel(f"👤 {group['name']}")
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(title)

        info = QGroupBox("고객 정보")
        form = QFormLayout(info)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for label_text, value in [
            ("수취인", group["receiver"] or "-"),
            ("연락처", group["phone"] or "-"),
            ("주소", group["address"] or "-"),
            ("이용 채널", group["channels"] or "-"),
            ("주문 횟수", f"{group['order_count']:,}회"),
            ("총 수량", f"{group['total_qty']:,}개"),
            ("총 주문금액", fmt_won(group["total_amount"])),
            ("최근 주문일", group["last_order"] or "-"),
        ]:
            v = QLabel(str(value))
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(f"{label_text} :", v)
        layout.addWidget(info)

        layout.addWidget(QLabel("🛒 주문 내역"))
        table = QTableWidget()
        rows = []
        for o in sorted(group["orders"], key=lambda x: x["order_date"] or "", reverse=True):
            def og(key):
                try:
                    return o[key] or ""
                except (IndexError, KeyError):
                    return ""
            rows.append((o["order_date"], og("channel_name"), o["product_name"],
                         o["option_name"] or "", f"{o['qty'] or 0:,}",
                         fmt_price(o["sale_price"]), fmt_price(o["total_amount"]),
                         og("buyer_name"), og("receiver_name")))
        fill_table(table, ["주문일", "채널", "상품명", "옵션", "수량", "판매단가", "주문금액",
                            "구매자", "수취인"], rows, persist_key="customer_detail")
        layout.addWidget(table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class CustomerRankingTab(QWidget):
    """리포트 > 매출분석 > 고객별 순위 (반복구매 고객 중심)"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.period_combo = QComboBox()
        self.period_combo.addItem("주간", "week")
        self.period_combo.addItem("월간", "month")
        self.period_combo.addItem("년간", "year")
        self.period_combo.setCurrentIndex(1)   # 기본값: 월간
        self.period_combo.currentIndexChanged.connect(self._apply_period_preset)
        row.addWidget(tight_pair("분석 단위:", self.period_combo))

        self.date_from = make_date_edit()
        self.date_to = make_date_edit()
        row.addWidget(tight_pair("시작일:", self.date_from))
        row.addWidget(tight_pair("종료일:", self.date_to))

        self.min_orders_combo = QComboBox()
        self.min_orders_combo.addItem("3회 이상", 3)
        self.min_orders_combo.addItem("5회 이상", 5)
        self.min_orders_combo.addItem("10회 이상", 10)
        self.min_orders_combo.currentIndexChanged.connect(self.refresh)
        row.addWidget(tight_pair("반복구매:", self.min_orders_combo))

        self.limit_combo = QComboBox()
        self.limit_combo.addItem("상위 10위", 10)
        self.limit_combo.addItem("상위 20위", 20)
        self.limit_combo.currentIndexChanged.connect(self.refresh)
        row.addWidget(tight_pair("표시:", self.limit_combo))

        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh)
        row.addWidget(search_btn)
        row.addStretch()
        layout.addLayout(row)

        note = QLabel("💡 전화번호 → 수취인+주소 → 구매자명 순으로 같은 고객을 묶어서 집계합니다. "
                       "고객 행을 더블클릭하면 상세 내역을 볼 수 있어요.")
        note.setStyleSheet("color: #666;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.summary = QLabel("")
        self.summary.setStyleSheet(
            "padding: 8px; background: #EAF2F8; font-weight: bold; border-radius: 6px;")
        layout.addWidget(self.summary)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_double_clicked)
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        enlarge_row_numbers(self.table)
        layout.addWidget(self.table)

        self._groups = []
        self._apply_period_preset()

    def _apply_period_preset(self):
        today = QDate.currentDate()
        unit = self.period_combo.currentData()
        if unit == "week":
            self.date_from.setDate(today.addDays(-6))            # 최근 7일
        elif unit == "year":
            self.date_from.setDate(QDate(today.year(), 1, 1))    # 올해 1월 1일부터
        else:
            self.date_from.setDate(QDate(today.year(), today.month(), 1))
        self.date_to.setDate(today)
        self.refresh()

    def refresh(self):
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        min_orders = self.min_orders_combo.currentData() or 3
        limit = self.limit_combo.currentData() or 10
        groups = db.get_customer_ranking(date_from, date_to, min_orders=min_orders, limit=limit)
        self._groups = groups

        total_amount = sum(g["total_amount"] for g in groups)
        total_orders = sum(g["order_count"] for g in groups)
        self.summary.setText(
            f"{date_from} ~ {date_to}   |   반복구매 {min_orders}회 이상 고객 {len(groups)}명   |   "
            f"주문 {total_orders:,}건   |   매출 {fmt_won(total_amount)}")

        rows = [
            (i, g["name"], g["receiver"] or "", f"{g['order_count']:,}회", f"{g['total_qty']:,}",
             fmt_won(g["total_amount"]), g["channels"], g["phone"], g["last_order"])
            for i, g in enumerate(groups, start=1)
        ]
        fill_table(self.table,
                   ["순위", "고객명", "수취인", "주문횟수", "총수량", "총매출", "이용채널", "연락처", "최근주문일"],
                   rows, persist_key="customer_ranking", sort_state=self._sort_state)

    def on_double_clicked(self, row, column):
        if 0 <= row < len(self._groups):
            CustomerDetailDialog(self._groups[row], self).exec()


class TrendTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        control_row = QHBoxLayout()
        self.period_combo = QComboBox()
        for label, val in TREND_PERIOD_PRESETS:
            self.period_combo.addItem(label, val)
        self.period_combo.setCurrentIndex(1)  # 기본값: 최근 6개월
        self.period_combo.currentIndexChanged.connect(self.refresh)
        control_row.addWidget(tight_pair("조회 기간:", self.period_combo))
        control_row.addStretch()
        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        control_row.addWidget(refresh_btn)
        layout.addLayout(control_row)

        self.chart_box = QGroupBox("채널별 월별 매출 추이")
        self.chart_layout = QVBoxLayout(self.chart_box)
        layout.addWidget(self.chart_box)

        self._canvas = None
        self.refresh()

    def refresh(self):
        preset_value = self.period_combo.currentData()
        date_from, date_to = compute_trend_range(preset_value)
        rows = db.get_monthly_trend_by_channel(date_from, date_to)
        months = sorted(set(r["ym"] for r in rows))
        by_channel = {}
        for r in rows:
            by_channel.setdefault(r["channel_name"], {})[r["ym"]] = r["total_sales"] or 0

        series = {}
        for channel_name, month_map in by_channel.items():
            series[channel_name] = [month_map.get(m, 0) for m in months]

        new_canvas = charts.line_chart_canvas(months, series, ylabel="매출(원)") if months \
            else charts.empty_message_canvas("추이를 표시할 데이터가 없습니다")
        if self._canvas is not None:
            self.chart_layout.removeWidget(self._canvas)
            self._canvas.setParent(None)
        self.chart_layout.addWidget(new_canvas)
        self._canvas = new_canvas


# ---------------------------------------------------------------------------
# 리포트 탭 (서브탭 4개를 묶는 컨테이너)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 리포트 - 서브탭: 정산 현황 (판매채널 미정산 / 매입거래처 미결제)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 리포트 - 서브탭: 재고 현황 (품목관리와 연동)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 리포트 - 서브탭: 월별결산 (매출-영업이익-지출, 누적 현황)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 리포트 - 서브탭: 통장 현황
# ---------------------------------------------------------------------------
class ExpenseStatusTab(QWidget):
    """리포트 > 자금현황 > 지출 현황 - 경비지출 + 매입지출을 한눈에"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.date_from = make_date_edit()
        self.date_from.setDate(QDate(QDate.currentDate().year(), QDate.currentDate().month(), 1))
        row.addWidget(tight_pair("시작일:", self.date_from))
        self.date_to = make_date_edit()
        self.date_to.setDate(QDate.currentDate())
        row.addWidget(tight_pair("종료일:", self.date_to))
        row.addSpacing(16)
        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh)
        row.addWidget(search_btn)
        for text, months in [("이번달", 0), ("지난달", -1), ("올해", 12)]:
            b = QPushButton(text)
            b.clicked.connect(lambda checked, m=months: self._preset(m))
            row.addWidget(b)
        row.addStretch()
        layout.addLayout(row)

        self.summary = QLabel("")
        self.summary.setAlignment(Qt.AlignCenter)
        self.summary.setStyleSheet("""
            QLabel { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #C0392B, stop:1 #E74C3C);
                     color: white; border-radius: 10px; padding: 14px;
                     font-size: 15px; font-weight: bold; }
        """)
        layout.addWidget(self.summary)

        # 구분별 / 결제수단별 요약
        self.breakdown = QLabel("")
        self.breakdown.setStyleSheet("padding: 8px; background: #F4F6F7; border-radius: 6px;")
        self.breakdown.setWordWrap(True)
        layout.addWidget(self.breakdown)

        layout.addWidget(QLabel("📋 지출 내역 (경비지출 + 매입지출)"))
        self.table = QTableWidget()
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        enlarge_row_numbers(self.table)
        layout.addWidget(self.table)

        self.refresh()

    def _preset(self, months):
        today = QDate.currentDate()
        if months == 0:
            self.date_from.setDate(QDate(today.year(), today.month(), 1))
            self.date_to.setDate(today)
        elif months == 12:
            self.date_from.setDate(QDate(today.year(), 1, 1))
            self.date_to.setDate(today)
        else:
            first = QDate(today.year(), today.month(), 1).addMonths(-1)
            self.date_from.setDate(first)
            self.date_to.setDate(first.addMonths(1).addDays(-1))
        self.refresh()

    def refresh(self):
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        rows = db.get_all_expenses_combined(date_from, date_to)
        total = sum(r["amount"] for r in rows)
        self.summary.setText(
            f"💸 {date_from} ~ {date_to} 총 지출<br><span style='font-size:24px;'>{fmt_won(total)}</span>")

        by_kind, by_method, by_category = {}, {}, {}
        for r in rows:
            by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + r["amount"]
            by_method[r["raw_method"]] = by_method.get(r["raw_method"], 0) + r["amount"]
            by_category[r["category"]] = by_category.get(r["category"], 0) + r["amount"]
        top_cat = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5]
        self.breakdown.setText(
            "구분별 :  " + ("   ".join(f"{k} {fmt_won(v)}" for k, v in by_kind.items()) or "-") + "\n"
            "결제수단 :  " + ("   ".join(f"{k} {fmt_won(v)}" for k, v in by_method.items()) or "-") + "\n"
            "상위 항목 :  " + ("   ".join(f"{k} {fmt_won(v)}" for k, v in top_cat) or "-")
        )

        fill_table(self.table, ["날짜", "구분", "항목/거래처", "금액", "결제수단", "메모"],
                   [(r["date"], r["kind"], r["category"], fmt_won(r["amount"]),
                     r["method"], r["memo"]) for r in rows],
                   persist_key="expense_status", sort_state=self._sort_state)


class CashAdjustDialog(QDialog):
    """현금 시재를 실제 보유액에 맞추거나, 임의로 더하고 빼는 창"""

    def __init__(self, current_balance, parent=None):
        super().__init__(parent)
        self.current_balance = current_balance or 0
        self.setWindowTitle("현금 조정 / 시재 입력")
        self.resize(420, 330)

        layout = QVBoxLayout(self)
        info = QLabel(f"현재 장부상 현금 시재 :  <b>{fmt_won(self.current_balance)}</b>")
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet("padding: 10px; background: #EAF2F8; border-radius: 6px; font-size: 14px;")
        layout.addWidget(info)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("실제 보유 현금으로 맞추기 (시재 실사)", "set")
        self.mode_combo.addItem("현금 늘리기 (+)", "plus")
        self.mode_combo.addItem("현금 줄이기 (−)", "minus")
        self.mode_combo.currentIndexChanged.connect(self._update_hint)
        layout.addWidget(self.mode_combo)

        form = QFormLayout()
        self.date_edit = make_date_edit()
        self.date_edit.setDate(QDate.currentDate())
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("숫자만 입력")
        self.amount_input.textChanged.connect(self._update_hint)
        self.reason_combo = QComboBox()
        self.reason_combo.setEditable(True)
        self.reason_combo.addItems(["시재 실사 반영", "시재 최초 등록", "현금 입금", "현금 인출",
                                     "통장에서 인출", "통장에 예금", "기타"])
        self.memo_input = QLineEdit()
        form.addRow("날짜", self.date_edit)
        form.addRow("금액", self.amount_input)
        form.addRow("사유", self.reason_combo)
        form.addRow("메모", self.memo_input)
        layout.addLayout(form)

        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #1A5276; padding: 6px;")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._update_hint()

    def _calc_change(self):
        amount = to_int(self.amount_input.text(), 0)
        mode = self.mode_combo.currentData()
        if mode == "set":
            return amount - self.current_balance
        if mode == "minus":
            return -amount
        return amount

    def _update_hint(self):
        if not self.amount_input.text().strip():
            self.hint_label.setText("")
            return
        change = self._calc_change()
        after = self.current_balance + change
        sign = "+" if change >= 0 else ""
        self.hint_label.setText(
            f"조정액 {sign}{change:,}원  →  조정 후 시재 {fmt_won(after)}")

    def save(self):
        if not self.amount_input.text().strip():
            QMessageBox.warning(self, "알림", "금액을 입력해주세요.")
            return
        change = self._calc_change()
        if change == 0:
            QMessageBox.information(self, "알림", "조정할 금액이 0원이라 저장하지 않았습니다.")
            return
        reason = self.reason_combo.currentText().strip() or "현금 조정"
        db.add_cash_adjustment(self.date_edit.date().toString("yyyy-MM-dd"),
                                change, reason, self.memo_input.text().strip())
        self.accept()


class ExpenseOverviewTab(QWidget):
    """리포트 > 자금현황 > 지출 종합 - 경비지출 + 매입대금을 한눈에"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.date_from = make_date_edit()
        self.date_from.setDate(QDate(QDate.currentDate().year(), QDate.currentDate().month(), 1))
        row.addWidget(tight_pair("시작일:", self.date_from))
        self.date_to = make_date_edit()
        self.date_to.setDate(QDate.currentDate())
        row.addWidget(tight_pair("종료일:", self.date_to))
        row.addSpacing(20)
        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh)
        row.addWidget(search_btn)
        for text, months in [("이번달", 0), ("최근 3개월", 3), ("올해", -1)]:
            b = QPushButton(text)
            b.clicked.connect(lambda checked, m=months: self._set_period(m))
            row.addWidget(b)
        row.addStretch()
        layout.addLayout(row)

        self.summary_label = QLabel("")
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setStyleSheet("""
            QLabel { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                     stop:0 #E74C3C, stop:1 #EC7063);
                     color: white; border-radius: 10px; padding: 14px;
                     font-size: 15px; font-weight: bold; }
        """)
        layout.addWidget(self.summary_label)

        mid = QHBoxLayout()
        left_box = QGroupBox("항목별 지출")
        left_v = QVBoxLayout(left_box)
        self.category_table = QTableWidget()
        left_v.addWidget(self.category_table)
        mid.addWidget(left_box)

        right_box = QGroupBox("지출방법별")
        right_v = QVBoxLayout(right_box)
        self.method_table = QTableWidget()
        right_v.addWidget(self.method_table)
        mid.addWidget(right_box)
        layout.addLayout(mid)

        layout.addWidget(QLabel("📋 전체 지출 내역"))
        self.table = QTableWidget()
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        enlarge_row_numbers(self.table)
        layout.addWidget(self.table)

        self.refresh()

    def _set_period(self, months):
        today = QDate.currentDate()
        if months == 0:
            self.date_from.setDate(QDate(today.year(), today.month(), 1))
        elif months == -1:
            self.date_from.setDate(QDate(today.year(), 1, 1))
        else:
            self.date_from.setDate(today.addMonths(-months))
        self.date_to.setDate(today)
        self.refresh()

    def refresh(self):
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        rows = db.get_all_expenses_overview(date_from, date_to)

        total = sum(r["amount"] or 0 for r in rows)
        expense_total = sum(r["amount"] or 0 for r in rows if r["kind"] == "경비")
        purchase_total = total - expense_total
        self.summary_label.setText(
            f"💸 {date_from} ~ {date_to} 총 지출<br>"
            f"<span style='font-size:24px;'>{fmt_won(total)}</span><br>"
            f"<span style='font-size:12px;'>경비 {fmt_won(expense_total)}  ·  "
            f"매입대금 {fmt_won(purchase_total)}  ·  {len(rows)}건</span>")

        # 항목별 집계
        by_cat = {}
        for r in rows:
            key = r["category"] or "기타"
            by_cat[key] = by_cat.get(key, 0) + (r["amount"] or 0)
        cat_rows = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)
        fill_table(self.category_table, ["항목", "금액", "비중"],
                   [(k, fmt_won(v), f"{(v/total*100 if total else 0):.1f}%") for k, v in cat_rows],
                   persist_key="expense_overview_cat")
        fit_table_height(self.category_table, max_rows=8)

        # 지출방법별 집계
        by_method = {}
        for r in rows:
            m = r["method"] or "통장"
            if m == "통장":
                label = f"통장 - {r['bank_name']}" if r["bank_name"] else "통장"
            elif m == "카드":
                label = f"카드 - {r['card_name']}" if r["card_name"] else "카드"
            else:
                label = "현금"
            by_method[label] = by_method.get(label, 0) + (r["amount"] or 0)
        method_rows = sorted(by_method.items(), key=lambda x: x[1], reverse=True)
        fill_table(self.method_table, ["지출방법", "금액", "비중"],
                   [(k, fmt_won(v), f"{(v/total*100 if total else 0):.1f}%") for k, v in method_rows],
                   persist_key="expense_overview_method")
        fit_table_height(self.method_table, max_rows=8)

        detail = []
        for r in rows:
            m = r["method"] or "통장"
            if m == "통장":
                mlabel = f"통장 - {r['bank_name']}" if r["bank_name"] else "통장"
            elif m == "카드":
                mlabel = f"카드 - {r['card_name']}" if r["card_name"] else "카드"
            else:
                mlabel = "현금"
            detail.append((r["date"], r["kind"], r["category"] or "", r["partner"] or "",
                           fmt_won(r["amount"]), mlabel, r["memo"] or ""))
        fill_table(self.table, ["날짜", "구분", "항목", "거래처", "금액", "지출방법", "메모"],
                   detail, persist_key="expense_overview", sort_state=self._sort_state)


class CashStatusTab(QWidget):
    """리포트 > 자금현황 > 현금 현황 - 현금으로 들어오고 나간 내역과 현재 현금 시재"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(refresh_btn)
        adjust_btn = QPushButton("💵 현금 조정 / 시재 입력")
        adjust_btn.setToolTip("실제 보유 현금과 맞추거나, 시재를 처음 입력할 때 사용합니다")
        adjust_btn.clicked.connect(self.open_cash_adjust)
        top_row.addWidget(adjust_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        note = QLabel("💡 현금 시재 = 현금으로 받은 정산입금 − 현금으로 나간 경비지출·매입지출 ± 현금조정\n"
                       "   (지출방법을 '현금'으로 등록한 건들만 집계됩니다)")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        self.summary_label = QLabel("")
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #16A085, stop:1 #1ABC9C);
                color: white; border-radius: 10px; padding: 16px;
                font-size: 16px; font-weight: bold;
            }
        """)
        layout.addWidget(self.summary_label)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("padding: 6px; color: #444;")
        layout.addWidget(self.detail_label)

        layout.addWidget(QLabel("📋 현금 입출금 내역"))
        self.table = QTableWidget()
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        enlarge_row_numbers(self.table)
        layout.addWidget(self.table)

        self.refresh()

    def open_cash_adjust(self):
        current = sum(e["amount"] for e in db.get_cash_summary())
        dialog = CashAdjustDialog(current, self)
        if dialog.exec() == QDialog.Accepted:
            notify_data_changed()
            self.refresh()

    def refresh(self):
        entries = db.get_cash_summary()
        total_in = sum(e["amount"] for e in entries if e["amount"] > 0)
        total_out = -sum(e["amount"] for e in entries if e["amount"] < 0)
        balance = total_in - total_out

        self.summary_label.setText(f"💵 현재 현금 시재<br><span style='font-size:26px;'>{fmt_won(balance)}</span>")
        self.detail_label.setText(
            f"현금 입금 합계: {fmt_won(total_in)}     |     현금 출금 합계: {fmt_won(total_out)}     |     "
            f"거래 {len(entries)}건"
        )

        # 최근 건이 위로 오도록 뒤집어서 표시 (잔액은 시간순 누적값 그대로)
        rows = [
            (e["date"], e["desc"],
             fmt_won(e["amount"]) if e["amount"] > 0 else "",
             fmt_won(-e["amount"]) if e["amount"] < 0 else "",
             fmt_won(e["balance"]), e["memo"])
            for e in reversed(entries)
        ]
        fill_table(self.table, ["날짜", "내역", "입금", "출금", "현금 시재", "메모"],
                   rows, persist_key="cash_status")


class BankTransferDialog(QDialog):
    """통장간 자금이동(이체) - 한 통장에서 다른 통장으로 돈을 옮김.
    회사 안에서 돈이 옮겨가는 것이라 매출/지출로는 잡지 않고,
    이체수수료만 실제로 빠져나간 돈으로 처리함"""

    def __init__(self, parent=None, preset_from_id=None):
        super().__init__(parent)
        self.setWindowTitle("통장간 자금이동")
        self.resize(460, 340)
        layout = QVBoxLayout(self)

        title = QLabel("💸 통장간 자금이동")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        note = QLabel("💡 회사 통장끼리 돈을 옮기는 것이라 <b>매출·지출로는 잡히지 않습니다.</b><br>"
                      "보내는 통장에서 <b>금액 + 이체수수료</b>가 빠지고, "
                      "받는 통장에는 <b>금액</b>만 들어갑니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555; background:#FEF9E7; padding:8px; border-radius:6px;")
        layout.addWidget(note)

        self._accounts = db.get_bank_accounts()
        form = QFormLayout()

        self.date_edit = make_date_edit()
        self.date_edit.setDate(QDate.currentDate())

        self.from_combo = QComboBox()
        self.to_combo = QComboBox()
        for a in self._accounts:
            label = f"{self._bank_label(a)}  ({fmt_won(a['balance'])})"
            self.from_combo.addItem(label, a["id"])
            self.to_combo.addItem(label, a["id"])
        if preset_from_id is not None:
            idx = self.from_combo.findData(preset_from_id)
            if idx >= 0:
                self.from_combo.setCurrentIndex(idx)
        if self.to_combo.count() > 1:
            self.to_combo.setCurrentIndex(1 if self.from_combo.currentIndex() == 0 else 0)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("예: 300000")
        self.fee_input = QLineEdit("0")
        self.fee_input.setPlaceholderText("이체수수료 (없으면 0)")
        self.memo_input = QLineEdit()
        self.memo_input.setPlaceholderText("예: 운영자금 이동")

        form.addRow("이체일", self.date_edit)
        form.addRow("보내는 통장", self.from_combo)
        form.addRow("받는 통장", self.to_combo)
        form.addRow("이체 금액", self.amount_input)
        form.addRow("이체수수료", self.fee_input)
        form.addRow("메모", self.memo_input)
        layout.addLayout(form)

        self.preview = QLabel("")
        self.preview.setStyleSheet("padding:8px; background:#EAF2F8; border-radius:5px; color:#1A5276;")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)

        self.amount_input.textChanged.connect(self._update_preview)
        self.fee_input.textChanged.connect(self._update_preview)
        self.from_combo.currentIndexChanged.connect(self._update_preview)
        self.to_combo.currentIndexChanged.connect(self._update_preview)
        self._update_preview()

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("💸 이체하기")
        ok_btn.clicked.connect(self.do_transfer)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def _bank_label(a):
        """통장 별칭이 '법인통장'처럼 겹칠 때 구분이 안 되므로 은행명을 우선 표시.
        은행명이 비어있는 통장은 기존 별칭을 그대로 씀"""
        try:
            bank = (a["bank_name"] or "").strip()
        except (IndexError, KeyError):
            bank = ""
        name = (a["name"] or "").strip()
        if bank and name and bank != name:
            return f"{bank} ({name})"
        return bank or name

    def _bank_by_id(self, bank_id):
        return next((a for a in self._accounts if a["id"] == bank_id), None)

    def _update_preview(self):
        amount = to_int(self.amount_input.text(), 0)
        fee = to_int(self.fee_input.text(), 0)
        src = self._bank_by_id(self.from_combo.currentData())
        dst = self._bank_by_id(self.to_combo.currentData())
        if not src or not dst or amount <= 0:
            self.preview.setText("금액을 입력하면 이체 후 잔액을 미리 보여드려요.")
            return
        if src["id"] == dst["id"]:
            self.preview.setText("⚠️ 보내는 통장과 받는 통장이 같습니다.")
            return
        src_after = (src["balance"] or 0) - amount - fee
        dst_after = (dst["balance"] or 0) + amount
        warn = "  ⚠️ 잔액이 마이너스가 됩니다" if src_after < 0 else ""
        self.preview.setText(
            f"{self._bank_label(src)}: {fmt_won(src['balance'])} → <b>{fmt_won(src_after)}</b>{warn}<br>"
            f"{self._bank_label(dst)}: {fmt_won(dst['balance'])} → <b>{fmt_won(dst_after)}</b>")

    def do_transfer(self):
        amount = to_int(self.amount_input.text(), 0)
        fee = to_int(self.fee_input.text(), 0)
        from_id = self.from_combo.currentData()
        to_id = self.to_combo.currentData()
        src = self._bank_by_id(from_id)
        dst = self._bank_by_id(to_id)

        if not src or not dst:
            QMessageBox.warning(self, "알림", "통장을 먼저 등록해주세요.")
            return
        if from_id == to_id:
            QMessageBox.warning(self, "알림", "보내는 통장과 받는 통장이 같습니다.")
            return
        if amount <= 0:
            QMessageBox.warning(self, "알림", "이체 금액을 입력해주세요.")
            return
        if (src["balance"] or 0) - amount - fee < 0:
            if QMessageBox.question(
                    self, "잔액 확인",
                    f"'{self._bank_label(src)}' 잔액이 부족해서 마이너스가 됩니다.\n그대로 진행할까요?"
            ) != QMessageBox.Yes:
                return

        try:
            db.add_bank_transfer(
                self.date_edit.date().toString("yyyy-MM-dd"),
                from_id, to_id, amount, fee, self.memo_input.text().strip())
        except Exception as e:
            QMessageBox.critical(self, "오류", f"이체 중 오류가 발생했습니다:\n{e}")
            return

        notify_data_changed()
        QMessageBox.information(
            self, "완료",
            f"{self._bank_label(src)} → {self._bank_label(dst)}\n{fmt_won(amount)}을 이체했습니다."
            + (f"\n(이체수수료 {fmt_won(fee)} 별도 차감)" if fee else ""))
        self.accept()


class BankTransferHistoryDialog(QDialog):
    """통장간 이체 내역 - 잘못 넣은 이체를 되돌릴 수 있음"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("통장간 이체 내역")
        self.resize(820, 440)
        layout = QVBoxLayout(self)

        title = QLabel("📋 통장간 이체 내역")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)
        note = QLabel("💡 이체를 삭제하면 양쪽 통장 잔액이 이체 전으로 되돌아갑니다.")
        note.setStyleSheet("color:#666;")
        layout.addWidget(note)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        del_btn = QPushButton("🗑️ 선택 이체 삭제(되돌리기)")
        del_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self):
        self._rows = db.get_bank_transfers()
        fill_table(self.table,
                   ["이체일", "보내는 통장", "받는 통장", "금액", "수수료", "메모"],
                   [(t["transfer_date"], t["from_name"] or "(삭제된 통장)",
                     t["to_name"] or "(삭제된 통장)", fmt_won(t["amount"]),
                     fmt_won(t["fee"]) if t["fee"] else "-", t["memo"] or "")
                    for t in self._rows],
                   persist_key="bank_transfers")

    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            QMessageBox.warning(self, "알림", "삭제할 이체 내역을 선택해주세요.")
            return
        t = self._rows[row]
        if not confirm_delete(
                self,
                f"{t['from_name']} → {t['to_name']} {fmt_won(t['amount'])} 이체",
                "삭제하면 양쪽 통장 잔액이 이체 전 상태로 되돌아갑니다."):
            return
        db.delete_bank_transfer(t["id"])
        notify_data_changed()
        self.refresh()


class BankStatusTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(refresh_btn)
        transfer_btn = QPushButton("💸 통장간 자금이동")
        transfer_btn.setToolTip("한 통장에서 다른 통장으로 돈을 옮깁니다 (매출/지출로 잡히지 않음)")
        transfer_btn.clicked.connect(self.open_transfer)
        btn_row.addWidget(transfer_btn)
        history_btn = QPushButton("📋 이체 내역")
        history_btn.clicked.connect(self.open_transfer_history)
        btn_row.addWidget(history_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 6px;"
        )
        layout.addWidget(self.summary_label)

        layout.addWidget(QLabel("🏦 통장별 잔액 (더블클릭하면 입출금 내역 상세)"))
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_bank_double_clicked)
        layout.addWidget(self.table)

        layout.addWidget(QLabel("📋 거래내역 (매입지출/경비지출/정산입금/통장이체 중 통장과 연계된 것)"))
        tx_ctrl = QHBoxLayout()
        today = QDate.currentDate()
        self.tx_date_from = make_date_edit()
        self.tx_date_from.setDate(QDate(today.year(), today.month(), 1))   # 기본: 이번달
        self.tx_date_to = make_date_edit()
        self.tx_date_to.setDate(today)
        tx_ctrl.addWidget(tight_pair("시작일:", self.tx_date_from))
        tx_ctrl.addWidget(tight_pair("종료일:", self.tx_date_to))
        tx_search_btn = QPushButton("조회")
        tx_search_btn.clicked.connect(self.refresh)
        tx_ctrl.addWidget(tx_search_btn)
        for label, fn in (("이번달", self._tx_this_month), ("지난달", self._tx_last_month),
                          ("올해", self._tx_this_year), ("전체", self._tx_all)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            tx_ctrl.addWidget(b)
        tx_ctrl.addStretch()
        layout.addLayout(tx_ctrl)

        self.tx_summary = QLabel("")
        self.tx_summary.setStyleSheet("color:#1A5276; padding:4px 8px;")
        layout.addWidget(self.tx_summary)

        self.tx_table = QTableWidget()
        layout.addWidget(self.tx_table)

        self._sort_state = {"column": None, "ascending": True}
        self._tx_sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        enable_header_click_sort(self.tx_table, self._tx_sort_state, self.refresh)
        enlarge_row_numbers(self.table)
        enlarge_row_numbers(self.tx_table)
        self.refresh()

    def on_bank_double_clicked(self, row, column):
        if row < 0 or row >= len(self._accounts):
            return
        dialog = BankTransactionDetailDialog(self._accounts[row], self)
        dialog.exec()

    def _tx_set_range(self, d_from, d_to):
        self.tx_date_from.setDate(d_from)
        self.tx_date_to.setDate(d_to)
        self.refresh()

    def _tx_this_month(self):
        t = QDate.currentDate()
        self._tx_set_range(QDate(t.year(), t.month(), 1), t)

    def _tx_last_month(self):
        t = QDate.currentDate()
        end = QDate(t.year(), t.month(), 1).addDays(-1)
        self._tx_set_range(QDate(end.year(), end.month(), 1), end)

    def _tx_this_year(self):
        t = QDate.currentDate()
        self._tx_set_range(QDate(t.year(), 1, 1), t)

    def _tx_all(self):
        self._tx_set_range(QDate(2000, 1, 1), QDate.currentDate())

    def open_transfer(self):
        if len(db.get_bank_accounts()) < 2:
            QMessageBox.information(self, "알림",
                                    "통장간 이체를 하려면 통장이 2개 이상 등록되어 있어야 합니다.")
            return
        preset = None
        row = self.table.currentRow()
        if 0 <= row < len(self._accounts):
            preset = self._accounts[row]["id"]
        if BankTransferDialog(self, preset_from_id=preset).exec() == QDialog.Accepted:
            self.refresh()

    def open_transfer_history(self):
        BankTransferHistoryDialog(self).exec()
        self.refresh()

    def refresh(self):
        accounts = db.get_bank_accounts()
        self._accounts = accounts
        total_balance = sum(a["balance"] or 0 for a in accounts)
        self.summary_label.setText(f"💰 통장 잔액 합계: {fmt_won(total_balance)}   |   통장 수: {len(accounts)}개")

        headers = ["통장별칭", "은행명", "계좌번호", "잔액", "메모"]
        rows = [(a["name"], a["bank_name"] or "", a["account_number"] or "",
                 fmt_won(a["balance"]), a["memo"] or "") for a in accounts]
        self._accounts = fill_table(self.table, headers, rows, persist_key="bank_status",
                                     sort_state=self._sort_state, id_list=accounts) or accounts

        df = self.tx_date_from.date().toString("yyyy-MM-dd")
        dt = self.tx_date_to.date().toString("yyyy-MM-dd")
        transactions = db.get_bank_transactions(500, date_from=df, date_to=dt)
        headers_tx = ["날짜", "내역", "구분", "통장(은행)", "입금", "출금", "메모"]
        rows_tx = []
        in_sum = out_sum = 0
        for t in transactions:
            amt = t["amount"] or 0
            if amt > 0:
                in_sum += amt
            else:
                out_sum += -amt
            if "이체" in t["kind"]:
                arrow = "→" if amt < 0 else "←"
                desc = f"통장이체 {arrow} {t['ref_name'] or '통장'}"
            elif "매입지출" in t["kind"]:
                desc = f"매입대금 - {t['ref_name'] or '거래처'}"
            elif "지출" in t["kind"]:
                desc = f"지출 ({t['category'] or '기타'})"
            else:
                desc = f"정산입금 - {t['ref_name'] or '채널'}"
            rows_tx.append((
                t["date"], desc, t["kind"], t["bank_account_name"],
                fmt_won(amt) if amt > 0 else "",
                fmt_won(-amt) if amt < 0 else "",
                t["memo"],
            ))
        fill_table(self.tx_table, headers_tx, rows_tx, persist_key="bank_transactions", sort_state=self._tx_sort_state)
        self.tx_summary.setText(
            f"{df} ~ {dt}   |   {len(rows_tx):,}건   |   "
            f"입금 {fmt_won(in_sum)}   |   출금 {fmt_won(out_sum)}   |   "
            f"순증감 {fmt_won(in_sum - out_sum)}")


class ChannelProfitDetailDialog(QDialog):
    """월별결산에서 월 항목을 더블클릭했을 때 채널/거래처별 이익현황 상세"""

    def __init__(self, year_month, parent=None):
        super().__init__(parent)
        self.year_month = year_month
        self.setWindowTitle(f"{year_month} 채널/거래처별 이익현황")
        self.resize(700, 450)

        layout = QVBoxLayout(self)
        title = QLabel(f"📊 {year_month} 채널/거래처별 이익현황")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.table = QTableWidget()
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        layout.addWidget(self.table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.refresh()

    def refresh(self):
        rows = db.get_channel_profit_for_month(self.year_month)
        headers = ["채널/거래처", "매출액", "수수료", "수수료율", "이익금", "이익률"]
        table_rows = [
            (r["channel_name"], fmt_won(r["total_sales"]), fmt_won(r["total_fee"]),
             f"{r['fee_rate']:.1f}%", fmt_won(r["profit"]), f"{r['profit_rate']:.1f}%")
            for r in rows
        ]
        # 맨 아래에 합계 행 추가
        if rows:
            total_sales = sum(r["total_sales"] for r in rows)
            total_fee = sum(r["total_fee"] for r in rows)
            total_profit = sum(r["profit"] for r in rows)
            fee_rate = (total_fee / total_sales * 100) if total_sales else 0
            profit_rate = (total_profit / total_sales * 100) if total_sales else 0
            table_rows.append((
                "■ 합계", fmt_won(total_sales), fmt_won(total_fee),
                f"{fee_rate:.1f}%", fmt_won(total_profit), f"{profit_rate:.1f}%"
            ))
        fill_table(self.table, headers, table_rows, sort_state=self._sort_state)


class MonthlySettlementTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # 조회 기간 설정
        filter_row = QHBoxLayout()
        self.date_from = make_date_edit()
        self.date_from.setDate(QDate.currentDate().addYears(-1))
        filter_row.addWidget(tight_pair("시작일:", self.date_from))
        self.date_to = make_date_edit()
        self.date_to.setDate(QDate.currentDate())
        filter_row.addWidget(tight_pair("종료일:", self.date_to))
        filter_row.addSpacing(24)
        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh)
        filter_row.addWidget(search_btn)
        this_year_btn = QPushButton("올해")
        this_year_btn.clicked.connect(self.set_this_year)
        filter_row.addWidget(this_year_btn)
        all_btn = QPushButton("전체기간")
        all_btn.clicked.connect(self.set_all_period)
        filter_row.addWidget(all_btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        note = QLabel("💡 영업이익 = 매출 - 수수료 - 원가 (품목관리에 원가/매칭된 주문만 반영).  "
                      "순이익 = 영업이익 - 지출(정산/지출관리에 등록된 지출)")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 6px;"
        )
        layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_month_double_clicked)
        layout.addWidget(self.table)

        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        enlarge_row_numbers(self.table)
        self.refresh()

    def set_this_year(self):
        today = QDate.currentDate()
        self.date_from.setDate(QDate(today.year(), 1, 1))
        self.date_to.setDate(today)
        self.refresh()

    def set_all_period(self):
        self.date_from.setDate(QDate(2000, 1, 1))
        self.date_to.setDate(QDate.currentDate())
        self.refresh()

    def on_month_double_clicked(self, row, column):
        if row < 0 or row >= len(self._year_months):
            return
        dialog = ChannelProfitDetailDialog(self._year_months[row], self)
        dialog.exec()

    def refresh(self):
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        rows = db.get_monthly_settlement(date_from=date_from, date_to=date_to)

        total_sales = sum(r["sales"] for r in rows)
        total_expense = sum(r["expense"] for r in rows)
        total_gross_profit = sum(r["gross_profit"] for r in rows)
        total_net_profit = sum(r["net_profit"] for r in rows)

        self.summary_label.setText(
            f"📊 {date_from} ~ {date_to} 합계  —  총 매출: {fmt_won(total_sales)}   |   "
            f"총 영업이익: {fmt_won(total_gross_profit)}   |   총 지출: {fmt_won(total_expense)}   |   "
            f"총 순이익: {fmt_won(total_net_profit)}"
        )

        headers = ["연월", "매출", "원가", "수수료", "영업이익(매출-수수료-원가)", "지출", "순이익(영업이익-지출)"]
        table_rows = [
            (r["ym"], fmt_won(r["sales"]), fmt_won(r["cost"]), fmt_won(r["fee"]),
             fmt_won(r["gross_profit"]), fmt_won(r["expense"]), fmt_won(r["net_profit"]))
            for r in rows
        ]
        year_months = [r["ym"] for r in rows]
        self._year_months = fill_table(self.table, headers, table_rows, persist_key="monthly_settlement",
                                        sort_state=self._sort_state, id_list=year_months) or year_months


class ChannelSalesTab(QWidget):
    """리포트 > 채널/거래처별 매출 분석"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("📊 채널/거래처별 매출 분석")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        ctrl = QHBoxLayout()
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate(QDate.currentDate().year(), QDate.currentDate().month(), 1))
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        ctrl.addWidget(tight_pair("시작일:", self.date_from))
        ctrl.addWidget(tight_pair("종료일:", self.date_to))
        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh)
        ctrl.addWidget(search_btn)
        this_month_btn = QPushButton("이번달")
        this_month_btn.clicked.connect(self._this_month)
        ctrl.addWidget(this_month_btn)
        last_month_btn = QPushButton("지난달")
        last_month_btn.clicked.connect(self._last_month)
        ctrl.addWidget(last_month_btn)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self.summary = QLabel("")
        self.summary.setStyleSheet("padding:6px 12px; background:#EAF2F8;"
                                   "border-radius:5px; font-weight:bold; color:#1A5276;")
        layout.addWidget(self.summary)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        self._sort = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort, self.refresh)

    def _this_month(self):
        t=QDate.currentDate()
        self.date_from.setDate(QDate(t.year(),t.month(),1))
        self.date_to.setDate(t); self.refresh()

    def _last_month(self):
        t=QDate.currentDate()
        first=QDate(t.year(),t.month(),1)
        end=first.addDays(-1)
        self.date_from.setDate(QDate(end.year(),end.month(),1))
        self.date_to.setDate(end); self.refresh()

    def refresh(self):
        df=self.date_from.date().toString("yyyy-MM-dd")
        dt=self.date_to.date().toString("yyyy-MM-dd")
        rows=db.get_channel_sales_summary(df, dt)
        total_sales=sum(r["total_sales"] or 0 for r in rows)
        total_profit=sum(r["profit"] or 0 for r in rows)
        total_ship=sum(r["shipping_net"] or 0 for r in rows)
        self.summary.setText(
            f"총 {len(rows)}개 채널/거래처  |  총 매출 {fmt_won(total_sales)}  |  "
            f"배송비순수익 {fmt_won(total_ship)}  |  총 이익 {fmt_won(total_profit)}"
            + (f"  |  이익률 {total_profit/total_sales*100:.1f}%" if total_sales else ""))
        def pct(p, s): return f"{p/s*100:.1f}%" if s else "-"
        table_rows=[(r["channel_name"], r["channel_type"], f"{r['order_count']:,}건",
                     fmt_won(r["total_sales"]), fmt_won(r["total_fee"]),
                     fmt_won(r["total_cost"]), fmt_won(r["shipping_net"]), fmt_won(r["profit"]),
                     pct(r["profit"] or 0, r["total_sales"] or 0)) for r in rows]
        fill_table(self.table,
                   ["채널/거래처","유형","주문건수","매출","수수료","원가","배송비순수익","이익","이익률"],
                   table_rows, persist_key="channel_sales", sort_state=self._sort)
        for r in range(self.table.rowCount()):
            for col in (2,8):
                it=self.table.item(r,col)
                if it: it.setTextAlignment(Qt.AlignCenter)


class ReturnStatusTab(QWidget):
    """반품/반출 내역 리포트
    · 고객 반품: 주문 상태가 '반품'인 건 (소비자가 돌려보낸 것)
    · 직접 반출: 입고관리에서 등록한 반출 건 (우리가 내보낸 것)"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("↩️ 반품 / 반출 내역")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        # 기간 필터
        ctrl = QHBoxLayout()
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        ctrl.addWidget(tight_pair("시작일:", self.date_from))
        ctrl.addWidget(tight_pair("종료일:", self.date_to))
        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh)
        ctrl.addWidget(search_btn)
        this_month_btn = QPushButton("이번달")
        this_month_btn.clicked.connect(self._this_month)
        ctrl.addWidget(this_month_btn)
        last_month_btn = QPushButton("지난달")
        last_month_btn.clicked.connect(self._last_month)
        ctrl.addWidget(last_month_btn)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # 요약 라벨
        self.summary = QLabel("")
        self.summary.setStyleSheet(
            "padding: 6px 12px; background: #FDEDEC; border-radius: 5px;"
            "font-weight: bold; color: #922B21;")
        layout.addWidget(self.summary)

        # 고객 반품 표
        layout.addWidget(QLabel("📦 고객 반품 (주문 취소·반품 처리된 건)"))
        self.return_table = QTableWidget()
        self.return_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.return_table, stretch=1)

        # 직접 반출 표
        layout.addWidget(QLabel("🚚 직접 반출 (입고관리에서 반출 등록한 건)"))
        self.outgoing_table = QTableWidget()
        self.outgoing_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.outgoing_table, stretch=1)

        self._sort_r = {"column": None, "ascending": True}
        self._sort_o = {"column": None, "ascending": True}
        enable_header_click_sort(self.return_table, self._sort_r, self.refresh)
        enable_header_click_sort(self.outgoing_table, self._sort_o, self.refresh)

    def _this_month(self):
        t = QDate.currentDate()
        self.date_from.setDate(QDate(t.year(), t.month(), 1))
        self.date_to.setDate(t)
        self.refresh()

    def _last_month(self):
        t = QDate.currentDate()
        first = QDate(t.year(), t.month(), 1)
        end = first.addDays(-1)
        self.date_from.setDate(QDate(end.year(), end.month(), 1))
        self.date_to.setDate(end)
        self.refresh()

    def refresh(self):
        df = self.date_from.date().toString("yyyy-MM-dd")
        dt = self.date_to.date().toString("yyyy-MM-dd")

        # 고객 반품: 주문 상태 '반품' + 취소
        try:
            orders = db.get_orders(date_from=df, date_to=dt)
            returned = [o for o in orders if (o["status"] or "") in ("반품", "취소")]
        except Exception:
            returned = []

        r_total = sum(o["total_amount"] or 0 for o in returned)
        r_rows = [(o["order_date"], o["channel_name"] or "", o["buyer_name"] or "",
                   o["product_name"] or "", o["option_name"] or "",
                   f"{o['qty']:,}개", fmt_price(o["sale_price"] or 0),
                   fmt_won(o["total_amount"] or 0), o["status"] or "",
                   o["memo"] or "")
                  for o in returned]
        fill_table(self.return_table,
                   ["주문일", "채널", "구매자", "상품명", "옵션", "수량", "단가", "금액", "상태", "메모"],
                   r_rows, persist_key="return_status", sort_state=self._sort_r)

        # 직접 반출: 입고관리 반출 건
        try:
            outgoing = db.get_returns(return_type="반출", date_from=df, date_to=dt)
        except Exception:
            outgoing = []

        o_total = sum(r["total_price"] or 0 for r in outgoing)
        o_rows = [(r["return_date"], r["channel_name"] or "", r["product_name"] or "",
                   f"{r['qty']:,}개", fmt_price(r["unit_price"] or 0),
                   fmt_won(r["total_price"] or 0), r["reason"] or "", r["memo"] or "")
                  for r in outgoing]
        fill_table(self.outgoing_table,
                   ["반출일", "거래처", "상품명", "수량", "단가", "금액", "사유", "메모"],
                   o_rows, persist_key="outgoing_status", sort_state=self._sort_o)

        self.summary.setText(
            f"고객 반품 {len(returned)}건  |  반품 금액: {fmt_won(r_total)}   ·   "
            f"직접 반출 {len(outgoing)}건  |  반출 금액: {fmt_won(o_total)}")


class StockStatusTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        control_row = QHBoxLayout()
        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        control_row.addWidget(refresh_btn)
        control_row.addStretch()
        layout.addLayout(control_row)

        note = QLabel("💡 재고금액 = 원가 × 재고수량. 품목관리에서 재고를 조정하면 여기도 함께 갱신돼요.")
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 6px; background: #f0f0f0;")
        layout.addWidget(self.summary_label)

        chart_row = QHBoxLayout()
        self.chart_box = QGroupBox("재고금액 상위 품목")
        self.chart_layout = QVBoxLayout(self.chart_box)
        chart_row.addWidget(self.chart_box)
        layout.addLayout(chart_row)

        self.table = QTableWidget()
        layout.addWidget(self.table)

        self._canvas = None
        self._sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort_state, self.refresh)
        enlarge_row_numbers(self.table)
        self.refresh()

    def refresh(self):
        products = db.get_stock_status()

        total_qty = sum(p["stock_qty"] or 0 for p in products)
        total_value = sum(p["stock_value"] or 0 for p in products)
        out_of_stock = sum(1 for p in products if (p["stock_qty"] or 0) <= 0)
        self.summary_label.setText(
            f"총 품목수: {len(products)}개   |   총 재고수량: {total_qty:,}개   |   "
            f"총 재고금액: {fmt_won(total_value)}   |   품절 품목: {out_of_stock}개"
        )

        top = products[:10]
        categories = [f"{p['name']} {p['option_name']}".strip() if p["option_name"] else p["name"] for p in top]
        series = {"재고금액": [p["stock_value"] or 0 for p in top]}
        new_canvas = charts.bar_chart_canvas(categories, series, ylabel="금액(원)") if categories \
            else charts.empty_message_canvas("등록된 품목이 없습니다")
        if self._canvas is not None:
            self.chart_layout.removeWidget(self._canvas)
            self._canvas.setParent(None)
        self.chart_layout.addWidget(new_canvas)
        self._canvas = new_canvas

        headers = ["SKU", "상품명(대분류)", "옵션(소분류)", "원가", "판매가", "재고수량", "재고금액"]
        table_rows = [
            (p["sku"], p["name"], p["option_name"] or "", fmt_won(p["cost_price"]), fmt_won(p["sale_price"]),
             f"{'⚠️ ' if (p['stock_qty'] or 0) <= 0 else ''}{p['stock_qty'] or 0}개",
             fmt_won(p["stock_value"]))
            for p in products
        ]
        fill_table(self.table, headers, table_rows, persist_key="stock_status", sort_state=self._sort_state)


class UnsettledOrderAmountPickerDialog(QDialog):
    def _load(self):
        """미수금(미정산) 주문 목록을 다시 채움"""
        self._unsettled = [o for o in db.get_orders(channel_id=self.channel_id)
                           if not o["is_settled"]]
        self._amounts = [sum((o["settlement_amount"] or 0) for o in self._unsettled)]
        headers = ["주문번호", "주문일", "구매자", "정산예정금액"]
        rows = [("(전체 미수금 합계)", "", "", fmt_won(self._amounts[0]))]
        for o in self._unsettled:
            self._amounts.append(o["settlement_amount"] or 0)
            rows.append((o["order_no"], o["order_date"], o["buyer_name"],
                         fmt_won(o["settlement_amount"])))
        fill_table(self.table, headers, rows)

    def mark_selected_settled(self):
        """이미 돈을 받은 주문을 정산완료로 바꿔 미수금 목록에서 빼줌.
        (예전에 등록한 입금은 주문 상태를 바꾸지 않아 계속 남아 있었음)"""
        row = self.table.currentRow()
        if row <= 0 or row > len(self._unsettled):
            QMessageBox.warning(self, "알림",
                                "정산완료로 바꿀 주문을 목록에서 골라주세요.\n"
                                "(첫 줄 '전체 미수금 합계'는 고를 수 없어요)")
            return
        o = self._unsettled[row - 1]
        amt = o["settlement_amount"] or 0
        if QMessageBox.question(
                self, "정산완료 처리",
                f"주문번호 {o['order_no']}\n금액 {fmt_won(amt)}\n\n"
                "이 주문을 '정산완료'로 바꿀까요?\n"
                "(미수금 목록에서 빠지며, 입금 내역이 새로 생기지는 않습니다)") != QMessageBox.Yes:
            return
        db.mark_orders_settled([(o["id"], amt,
                                 o["order_date"] or date.today().strftime("%Y-%m-%d"))])
        notify_data_changed()
        self._load()
        QMessageBox.information(self, "완료", "정산완료로 처리했습니다.")

    """정산입금 입금액 입력 시 - 선택된 채널/거래처의 미수금(미결제 주문) 목록에서
    금액을 골라올 수 있게 하는 창"""

    def __init__(self, channel_id, channel_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{channel_name} - 미수금 내역에서 선택")
        self.resize(650, 420)
        self.selected_amount = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"💰 {channel_name} 미수금(미결제 주문) 목록 - 더블클릭하면 그 금액이 선택됩니다"))

        self.channel_id = channel_id
        self.channel_name = channel_name
        self.table = QTableWidget()
        self._load()
        self.table.cellDoubleClicked.connect(lambda r, c: self.confirm_selection())
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        settle_btn = QPushButton("💰 선택 건 정산완료 처리")
        settle_btn.setToolTip("이미 입금받은 주문을 정산완료로 바꿔 미수금에서 빼줍니다")
        settle_btn.clicked.connect(self.mark_selected_settled)
        btn_row.addWidget(settle_btn)
        select_btn = QPushButton("✅ 선택")
        select_btn.clicked.connect(self.confirm_selection)
        btn_row.addWidget(select_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def confirm_selection(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._amounts):
            QMessageBox.warning(self, "알림", "항목을 선택해주세요.")
            return
        self.selected_amount = self._amounts[row]
        self.accept()


class UnpaidPurchaseAmountPickerDialog(QDialog):
    """매입지출 결제금액 입력 시 - 선택된 거래처의 미결제 입고건 목록에서
    금액을 골라올 수 있게 하는 창"""

    def __init__(self, supplier_id, supplier_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{supplier_name} - 미결제 내역에서 선택")
        self.resize(650, 420)
        self.selected_amount = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"📦 {supplier_name} 미결제 입고건 목록 - 더블클릭하면 그 금액이 선택됩니다"))
        try:
            unpaid, rate, discount, payable = db.get_supplier_unpaid_with_discount(supplier_id)
            if rate:
                disc_label = QLabel(
                    f"💰 매입 할인율 {rate:g}% 적용   |   미결제 원금 {fmt_won(unpaid)}   −   "
                    f"할인 {fmt_won(discount)}   =   실제 결제금액 <b>{fmt_won(payable)}</b>")
                disc_label.setTextFormat(Qt.RichText)
                disc_label.setStyleSheet(
                    "padding: 8px; background: #FEF9E7; border: 1px solid #F7DC6F; border-radius: 6px;")
                layout.addWidget(disc_label)
                self._discounted_payable = payable
        except Exception:
            pass

        purchases = db.get_purchases(supplier_id=supplier_id)
        unpaid_list = [(p, (p["total_amount"] or 0) - (p["paid_amount"] or 0)) for p in purchases]
        unpaid_list = [(p, amt) for p, amt in unpaid_list if amt > 0]
        self._amounts = [sum(amt for _, amt in unpaid_list)]  # 0번: 전체합계
        total = self._amounts[0]

        self.table = QTableWidget()
        headers = ["입고일", "품목명", "합계금액", "지급액", "미결제"]
        rows = [("(전체 미결제 합계)", "", "", "", fmt_won(total))]
        discounted = getattr(self, "_discounted_payable", None)
        if discounted is not None and discounted != total:
            self._amounts.append(discounted)
            rows.append(("(할인 적용 결제금액)", "", "", "", fmt_won(discounted)))
        for p, amt in unpaid_list:
            self._amounts.append(amt)
            rows.append((p["purchase_date"], p["product_name"], fmt_won(p["total_amount"]),
                         fmt_won(p["paid_amount"]), fmt_won(amt)))
        fill_table(self.table, headers, rows)
        self.table.cellDoubleClicked.connect(lambda r, c: self.confirm_selection())
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        select_btn = QPushButton("✅ 선택")
        select_btn.clicked.connect(self.confirm_selection)
        btn_row.addWidget(select_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def confirm_selection(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._amounts):
            QMessageBox.warning(self, "알림", "항목을 선택해주세요.")
            return
        self.selected_amount = self._amounts[row]
        self.accept()


class ReceivableDetailDialog(QDialog):
    """미수현황에서 채널/거래처 더블클릭 시: 상세 주문내역 + 거래원장 출력(엑셀/PDF)"""

    def __init__(self, channel_id, channel_name, parent=None):
        super().__init__(parent)
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.setWindowTitle(f"{channel_name} - 미수금 상세 / 거래원장")
        self.resize(900, 600)

        layout = QVBoxLayout(self)
        title = QLabel(f"💰 {channel_name} 상세 내역")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        control_row = QHBoxLayout()
        self.date_from = make_date_edit()
        self.date_from.setDate(QDate.currentDate().addMonths(-3))
        control_row.addWidget(tight_pair("시작일:", self.date_from))
        self.date_to = make_date_edit()
        self.date_to.setDate(QDate.currentDate())
        control_row.addWidget(tight_pair("종료일:", self.date_to))
        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh)
        control_row.addWidget(search_btn)
        control_row.addStretch()
        excel_btn = QPushButton("📊 거래원장 엑셀 출력")
        excel_btn.clicked.connect(self.export_excel)
        control_row.addWidget(excel_btn)
        pdf_btn = QPushButton("📄 거래원장 PDF 출력")
        pdf_btn.clicked.connect(self.export_pdf)
        control_row.addWidget(pdf_btn)
        layout.addLayout(control_row)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("padding: 6px; background: #f0f0f0;")
        layout.addWidget(self.summary_label)

        self._sort_state = {"column": None, "ascending": False}
        self.table = QTableWidget()
        layout.addWidget(self.table)
        enable_header_click_sort(self.table, self._sort_state, self.refresh)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.refresh()

    def _current_range(self):
        return self.date_from.date().toString("yyyy-MM-dd"), self.date_to.date().toString("yyyy-MM-dd")

    def refresh(self):
        date_from, date_to = self._current_range()
        self._entries = db.get_ledger_entries(self.channel_id, date_from, date_to)
        opening = next((e["balance"] for e in self._entries if e.get("is_opening")), 0)
        sales_total = sum(e["amount"] for e in self._entries
                          if e.get("kind") == "매출")
        received_total = sum(-e["amount"] for e in self._entries if e.get("kind") == "입금")
        balance = opening + sales_total - received_total
        self.summary_label.setText(
            (f"전기이월: {fmt_won(opening)}   |   " if opening else "")
            + f"조회기간 매출: {fmt_won(sales_total)}   |   입금: {fmt_won(received_total)}   |   "
            f"잔액(미수금): {fmt_won(balance)}   |   라인 수: {len(self._entries)}건"
        )

        headers = ["일자", "거래처명", "구매자", "거래형식", "품목", "수량", "단가",
                   "합계금액", "미수금액", "정산여부", "적요"]
        rows = [
            (e["date"], self.channel_name, e.get("buyer", ""), e.get("kind", "매출"),
             e["product"], e["qty"], fmt_price(e["unit_price"]), fmt_price(e["amount"]),
             fmt_won(e.get("balance", 0)), e.get("settled", ""), "")
            for e in self._entries
        ]
        fill_table(self.table, headers, rows, persist_key="receivable_detail", sort_state=self._sort_state)
        # 입금 라인은 파란 배경으로 구분
        # (정렬하면 행 순서가 바뀌므로, 표에 실제로 그려진 '거래형식' 값을 보고 판단)
        try:
            kind_col = headers.index("거래형식")
        except ValueError:
            kind_col = 2
        for r in range(self.table.rowCount()):
            kind_item = self.table.item(r, kind_col)
            if kind_item and "이월" in kind_item.text():
                for col in range(self.table.columnCount()):
                    item = self.table.item(r, col)
                    if item:
                        item.setBackground(QColor("#FDEBD0"))
                        f = item.font(); f.setBold(True); item.setFont(f)
            elif kind_item and "입금" in kind_item.text():
                for col in range(self.table.columnCount()):
                    item = self.table.item(r, col)
                    if item:
                        item.setBackground(QColor("#D6EAF8"))
                        item.setForeground(QColor("#1A5276"))

    def export_excel(self):
        date_from, date_to = self._current_range()
        export_ledger_to_excel(self, self.channel_name, date_from, date_to, self._entries)

    def export_pdf(self):
        date_from, date_to = self._current_range()
        export_ledger_to_pdf(self, self.channel_name, date_from, date_to, self._entries)


class PayableDetailDialog(QDialog):
    """미결재현황에서 거래처 더블클릭 시: 매입(입고) + 지급(결제) 통합 상세"""

    def __init__(self, supplier_id, supplier_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{supplier_name} - 미결제 상세")
        self.resize(900, 520)

        layout = QVBoxLayout(self)
        title = QLabel(f"📦 {supplier_name} 매입 / 지급 상세 내역")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        purchases = db.get_purchases(supplier_id=supplier_id)
        payments = db.get_purchase_payments(supplier_id=supplier_id)

        total_purchase = sum(p["total_amount"] or 0 for p in purchases)
        total_paid = sum(pm["amount"] or 0 for pm in payments)
        summary = QLabel(
            f"총 매입금액: {fmt_won(total_purchase)}   |   총 지급액: {fmt_won(total_paid)}   |   "
            f"미결제금액: {fmt_won(total_purchase - total_paid)}"
        )
        summary.setStyleSheet("padding: 6px; background: #f0f0f0; font-weight: bold;")
        layout.addWidget(summary)

        # 매입(+)과 지급(-)을 하나의 시간순 원장으로 합침
        entries = []
        for p in purchases:
            entries.append({
                "date": p["purchase_date"], "kind": "매입",
                "item": (f"{p['product_name'] or ''} {p['option_name'] or ''}".strip()
                          or p["option_name"] or p["product_name"] or ""),
                "qty": p["qty"] or 0, "unit": p["unit_cost"] or 0,
                "amount": p["total_amount"] or 0,
                "method": "", "paid": 0,
            })
        for pm in payments:
            bank = pm["bank_account_name"] or "현금"
            entries.append({
                "date": pm["payment_date"], "kind": "지급",
                "item": pm["memo"] or "매입대금 결제",
                "qty": "", "unit": "",
                "amount": 0,
                "method": bank, "paid": pm["amount"] or 0,
            })
        entries.sort(key=lambda e: (e["date"] or "", e["kind"]))

        running = 0
        rows = []
        for e in entries:
            running += e["amount"] - e["paid"]
            rows.append((
                e["date"], e["kind"], e["item"],
                f"{e['qty']:,}" if e["qty"] != "" else "",
                fmt_price(e["unit"]) if e["unit"] != "" else "",
                fmt_price(e["amount"]) if e["amount"] else "",
                e["method"],
                fmt_won(e["paid"]) if e["paid"] else "",
                fmt_won(running),
            ))
        rows.reverse()  # 최근 건이 위로

        table = QTableWidget()
        self.table = table
        headers = ["일자", "구분", "품목(옵션)/적요", "수량", "단가", "매입금액",
                   "지급방법", "지급액", "미결제잔액"]
        fill_table(table, headers, rows, persist_key="payable_detail")
        layout.addWidget(table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class DuplicateOrderCheckDialog(QDialog):
    """주문 파일에 똑같은 주문이 여러 줄 들어있을 때 확인받는 창.

    같은 주문을 소분해서 보내느라 줄을 나눠 적는 경우도 있고,
    파일을 두 번 받아 붙였거나 마켓에서 중복 출력된 경우도 있음.
    그대로 등록하면 매출과 재고가 두 배로 잡히므로 먼저 확인받음.
    """

    def __init__(self, groups, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ 중복 의심 주문 확인")
        self.resize(920, 480)
        self.groups = groups

        layout = QVBoxLayout(self)
        title = QLabel("⚠️ 똑같은 주문이 여러 줄 들어있어요")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color:#C0392B;")
        layout.addWidget(title)

        note = QLabel(
            "주문번호·상품·옵션·수량이 모두 같은 줄이 발견됐습니다.<br>"
            "· <b>소분해서 보내려고 줄을 나눈 것</b>이면 그대로 두세요 (체크 해제)<br>"
            "· <b>파일이 중복으로 들어간 것</b>이면 한 줄만 남기세요 (체크)<br><br>"
            "⚠️ 중복인데 그대로 등록하면 <b>매출과 재고가 두 배로</b> 잡힙니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555; background:#FEF9E7; padding:8px; border-radius:6px;")
        layout.addWidget(note)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["한 줄만 남기기", "주문번호", "상품명", "옵션", "수량", "금액", "같은 줄 수"])
        self.table.setRowCount(len(groups))
        self.checks = []
        for r, g in enumerate(groups):
            cb = QCheckBox()
            cb.setChecked(True)      # 기본은 중복 제거 (안전한 쪽)
            holder = QWidget(); hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0); hl.setAlignment(Qt.AlignCenter)
            hl.addWidget(cb)
            self.table.setCellWidget(r, 0, holder)
            self.checks.append(cb)
            first = g["rows"][0]
            vals = [first.get("order_no", ""), first.get("product_name", ""),
                    first.get("option_name", ""), f"{first.get('qty', 0):,}",
                    fmt_won(first.get("total_amount", 0)), f"{len(g['rows'])}줄"]
            for c, v in enumerate(vals, start=1):
                item = QTableWidgetItem(str(v))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if c in (4, 5, 6):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 6:
                    f = item.font(); f.setBold(True); item.setFont(f)
                    item.setForeground(QColor("#C0392B"))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(2, 260)
        layout.addWidget(self.table)

        sel_row = QHBoxLayout()
        all_btn = QPushButton("전체 체크 (중복 제거)")
        all_btn.clicked.connect(lambda: [c.setChecked(True) for c in self.checks])
        none_btn = QPushButton("전체 해제 (모두 등록)")
        none_btn.clicked.connect(lambda: [c.setChecked(False) for c in self.checks])
        sel_row.addWidget(all_btn); sel_row.addWidget(none_btn); sel_row.addStretch()
        layout.addLayout(sel_row)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("✅ 이대로 진행")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("업로드 취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def dedupe_keys(self):
        """한 줄만 남기기로 체크된 그룹의 키 목록"""
        return {self.groups[i]["key"] for i, c in enumerate(self.checks) if c.isChecked()}


class SettlementDepositDialog(QDialog):
    """정산 파일 업로드 후, 통장에 실제로 들어온 금액을 확인하는 창.

    마켓은 파일 합계를 그대로 주지 않는 경우가 많음.
      · 쿠팡 주정산 : 정산대상액의 70%만 먼저 지급, 나머지는 월정산
      · 광고비 등   : 정산에서 미리 빼고 지급
    쿠팡 정산 화면과 같은 순서로 입력하면 최종 입금액이 자동 계산됨.
        최종지급액 = 정산대상액 × 지급비율 − 공제금액
    """

    def __init__(self, calc_total, channel_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("정산 입금액 확인")
        self.resize(480, 400)
        self.calc_total = int(calc_total or 0)

        layout = QVBoxLayout(self)
        title = QLabel("💰 통장에 들어온 금액 확인")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        note = QLabel(
            "💡 파일로 계산한 금액과 통장에 실제 들어온 금액이 다를 수 있어요.<br>"
            "<b>쿠팡</b>은 주정산에서 정산대상액의 <b>70%</b>만 먼저 주고, "
            "광고비 등을 빼고 입금합니다.<br>"
            "마켓 정산 화면의 숫자를 그대로 넣으면 됩니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555; background:#FEF9E7; padding:8px; border-radius:6px;")
        layout.addWidget(note)

        form = QFormLayout()
        self.base_label = QLabel(fmt_won(self.calc_total))
        self.base_label.setStyleSheet("font-weight:bold; font-size:14px;")
        form.addRow("정산대상액 (파일 계산)", self.base_label)

        self.rate_input = QLineEdit("100")
        self.rate_input.setFixedWidth(90)
        self.rate_input.setToolTip("쿠팡 주정산이면 70, 전액 지급이면 100")
        rate_row = QWidget(); rr = QHBoxLayout(rate_row)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.addWidget(self.rate_input); rr.addWidget(QLabel("%"))
        for label, val in (("전액 100%", "100"), ("쿠팡 주정산 70%", "70")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, v=val: (self.rate_input.setText(v), self._recalc()))
            rr.addWidget(b)
        rr.addStretch()
        form.addRow("지급비율", rate_row)

        self.deduct_input = QLineEdit("0")
        self.deduct_input.setFixedWidth(130)
        self.deduct_input.setPlaceholderText("예: 109365")
        form.addRow("공제금액 (광고비 등)", self.deduct_input)

        self.deduct_name = QLineEdit("광고비")
        self.deduct_name.setPlaceholderText("공제 항목 이름")
        form.addRow("공제 항목명", self.deduct_name)
        layout.addLayout(form)

        self.expense_cb = QCheckBox("공제금액을 지출로도 함께 등록하기")
        self.expense_cb.setChecked(True)
        self.expense_cb.setToolTip("정산에서 미리 빠진 광고비 등을 지출 내역에도 남깁니다")
        layout.addWidget(self.expense_cb)

        self.result_label = QLabel("")
        self.result_label.setStyleSheet(
            "padding:10px; background:#EAF2F8; border-radius:6px;"
            "color:#1A5276; font-size:14px;")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        final_row = QHBoxLayout()
        self.final_input = QLineEdit()
        self.final_input.setFixedWidth(160)
        self.final_input.setStyleSheet("font-weight:bold; font-size:14px;")
        final_row.addWidget(QLabel("통장에 기록할 최종 입금액:"))
        final_row.addWidget(self.final_input)
        final_row.addStretch()
        layout.addLayout(final_row)

        hint = QLabel("    └ 자동 계산된 값입니다. 실제 입금액과 다르면 직접 고쳐주세요.")
        hint.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(hint)

        self.rate_input.textEdited.connect(self._recalc)
        self.deduct_input.textEdited.connect(self._recalc)
        self._recalc()

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("✅ 이 금액으로 기록")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("파일 금액 그대로")
        cancel_btn.clicked.connect(self._use_file_total)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _recalc(self, *_):
        rate = to_float(self.rate_input.text(), 100)
        deduct = to_int(self.deduct_input.text(), 0)
        pay = int(round(self.calc_total * rate / 100.0))
        final = pay - deduct
        self.result_label.setText(
            f"정산대상액 {fmt_won(self.calc_total)}<br>"
            f"× 지급비율 {rate:g}%  =  {fmt_won(pay)}<br>"
            f"− 공제금액 {fmt_won(deduct)}<br>"
            f"<b>= 최종 입금액 {fmt_won(final)}</b>")
        self.final_input.setText(str(final))

    def _use_file_total(self):
        self.rate_input.setText("100")
        self.deduct_input.setText("0")
        self._recalc()
        self.accept()

    def result(self):
        """(최종 입금액, 공제금액, 공제항목명, 지출등록 여부)"""
        return (to_int(self.final_input.text(), self.calc_total),
                to_int(self.deduct_input.text(), 0),
                self.deduct_name.text().strip() or "광고비",
                self.expense_cb.isChecked())


class SettlementStatusTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)

        # 미수(왼쪽) / 미결재(오른쪽)를 나란히 배치
        columns = QHBoxLayout()
        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        columns.addLayout(left_col, stretch=1)
        columns.addLayout(right_col, stretch=1)
        layout.addLayout(columns)

        self.receivable_summary = QLabel("")
        self.receivable_summary.setStyleSheet(
            "font-weight: bold; color: #1A5276; background: #EAF2F8;"
            "padding: 6px 10px; border-radius: 5px;")
        left_col.addWidget(QLabel("💰 미수현황 (매출채권) - 아직 못 받은 돈\n더블클릭하면 상세/거래원장"))
        left_col.addWidget(self.receivable_summary)
        self.channel_table = QTableWidget()
        self.channel_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.channel_table.cellDoubleClicked.connect(self.on_channel_double_clicked)
        left_col.addWidget(self.channel_table)

        self.payable_summary = QLabel("")
        self.payable_summary.setStyleSheet(
            "font-weight: bold; color: #7D6608; background: #FEF9E7;"
            "padding: 6px 10px; border-radius: 5px;")
        right_col.addWidget(QLabel("📦 미결재현황 (매입채무) - 아직 안 준 돈\n더블클릭하면 상세"))
        right_col.addWidget(self.payable_summary)
        self.supplier_table = QTableWidget()
        self.supplier_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.supplier_table.cellDoubleClicked.connect(self.on_supplier_double_clicked)
        right_col.addWidget(self.supplier_table)

        self._channel_sort_state = {"column": None, "ascending": True}
        self._supplier_sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.channel_table, self._channel_sort_state, self.refresh)
        enable_header_click_sort(self.supplier_table, self._supplier_sort_state, self.refresh)
        enlarge_row_numbers(self.channel_table)
        enlarge_row_numbers(self.supplier_table)
        self.refresh()

    def refresh(self):
        # 미수금이 남아있는 곳만 표시하고, 온라인 채널 -> 일반거래처(가나다순) 순으로 정렬
        channel_rows = [r for r in db.get_channel_unsettled_summary()
                        if r["order_count"] and (r["unsettled"] or 0) != 0]
        channel_types = {ch["id"]: (ch["channel_type"] or "온라인채널") for ch in db.get_channels()}
        channel_rows.sort(key=lambda r: (
            0 if channel_types.get(r["channel_id"], "온라인채널") == "온라인채널" else 1,
            r["channel_name"] or ""))
        channel_ids = [r["channel_id"] for r in channel_rows]
        headers1 = ["채널/거래처", "주문건수", "매출액(정산예정)", "미수금"]
        rows1 = [
            (r["channel_name"], r["order_count"], fmt_won(r["total_expected"]),
             fmt_won(r["unsettled"]))
            for r in channel_rows
        ]
        self._channel_ids = fill_table(self.channel_table, headers1, rows1, persist_key="settlement_status_channel",
                                        sort_state=self._channel_sort_state, id_list=channel_ids)
        _bold_column(self.channel_table, 3)      # 미수금 컬럼 강조
        total_unsettled = sum(r["unsettled"] or 0 for r in channel_rows)
        self.receivable_summary.setText(
            f"합계 {len(channel_rows)}곳  |  미수금 총액: {fmt_won(total_unsettled)}")

        supplier_rows = [r for r in db.get_supplier_unpaid_summary()
                         if r["purchase_count"] and (r["unpaid"] or 0) != 0]
        supplier_rows.sort(key=lambda r: r["supplier_name"] or "")
        supplier_ids = [r["supplier_id"] for r in supplier_rows]
        headers2 = ["거래처", "매입건수", "총 매입금액", "지급액", "미결제금액"]
        rows2 = [
            (r["supplier_name"], r["purchase_count"], fmt_won(r["total_purchase"]),
             fmt_won(r["total_paid"]), fmt_won(r["unpaid"]))
            for r in supplier_rows
        ]
        self._supplier_ids = fill_table(self.supplier_table, headers2, rows2, persist_key="settlement_status_supplier",
                                         sort_state=self._supplier_sort_state, id_list=supplier_ids)
        _bold_column(self.supplier_table, 4)     # 미결제금액 컬럼 강조
        total_unpaid = sum(r["unpaid"] or 0 for r in supplier_rows)
        self.payable_summary.setText(
            f"합계 {len(supplier_rows)}곳  |  미결제 총액: {fmt_won(total_unpaid)}")

    def on_channel_double_clicked(self, row, column):
        if row < 0 or row >= len(self._channel_ids):
            return
        channel_id = self._channel_ids[row]
        channel_name = self.channel_table.item(row, 0).text()
        dialog = ReceivableDetailDialog(channel_id, channel_name, self)
        dialog.exec()

    def on_supplier_double_clicked(self, row, column):
        if row < 0 or row >= len(self._supplier_ids):
            return
        supplier_id = self._supplier_ids[row]
        supplier_name = self.supplier_table.item(row, 0).text()
        dialog = PayableDetailDialog(supplier_id, supplier_name, self)
        dialog.exec()


# ---------------------------------------------------------------------------
# 리포트 탭 (서브탭 5개를 묶는 컨테이너)
# ---------------------------------------------------------------------------
class ShippingFeeRateDialog(QDialog):
    """채널별 '배송비에 붙는 수수료율(%)' 설정.
    여기서 정한 비율만큼을 배송비에서 빼고, 남은 순액만 수익으로 잡습니다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("채널별 배송비 수수료율 설정")
        self.resize(620, 460)
        layout = QVBoxLayout(self)

        title = QLabel("🚚 채널별 배송비 수수료율")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        note = QLabel(
            "💡 마켓은 상품값뿐 아니라 <b>배송비에도 수수료를 떼갑니다.</b><br>"
            "여기에 채널별 수수료율(%)을 넣어두면, 배송비에서 그만큼을 뺀 "
            "<b>순액만 수익</b>으로 잡습니다.<br>"
            "예) 배송비 3,000원 · 수수료율 10% → 수수료 300원, 순수익 2,700원<br>"
            "수수료를 떼지 않는 채널은 0으로 두면 배송비 전액이 수익이 됩니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555; background:#FEF9E7; padding:8px; border-radius:6px;")
        layout.addWidget(note)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        edit_row = QHBoxLayout()
        self.rate_input = QLineEdit()
        self.rate_input.setPlaceholderText("예: 10  (10%)")
        self.rate_input.setFixedWidth(120)
        edit_row.addWidget(tight_pair("선택한 채널의 수수료율(%):", self.rate_input))
        save_btn = QPushButton("💾 적용")
        save_btn.setToolTip("저장하면 기존 주문의 배송비 순수익도 이 비율로 다시 계산됩니다")
        save_btn.clicked.connect(self.save_rate)
        edit_row.addWidget(save_btn)
        edit_row.addStretch()
        layout.addLayout(edit_row)

        btn_row = QHBoxLayout()
        recalc_btn = QPushButton("🔄 전체 다시 계산")
        recalc_btn.setToolTip("모든 주문의 배송비 순수익을 현재 수수료율 기준으로 다시 계산합니다")
        recalc_btn.clicked.connect(self.recalc_all)
        btn_row.addWidget(recalc_btn)
        btn_row.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.table.currentCellChanged.connect(self._on_row_changed)
        self.refresh()

    def refresh(self):
        self._rows = db.get_all_channel_shipping_rates()
        fill_table(self.table, ["채널/거래처", "유형", "배송비 수수료율"],
                   [(r["name"], r["channel_type"], f"{r['shipping_fee_rate']:.1f}%")
                    for r in self._rows])

    def _on_row_changed(self, row, *_):
        if 0 <= row < len(self._rows):
            self.rate_input.setText(f"{self._rows[row]['shipping_fee_rate']:.1f}")

    def save_rate(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            QMessageBox.warning(self, "알림", "먼저 표에서 채널을 선택해주세요.")
            return
        rate = to_float(self.rate_input.text(), -1)
        if rate < 0 or rate > 100:
            QMessageBox.warning(self, "알림", "수수료율은 0~100 사이의 숫자로 입력해주세요.")
            return
        ch = self._rows[row]
        updated = db.set_channel_shipping_fee_rate(ch["id"], rate)
        self.refresh()
        notify_data_changed()
        QMessageBox.information(
            self, "완료",
            f"'{ch['name']}'의 배송비 수수료율을 {rate:.1f}%로 저장했습니다.\n"
            f"배송비가 있는 주문 {updated:,}건의 순수익을 다시 계산했습니다.")

    def recalc_all(self):
        updated = db.recalc_shipping_revenue()
        notify_data_changed()
        QMessageBox.information(self, "완료",
                                f"배송비가 있는 주문 {updated:,}건의 순수익을 다시 계산했습니다.")


class ShippingOrderDetailDialog(QDialog):
    """특정 채널의 배송비 발생 주문 상세"""

    def __init__(self, channel_id, channel_name, date_from, date_to, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"배송비 상세 - {channel_name}")
        self.resize(1000, 520)
        layout = QVBoxLayout(self)

        title = QLabel(f"🚚 {channel_name}  배송비 상세  ({date_from} ~ {date_to})")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        rows = db.get_shipping_orders(channel_id, date_from, date_to)
        total = sum(r["shipping_fee"] for r in rows)
        charge = sum(r["shipping_fee_charge"] for r in rows)
        net = sum(r["shipping_net"] for r in rows)

        summary = QLabel(
            f"총 {len(rows):,}건  |  받은 배송비 {fmt_won(total)}  |  "
            f"수수료 {fmt_won(charge)}  |  <b>순수익 {fmt_won(net)}</b>")
        summary.setStyleSheet("padding:6px 12px; background:#EAF2F8;"
                              "border-radius:5px; color:#1A5276;")
        layout.addWidget(summary)

        table = QTableWidget()
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        fill_table(table,
                   ["주문일", "주문번호", "상품명", "옵션", "구매자",
                    "받은 배송비", "수수료율", "수수료", "순수익"],
                   [(r["order_date"], r["order_no"], r["product_name"], r["option_name"],
                     r["buyer_name"], fmt_won(r["shipping_fee"]),
                     f"{r['shipping_fee_rate']:.1f}%",
                     fmt_won(r["shipping_fee_charge"]), fmt_won(r["shipping_net"]))
                    for r in rows],
                   persist_key="shipping_detail")
        layout.addWidget(table)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class ShippingRevenueTab(QWidget):
    """리포트 > 배송비 수익 (수수료 제외 순액)
    채널별로 배송비가 얼마나 발생했는지, 그중 수수료를 뺀 순수익이 얼마인지 봅니다."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("🚚 배송비 수익 (수수료 제외 순액)")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        note = QLabel("💡 배송비는 매출에 섞지 않고 <b>별도 수익 항목</b>으로 잡습니다. "
                      "고객에게 받은 배송비에서 마켓이 떼가는 수수료를 뺀 순액만 수익입니다. "
                      "채널 행을 더블클릭하면 주문별 상세를 볼 수 있어요.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        layout.addWidget(note)

        ctrl = QHBoxLayout()
        self.date_from = make_date_edit()
        self.date_from.setDate(QDate(QDate.currentDate().year(), QDate.currentDate().month(), 1))
        self.date_to = make_date_edit()
        self.date_to.setDate(QDate.currentDate())
        ctrl.addWidget(tight_pair("시작일:", self.date_from))
        ctrl.addWidget(tight_pair("종료일:", self.date_to))
        search_btn = QPushButton("조회")
        search_btn.clicked.connect(self.refresh)
        ctrl.addWidget(search_btn)
        this_month_btn = QPushButton("이번달")
        this_month_btn.clicked.connect(self._this_month)
        ctrl.addWidget(this_month_btn)
        last_month_btn = QPushButton("지난달")
        last_month_btn.clicked.connect(self._last_month)
        ctrl.addWidget(last_month_btn)
        this_year_btn = QPushButton("올해")
        this_year_btn.clicked.connect(self._this_year)
        ctrl.addWidget(this_year_btn)
        ctrl.addStretch()
        rate_btn = QPushButton("⚙️ 채널별 수수료율 설정")
        rate_btn.clicked.connect(self.open_rate_dialog)
        ctrl.addWidget(rate_btn)
        export_btn = QPushButton("📄 엑셀로 내보내기")
        export_btn.clicked.connect(self.export_excel)
        ctrl.addWidget(export_btn)
        layout.addLayout(ctrl)

        self.summary = QLabel("")
        self.summary.setStyleSheet("padding:8px 12px; background:#EAF2F8;"
                                   "border-radius:5px; font-weight:bold; color:#1A5276;")
        layout.addWidget(self.summary)

        ch_label = QLabel("📊 채널별 배송비 발생 현황")
        ch_label.setStyleSheet("font-weight:bold; padding-top:6px;")
        layout.addWidget(ch_label)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_double_clicked)
        layout.addWidget(self.table)

        m_label = QLabel("📅 월별 배송비 추이")
        m_label.setStyleSheet("font-weight:bold; padding-top:6px;")
        layout.addWidget(m_label)

        self.month_table = QTableWidget()
        self.month_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.month_table.setMaximumHeight(180)
        layout.addWidget(self.month_table)

        self._channel_ids = []
        self._sort = {"column": None, "ascending": True}
        enable_header_click_sort(self.table, self._sort, self.refresh)
        self.refresh()

    def _dates(self):
        return (self.date_from.date().toString("yyyy-MM-dd"),
                self.date_to.date().toString("yyyy-MM-dd"))

    def _this_month(self):
        t = QDate.currentDate()
        self.date_from.setDate(QDate(t.year(), t.month(), 1))
        self.date_to.setDate(t)
        self.refresh()

    def _last_month(self):
        t = QDate.currentDate()
        end = QDate(t.year(), t.month(), 1).addDays(-1)
        self.date_from.setDate(QDate(end.year(), end.month(), 1))
        self.date_to.setDate(end)
        self.refresh()

    def _this_year(self):
        t = QDate.currentDate()
        self.date_from.setDate(QDate(t.year(), 1, 1))
        self.date_to.setDate(t)
        self.refresh()

    def open_rate_dialog(self):
        ShippingFeeRateDialog(self).exec()
        self.refresh()

    def refresh(self):
        df, dt = self._dates()
        rows = db.get_shipping_summary_by_channel(df, dt)
        total = sum(r["shipping_total"] for r in rows)
        charge = sum(r["shipping_charge"] for r in rows)
        net = sum(r["shipping_net"] for r in rows)
        cnt = sum(r["order_count"] for r in rows)

        self.summary.setText(
            f"배송비 발생 주문 {cnt:,}건  |  받은 배송비 {fmt_won(total)}  |  "
            f"수수료 {fmt_won(charge)}  |  ▶ 순배송수익 {fmt_won(net)}"
            + (f"  ({net / total * 100:.1f}%)" if total else ""))

        table_rows = []
        self._channel_ids = []
        for r in rows:
            self._channel_ids.append((r["channel_id"], r["channel_name"]))
            table_rows.append((
                r["channel_name"], r["channel_type"], f"{r['order_count']:,}건",
                fmt_won(r["shipping_total"]), f"{r['rate']:.1f}%",
                fmt_won(r["shipping_charge"]), fmt_won(r["shipping_net"]),
                f"{r['shipping_net'] / r['shipping_total'] * 100:.1f}%" if r["shipping_total"] else "-",
            ))
        headers = ["채널/거래처", "유형", "건수", "받은 배송비", "수수료율",
                   "수수료", "순배송수익", "순수익률"]
        table_rows, self._channel_ids = apply_table_sort(table_rows, self._channel_ids, self._sort)
        fill_table(self.table, headers, table_rows, persist_key="shipping_channel")

        # 합계 행
        if rows:
            last = self.table.rowCount()
            self.table.insertRow(last)
            summary_values = ["■ 합계", "", f"{cnt:,}건", fmt_won(total), "",
                              fmt_won(charge), fmt_won(net),
                              f"{net / total * 100:.1f}%" if total else "-"]
            for c, val in enumerate(summary_values):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setFont(QFont("", -1, QFont.Bold))
                item.setBackground(QColor("#EAF2F8"))
                if looks_numeric(str(val)):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(last, c, item)
            self._channel_ids = list(self._channel_ids) + [None]

        # 월별 추이
        mrows = db.get_shipping_summary_by_period("month", df, dt)
        fill_table(self.month_table,
                   ["월", "건수", "받은 배송비", "수수료", "순배송수익"],
                   [(m["period_key"], f"{m['order_count']:,}건",
                     fmt_won(m["shipping_total"]), fmt_won(m["shipping_charge"]),
                     fmt_won(m["shipping_net"])) for m in mrows],
                   persist_key="shipping_month")

    def on_double_clicked(self, row, column):
        if row < 0 or row >= len(self._channel_ids):
            return
        entry = self._channel_ids[row]
        if not entry:      # 합계 행
            return
        channel_id, channel_name = entry
        df, dt = self._dates()
        ShippingOrderDetailDialog(channel_id, channel_name, df, dt, self).exec()

    def export_excel(self):
        import pandas as pd
        df_date, dt_date = self._dates()
        rows = db.get_shipping_summary_by_channel(df_date, dt_date)
        if not rows:
            QMessageBox.information(self, "알림", "내보낼 배송비 내역이 없습니다.")
            return
        data = [{
            "채널/거래처": r["channel_name"], "유형": r["channel_type"],
            "건수": r["order_count"], "받은 배송비": r["shipping_total"],
            "수수료율(%)": r["rate"], "수수료": r["shipping_charge"],
            "순배송수익": r["shipping_net"],
        } for r in rows]
        filepath = ask_save_file(self, "엑셀로 저장", f"배송비수익_{df_date}_{dt_date}.xlsx",
                                 "Excel 파일 (*.xlsx)", "report")
        if filepath:
            pd.DataFrame(data).to_excel(filepath, index=False)
            QMessageBox.information(self, "완료", "엑셀 파일로 저장되었습니다.")


class ReportTab(QWidget):
    NAV_GROUPS = [
        ("📊  매출분석", ["period_profit_tab", "channel_sales_tab", "product_ranking_tab", "customer_ranking_tab", "trend_tab"]),
        ("💰  자금현황", ["settlement_status_tab", "bank_status_tab", "cash_status_tab",
                          "expense_overview_tab", "monthly_settlement_tab", "shipping_revenue_tab"]),
        ("📦  재고", ["stock_status_tab"]),
        ("↩️  반품/반출", ["return_status_tab"]),
    ]
    NAV_LABELS = {
        "period_profit_tab": "기간별 이익",
        "product_ranking_tab": "상품별 순위",
        "customer_ranking_tab": "고객별 순위",
        "trend_tab": "월별 추이",
        "settlement_status_tab": "미수/미결재 현황",
        "expense_overview_tab": "지출 현황",
        "bank_status_tab": "통장 현황",
        "cash_status_tab": "현금 현황",
        "expense_status_tab": "지출 현황",
        "monthly_settlement_tab": "월별결산",
        "channel_sales_tab": "채널/거래처별 매출",
        "stock_status_tab": "재고 현황",
        "return_status_tab": "반품/반출 내역",
        "shipping_revenue_tab": "배송비 수익",
    }

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.period_profit_tab = PeriodProfitTab()
        self.product_ranking_tab = ProductRankingTab()
        self.customer_ranking_tab = CustomerRankingTab()
        self.trend_tab = TrendTab()
        self.settlement_status_tab = SettlementStatusTab()
        self.channel_sales_tab = ChannelSalesTab()
        self.stock_status_tab = StockStatusTab()
        self.return_status_tab = ReturnStatusTab()
        self.monthly_settlement_tab = MonthlySettlementTab()
        self.expense_overview_tab = ExpenseOverviewTab()
        self.bank_status_tab = BankStatusTab()
        self.cash_status_tab = CashStatusTab()
        self.expense_status_tab = ExpenseStatusTab()
        self.shipping_revenue_tab = ShippingRevenueTab()

        self.stack = QStackedWidget()
        self.nav_list = QListWidget()
        # 스페이스바/방향키로 메뉴가 움직이지 않게 함 (즉시 잠금 단축키와 겹침 방지)
        self.nav_list.setFocusPolicy(Qt.NoFocus)
        self.nav_list.setFixedWidth(170)
        self.nav_list.setStyleSheet("""
            QListWidget { background-color: #F4F6F7; border: none; outline: none; padding-top: 6px; }
            QListWidget::item { padding: 8px 16px; color: #333; }
            QListWidget::item:selected { background-color: #D6EAF8; color: #1A5276; font-weight: bold; }
            QListWidget::item:hover:!selected { background-color: #EAECEE; }
        """)

        self._row_to_page = {}
        row = 0
        for header_text, attr_names in self.NAV_GROUPS:
            header_item = QListWidgetItem(header_text)
            header_item.setFlags(Qt.NoItemFlags)
            f = header_item.font()
            f.setBold(True)
            header_item.setFont(f)
            header_item.setForeground(QColor("#909497"))
            self.nav_list.addItem(header_item)
            row += 1
            for attr in attr_names:
                widget = getattr(self, attr)
                item = QListWidgetItem("   " + self.NAV_LABELS[attr])
                self.nav_list.addItem(item)
                page_index = self.stack.addWidget(widget)
                self._row_to_page[row] = page_index
                row += 1

        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav_list)

        content_wrap = QWidget()
        content_col = QVBoxLayout(content_wrap)
        content_col.setContentsMargins(15, 15, 15, 15)
        title = QLabel("📈 리포트")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        content_col.addWidget(title)
        content_col.addWidget(self.stack)
        layout.addWidget(content_wrap, stretch=1)

        self.nav_list.setCurrentRow(1)  # 기본: 첫 항목(기간별 이익)

    def _on_nav_changed(self, row):
        if row not in self._row_to_page:
            return
        page_index = self._row_to_page[row]
        self.stack.setCurrentIndex(page_index)
        widget = self.stack.widget(page_index)
        if hasattr(widget, "refresh"):
            widget.refresh()
        self._highlight_selected(row)
        _qsettings.setValue("window/last_report_nav_row", row)

    def _highlight_selected(self, selected_row):
        """선택된 세부메뉴만 굵게 + 색으로 표시 (그룹 제목은 원래 굵으므로
        구분이 되도록 선택 항목은 색까지 함께 바꿔줌)"""
        for i in range(self.nav_list.count()):
            item = self.nav_list.item(i)
            if item is None or i not in self._row_to_page:
                continue   # 그룹 제목은 건드리지 않음
            font = item.font()
            is_sel = (i == selected_row)
            font.setBold(is_sel)
            item.setFont(font)
            item.setForeground(QColor("#1A5276") if is_sel else QColor("#000000"))

    def refresh(self):
        current = self.stack.currentWidget()
        if hasattr(current, "refresh"):
            current.refresh()


# ---------------------------------------------------------------------------
# 설정 탭
# ---------------------------------------------------------------------------


class BackupSelectionDialog(QDialog):
    """백업할 데이터를 메뉴별로 선택. 품목/거래처(채널)/리포트 관련 설정값(지출항목,
    옵션프리셋, 통장 목록)은 항상 포함되고 물어보지 않음."""

    # 체크를 풀면 그 데이터는 백업에서 빠집니다 (기본은 전부 포함)
    OPTIONAL_ITEMS = [
        ("📦 품목 (상품/옵션/재고)", ["products"]),
        ("🏢 판매채널 · 거래처", ["channels"]),
        ("🧩 조합(세트) 구성", ["product_bundles"]),
        ("🏦 통장 · 💳 카드", ["bank_accounts", "cards"]),
        ("⚙️ 설정값 (지출항목·옵션·수량프리셋·채널수수료율)",
         ["expense_categories", "option_presets", "qty_presets", "channel_fee_rates"]),
        ("🛒 주문 내역 (주문관리)", ["orders"]),
        ("📥 입고/매입 내역 (입고관리 + 매입지출)", ["purchases", "purchase_payments"]),
        ("💸 지출 내역 (정산/지출관리)", ["expenses"]),
        ("💰 정산 입금 내역", ["settlements"]),
        ("💵 현금 조정 이력", ["cash_adjustments"]),
        ("📄 업로드 파일 이력", ["upload_history"]),
        ("🔧 재고 조정 이력", ["stock_adjustments"]),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("백업 항목 선택")
        self.resize(480, 520)

        layout = QVBoxLayout(self)
        note = QLabel("💡 백업에 포함할 항목을 골라주세요. 기본은 전부 포함이고, 체크를 풀면 그 데이터만 빠집니다.\n"
                      "   (테스트 데이터만 지우고 품목·거래처는 남기고 싶을 때 활용하세요)")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        self.checkboxes = []
        for label, tables in self.OPTIONAL_ITEMS:
            cb = QCheckBox(label)
            cb.setChecked(True)
            layout.addWidget(cb)
            self.checkboxes.append((cb, tables))

        sel_row = QHBoxLayout()
        all_btn = QPushButton("전체 선택")
        all_btn.clicked.connect(lambda: [cb.setChecked(True) for cb, _ in self.checkboxes])
        sel_row.addWidget(all_btn)
        none_btn = QPushButton("전체 해제")
        none_btn.clicked.connect(lambda: [cb.setChecked(False) for cb, _ in self.checkboxes])
        sel_row.addWidget(none_btn)
        base_btn = QPushButton("기준정보만 (품목·거래처·설정)")
        base_btn.setToolTip("품목/채널·거래처/조합/통장·카드/설정값만 백업하고 거래 데이터는 제외합니다")
        base_btn.clicked.connect(self._select_master_only)
        sel_row.addWidget(base_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("✅ 이 항목들로 백업")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _select_master_only(self):
        master = {"products", "channels", "product_bundles", "bank_accounts", "cards",
                   "expense_categories", "option_presets", "qty_presets", "channel_fee_rates"}
        for cb, tables in self.checkboxes:
            cb.setChecked(bool(set(tables) & master))

    def get_excluded_tables(self):
        excluded = []
        for cb, tables in self.checkboxes:
            if not cb.isChecked():
                excluded.extend(tables)
        return excluded


class UnlockDialog(QDialog):
    """자동 잠금이 걸렸을 때 잠금을 푸는 창.
    잠금 방식이 'PIN 번호'면 번호를 입력하고, '클릭 횟수'면 버튼을 정해진 횟수만큼 누름"""

    def __init__(self, mode, secret, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.secret = str(secret)
        self._clicks = 0
        self.setWindowTitle("🔒 잠금 해제")
        self.setModal(True)
        # 창을 닫아서 잠금을 우회하지 못하도록 닫기 버튼은 숨기되,
        # 급할 때 화면을 치울 수 있게 최소화는 허용
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint
                            | Qt.WindowMinimizeButtonHint)
        self.resize(380, 240)
        self.setStyleSheet("QDialog { background-color: #1C2833; }")

        layout = QVBoxLayout(self)
        min_row = QHBoxLayout()
        min_row.addStretch()
        min_btn = QPushButton("🗕 최소화")
        min_btn.setToolTip("잠금은 그대로 두고 창만 작업표시줄로 내립니다")
        min_btn.setFixedWidth(90)
        min_btn.setStyleSheet(
            "QPushButton { background:#34495E; color:white; border:none;"
            " padding:4px 8px; border-radius:4px; }"
            "QPushButton:hover { background:#4A6572; }")
        min_btn.clicked.connect(self._minimize_all)
        min_row.addWidget(min_btn)
        layout.addLayout(min_row)

        title = QLabel("🔒 화면이 잠겼습니다")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        if mode == "pin":
            self.info = QLabel("잠금 해제 번호를 입력하세요.")
            self.info.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.info)
            self.pin_input = QLineEdit()
            self.pin_input.setEchoMode(QLineEdit.Password)
            self.pin_input.setAlignment(Qt.AlignCenter)
            self.pin_input.setMaxLength(12)
            self.pin_input.returnPressed.connect(self._check_pin)
            # 창이 뜨자마자 바로 번호를 칠 수 있게 입력칸에 커서를 놓음
            # (예전엔 칸을 눌러야만 입력이 먹혀서 반응이 없는 것처럼 보였음)
            self.pin_input.setFocus()
            self.setFocusProxy(self.pin_input)
            layout.addWidget(self.pin_input)
            ok_btn = QPushButton("잠금 해제")
            ok_btn.clicked.connect(self._check_pin)
            layout.addWidget(ok_btn)
        else:
            self.info = QLabel(f"아래 버튼을 {self.secret}번 누르면 잠금이 풀립니다.")
            self.info.setAlignment(Qt.AlignCenter)
            self.info.setWordWrap(True)
            layout.addWidget(self.info)
            self.count_label = QLabel("0회")
            self.count_label.setAlignment(Qt.AlignCenter)
            self.count_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #2980B9;")
            layout.addWidget(self.count_label)
            click_btn = QPushButton("🔓 여기를 누르세요")
            click_btn.setMinimumHeight(48)
            click_btn.clicked.connect(self._count_click)
            layout.addWidget(click_btn)

        self.msg = QLabel("")
        self.msg.setAlignment(Qt.AlignCenter)
        self.msg.setStyleSheet("color: #C0392B;")
        layout.addWidget(self.msg)

    def showEvent(self, event):
        """창이 보일 때마다 비밀번호 칸에 커서를 다시 놓아줌
        (최소화했다가 되돌아왔을 때도 바로 입력되도록)"""
        super().showEvent(event)
        if hasattr(self, "pin_input"):
            self.pin_input.setFocus()
            self.pin_input.activateWindow()

    def _minimize_all(self):
        """잠금 상태를 유지한 채 프로그램 창을 작업표시줄로 내림"""
        try:
            if self.parent() is not None:
                self.parent().showMinimized()
        except Exception:
            pass
        self.showMinimized()

    def _check_pin(self):
        if self.pin_input.text() == self.secret:
            self.accept()
        else:
            self.msg.setText("번호가 맞지 않습니다.")
            self.pin_input.clear()

    def _count_click(self):
        self._clicks += 1
        try:
            need = int(self.secret or 1)
        except (TypeError, ValueError):
            need = 1
        self.count_label.setText(f"{self._clicks} / {need}회")
        if self._clicks >= need:
            self.accept()

    def mousePressEvent(self, event):
        """클릭 해제 방식일 때는 잠금 화면 아무 곳이나 눌러도 카운트됨
        (작은 버튼을 정확히 눌러야 하는 불편을 없앰)"""
        if self.mode != "pin":
            self._count_click()
        super().mousePressEvent(event)

    def reset_clicks(self):
        self._clicks = 0


class SettleBankDialog(QDialog):
    """채널별 정산 입금통장 지정"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("채널별 정산 입금통장")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        title = QLabel("🏦 채널별 정산 입금통장")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        note = QLabel("💡 채널마다 정산금이 들어오는 통장을 지정해두면, 정산 입금 등록에서 "
                       "그 채널을 고를 때 통장이 자동으로 선택됩니다. (정산금은 통장으로만 들어옵니다)")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        row = QHBoxLayout()
        self.channel_combo = QComboBox()
        self.channel_combo.setFixedWidth(180)
        self.channel_combo.currentIndexChanged.connect(self._load_current)
        row.addWidget(tight_pair("채널:", self.channel_combo))
        self.bank_combo = QComboBox()
        self.bank_combo.setFixedWidth(200)
        row.addWidget(tight_pair("정산 통장:", self.bank_combo))
        save_btn = QPushButton("💾 지정")
        save_btn.clicked.connect(self.save)
        row.addWidget(save_btn)
        row.addStretch()
        layout.addLayout(row)

        self.table = QTableWidget()
        layout.addWidget(self.table)
        fix_btn = QPushButton("🔄 기존 정산 내역에 통장 소급 적용")
        fix_btn.setToolTip("지금까지 bank_account_id 없이 저장된 정산 건에 지정한 통장을 한 번에 반영합니다")
        fix_btn.clicked.connect(self.fix_history)
        layout.addWidget(fix_btn)
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.refresh()

    def refresh(self):
        cur_ch = self.channel_combo.currentData()
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        for ch in db.get_channels():
            if (ch["channel_type"] or "온라인채널") == "온라인채널":
                self.channel_combo.addItem(ch["name"], ch["id"])
        if cur_ch:
            i = self.channel_combo.findData(cur_ch)
            if i >= 0:
                self.channel_combo.setCurrentIndex(i)
        self.channel_combo.blockSignals(False)

        self.bank_combo.clear()
        self.bank_combo.addItem("(지정 안 함)", None)
        for a in db.get_bank_accounts():
            self.bank_combo.addItem(a["bank_name"] or a["name"], a["id"])
        self._load_current()

        banks = {a["id"]: (a["bank_name"] or a["name"]) for a in db.get_bank_accounts()}
        rows = []
        for ch in db.get_channels():
            if (ch["channel_type"] or "온라인채널") != "온라인채널":
                continue
            try:
                bid = ch["settle_bank_id"]
            except (IndexError, KeyError):
                bid = None
            rows.append((ch["name"], banks.get(bid, "— 미지정 —")))
        fill_table(self.table, ["채널", "정산 입금통장"], rows, persist_key="channel_settle_bank")

    def _load_current(self):
        cid = self.channel_combo.currentData()
        bid = db.get_channel_settle_bank(cid) if cid else None
        idx = self.bank_combo.findData(bid) if bid else 0
        self.bank_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def fix_history(self):
        n = db.fix_settlement_bank_accounts()
        notify_data_changed()
        self.refresh()
        QMessageBox.information(
            self, "완료",
            f"기존 정산 내역 {n}건에 통장을 반영했습니다.\n\n"
            "통장현황에서 정산 입금이 보이지 않던 내역이 이제 표시됩니다.")

    def save(self):
        cid = self.channel_combo.currentData()
        if cid is None:
            QMessageBox.warning(self, "알림", "채널을 선택해주세요.")
            return
        db.set_channel_settle_bank(cid, self.bank_combo.currentData())
        notify_data_changed()
        self.refresh()
        QMessageBox.information(self, "완료", "정산 입금통장을 지정했습니다.")


class CompanyInfoDialog(QDialog):
    """사용자(공급자) 정보 - 거래명세표에 들어가는 우리 회사 정보"""

    FIELDS = [("name", "상호(법인명)"), ("ceo", "성명"), ("biznum", "사업자등록번호"),
               ("address", "사업장 주소"), ("business_type", "업태"),
               ("business_item", "종목"), ("bank_info", "계좌 안내")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("사용자 정보 설정")
        self.resize(520, 380)

        layout = QVBoxLayout(self)
        title = QLabel("🏢 사용자 정보")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        note = QLabel("💡 여기 입력한 내용이 거래명세표의 '공급자' 칸에 자동으로 들어갑니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        info = db.get_my_company_info()
        self.inputs = {}
        for key, label in self.FIELDS:
            edit = QLineEdit(info.get(key, "") or "")
            edit.setMinimumHeight(28)
            if key == "biznum":
                edit.setPlaceholderText("189 - 81 - 00485")
            elif key == "bank_info":
                edit.setPlaceholderText("국민 282401-04-300004  예금주: ㈜에누리하우스")
            form.addRow(label + " :", edit)
            self.inputs[key] = edit
        layout.addLayout(form)
        layout.addStretch()

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        db.save_my_company_info({k: e.text().strip() for k, e in self.inputs.items()})
        QMessageBox.information(self, "완료", "사용자 정보를 저장했습니다.")
        self.accept()


class SaveToast(QLabel):
    """저장 완료를 잠깐 보여주고 1초 후 사라지는 알림 창
    (편의기능에서 켜고 끌 수 있음)"""

    def __init__(self, parent):
        super().__init__("✅ 저장되었습니다", parent)
        self.setStyleSheet(
            "background: #1E8449; color: white; border-radius: 8px;"
            "padding: 8px 20px; font-size: 14px; font-weight: bold;")
        self.setAlignment(Qt.AlignCenter)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_at(self, parent_widget):
        if not conv_on("save_toast"):
            return
        self.setParent(parent_widget)
        pw = parent_widget.width()
        self.adjustSize()
        self.move((pw - self.width()) // 2, 12)
        self.show()
        self.raise_()
        self._timer.start(1200)


def show_save_toast(parent_widget):
    """부모 위젯 위에 "저장 완료" 메시지를 잠깐 표시 (편의기능 켜져있을 때만)"""
    if not conv_on("save_toast"):
        return
    toast = SaveToast(parent_widget)
    toast.show_at(parent_widget)


class ConvenienceSettingsDialog(QDialog):
    """편의 기능 켜고 끄기 (설정 화면이 복잡해지지 않도록 별도 창으로 분리)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("편의 기능 설정")
        self.resize(520, 400)

        layout = QVBoxLayout(self)
        title = QLabel("✨ 편의 기능")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        note = QLabel("💡 필요한 것만 켜서 쓰세요. 저장하면 즉시 반영되고 다음에 켤 때도 유지됩니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        self.checkboxes = {}
        for key, label, default in CONVENIENCE_OPTIONS:
            cb = QCheckBox(label)
            cb.setChecked(conv_on(key, default))
            cb.setStyleSheet("padding: 4px;")
            layout.addWidget(cb)
            self.checkboxes[key] = cb

        layout.addStretch()
        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        for key, cb in self.checkboxes.items():
            _qsettings.setValue(f"conv/{key}", "true" if cb.isChecked() else "false")
        notify_data_changed()
        self.accept()


class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)

        title_row = QHBoxLayout()
        title = QLabel("⚙️ 설정")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title_row.addWidget(title)
        title_row.addStretch()
        settle_bank_btn = QPushButton("🏦 정산 입금통장 설정")
        settle_bank_btn.setToolTip("채널별로 정산금이 들어오는 통장을 지정합니다")
        settle_bank_btn.clicked.connect(lambda: SettleBankDialog(self).exec())
        title_row.addWidget(settle_bank_btn)
        company_btn = QPushButton("🏢 사용자 정보 설정")
        company_btn.setToolTip("거래명세표에 들어가는 우리 회사 정보를 입력합니다")
        company_btn.clicked.connect(self.open_company_settings)
        title_row.addWidget(company_btn)
        conv_btn = QPushButton("✨ 편의 기능")
        conv_btn.setToolTip("자주 쓰는 편의 기능을 켜고 끕니다")
        conv_btn.clicked.connect(self.open_convenience_settings)
        title_row.addWidget(conv_btn)
        outer.addLayout(title_row)


        # ---------- 판매채널 관리 ----------
        sales_box = QGroupBox("🛒 판매채널 관리 (스마트스토어, 11번가, 쿠팡 등)")
        sales_layout = QVBoxLayout(sales_box)

        sales_btn_row = QHBoxLayout()
        add_sales_btn = QPushButton("➕ 채널 추가")
        add_sales_btn.clicked.connect(lambda: self.add_channel_of_type("online"))
        sales_btn_row.addWidget(add_sales_btn)
        rename_sales_btn = QPushButton("✏️ 이름변경")
        rename_sales_btn.clicked.connect(lambda: self.rename_selected(self.sales_channel_table, self._sales_ids))
        sales_btn_row.addWidget(rename_sales_btn)
        delete_sales_btn = QPushButton("🗑️ 삭제")
        delete_sales_btn.setStyleSheet("color: red;")
        delete_sales_btn.clicked.connect(lambda: self.delete_selected(self.sales_channel_table, self._sales_ids, False))
        sales_btn_row.addWidget(delete_sales_btn)
        sales_btn_row.addStretch()
        sales_layout.addLayout(sales_btn_row)

        self.sales_channel_table = QTableWidget()
        self.sales_channel_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._sales_sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.sales_channel_table, self._sales_sort_state, self.refresh)
        sales_layout.addWidget(self.sales_channel_table)
        outer.addWidget(sales_box)

        # ---------- 거래처(매입처) 관리 ----------
        supplier_box = QGroupBox("🏢 거래처 관리")
        supplier_layout = QVBoxLayout(supplier_box)

        supplier_btn_row = QHBoxLayout()
        manage_supplier_btn = QPushButton("📋 거래처 관리 (추가·수정·삭제)")
        manage_supplier_btn.setToolTip("거래처를 등록하고 사업자등록번호·주소·연락처를 관리합니다")
        manage_supplier_btn.clicked.connect(self.open_supplier_management)
        supplier_btn_row.addWidget(manage_supplier_btn)
        supplier_btn_row.addStretch()
        supplier_layout.addLayout(supplier_btn_row)
        outer.addWidget(supplier_box)

        # ---------- 채널별 수수료율 적용 ----------
        fee_box = QGroupBox("💳 채널별 수수료율 적용 (마켓파일에 수수료가 안 나올 때 사용)")
        fee_layout = QVBoxLayout(fee_box)
        fee_note = QLabel("💡 채널 + 상품을 고르고 수수료율(%)을 등록해두면, 주문관리의 "
                           "'🔄 미기재 수수료 자동계산' 버튼으로 수수료가 비어있는 주문에 일괄 적용할 수 있어요.")
        fee_note.setWordWrap(True)
        fee_note.setStyleSheet("color: #666;")
        fee_layout.addWidget(fee_note)

        fee_form_row = QHBoxLayout()
        self.fee_channel_combo = QComboBox()
        self.fee_channel_combo.setFixedWidth(160)
        fee_form_row.addWidget(tight_pair("채널:", self.fee_channel_combo))
        self.fee_product_combo = QComboBox()
        self.fee_product_combo.setFixedWidth(220)
        fee_form_row.addWidget(tight_pair("상품:", self.fee_product_combo))
        self.fee_rate_value_input = QLineEdit()
        self.fee_rate_value_input.setFixedWidth(80)
        self.fee_rate_value_input.setPlaceholderText("예: 7.8")
        fee_form_row.addWidget(tight_pair("수수료율(%):", self.fee_rate_value_input))
        fee_save_btn = QPushButton("➕ 등록")
        fee_save_btn.clicked.connect(self.save_channel_fee_rate)
        fee_form_row.addWidget(fee_save_btn)
        fee_form_row.addStretch()
        fee_layout.addLayout(fee_form_row)

        fee_action_row = QHBoxLayout()
        fee_delete_btn = QPushButton("🗑️ 선택 삭제")
        fee_delete_btn.setStyleSheet("color: red;")
        fee_delete_btn.clicked.connect(self.delete_channel_fee_rate)
        fee_action_row.addWidget(fee_delete_btn)
        fee_action_row.addStretch()
        fee_layout.addLayout(fee_action_row)

        self.fee_rate_table = QTableWidget()
        self.fee_rate_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._fee_rate_sort_state = {"column": None, "ascending": True}
        enable_header_click_sort(self.fee_rate_table, self._fee_rate_sort_state, self.refresh)
        fee_layout.addWidget(self.fee_rate_table)
        outer.addWidget(fee_box)



        # ---------- 보안 (자동 잠금) ----------
        lock_box = QGroupBox("🔒 보안 - 자동 잠금 (장부를 다른 사람이 보지 못하게)")
        lock_outer = QVBoxLayout(lock_box)
        lock_note = QLabel("💡 정해둔 시간 동안 마우스·키보드 조작이 없으면 화면이 잠깁니다. "
                            "해제는 PIN 번호 또는 정해진 횟수만큼 클릭하는 방식 중에 고를 수 있어요.\n"
                            "⚡ '즉시 잠금'을 정해두면 손님이 갑자기 왔을 때 바로 화면을 가릴 수 있어요. "
                            "(글자 입력 중에는 눌러도 잠기지 않으니 안심하세요)")
        lock_note.setWordWrap(True)
        lock_note.setStyleSheet("color: #666;")
        lock_outer.addWidget(lock_note)

        lock_row = QHBoxLayout()
        self.lock_minutes_combo = QComboBox()
        self.lock_minutes_combo.addItem("사용 안 함", 0)
        for label, mins in [("1분", 1), ("3분", 3), ("5분", 5), ("10분", 10),
                             ("30분", 30), ("1시간", 60)]:
            self.lock_minutes_combo.addItem(label, mins)
        lock_row.addWidget(tight_pair("잠금까지:", self.lock_minutes_combo))

        self.lock_mode_combo = QComboBox()
        self.lock_mode_combo.addItem("PIN 번호", "pin")
        self.lock_mode_combo.addItem("클릭 횟수", "click")
        self.lock_mode_combo.currentIndexChanged.connect(self._update_lock_secret_hint)
        lock_row.addWidget(tight_pair("해제 방법:", self.lock_mode_combo))

        self.lock_secret_input = QLineEdit()
        self.lock_secret_input.setFixedWidth(120)
        lock_row.addWidget(tight_pair("PIN/횟수:", self.lock_secret_input))

        # 급하게 화면을 가려야 할 때 쓰는 즉시 잠금 단축키
        self.quick_lock_combo = QComboBox()
        self.quick_lock_combo.addItem("사용 안 함", "off")
        self.quick_lock_combo.addItem("스페이스바 빠르게 2번", "space2")
        self.quick_lock_combo.addItem("스페이스바 빠르게 3번", "space3")
        self.quick_lock_combo.addItem("ESC 빠르게 2번", "esc2")
        self.quick_lock_combo.addItem("Ctrl + L", "ctrl_l")
        self.quick_lock_combo.setFixedWidth(180)
        lock_row.addWidget(tight_pair("즉시 잠금:", self.quick_lock_combo))

        save_lock_btn = QPushButton("💾 잠금 설정 저장")
        save_lock_btn.clicked.connect(self.save_lock_settings)
        lock_row.addWidget(save_lock_btn)
        lock_now_btn = QPushButton("🔒 지금 잠그기")
        lock_now_btn.clicked.connect(self.lock_now)
        lock_row.addWidget(lock_now_btn)
        lock_row.addStretch()
        lock_outer.addLayout(lock_row)
        self.lock_hint = QLabel("")
        self.lock_hint.setWordWrap(True)
        self.lock_hint.setStyleSheet("color: #7F8C8D;")
        lock_outer.addWidget(self.lock_hint)
        # 잠금 + 백업 좌우 배치
        lock_backup_row = QHBoxLayout()
        lock_backup_row.addWidget(lock_box, stretch=3)

        data_box = QGroupBox("💾 데이터 백업 / 복원")
        data_layout = QVBoxLayout(data_box)
        backup_btn = QPushButton("💾 데이터 백업하기 (파일로 저장)")
        backup_btn.clicked.connect(self.backup_data)
        data_layout.addWidget(backup_btn)
        restore_btn = QPushButton("📂 백업 파일에서 복원하기")
        restore_btn.clicked.connect(self.restore_data)
        data_layout.addWidget(restore_btn)

        # ── 프로그램 업데이트 ───────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#D5D8DC;")
        data_layout.addWidget(line)

        ver_row = QHBoxLayout()
        ver_label = QLabel(f"현재 버전  <b>{BUILD_VERSION}</b>")
        ver_label.setStyleSheet("color:#555;")
        ver_row.addWidget(ver_label)
        ver_row.addStretch()
        data_layout.addLayout(ver_row)

        src_row = QHBoxLayout()
        self.update_src_input = QLineEdit(
            str(_qsettings.value("update/location", "") or ""))
        self.update_src_input.setPlaceholderText(
            "업데이트 위치 (인터넷 주소 또는 폴더 경로)")
        src_row.addWidget(self.update_src_input)
        pick_btn = QPushButton("📁")
        pick_btn.setFixedWidth(36)
        pick_btn.setToolTip("업데이트 파일이 들어있는 폴더 고르기")
        pick_btn.clicked.connect(self._pick_update_folder)
        src_row.addWidget(pick_btn)
        data_layout.addLayout(src_row)

        upd_btn = QPushButton("⬆️ 업데이트 확인 및 설치")
        upd_btn.setStyleSheet(
            "QPushButton { background:#2E86C1; color:white; font-weight:bold;"
            " padding:6px; border:none; border-radius:5px; }"
            "QPushButton:hover { background:#2874A6; }")
        upd_btn.clicked.connect(self.run_update)
        data_layout.addWidget(upd_btn)

        upd_note = QLabel(
            "💡 업데이트 위치에 <b>version.json</b>과 압축파일을 놓아두면 "
            "여기서 바로 받아 설치합니다.<br>"
            "설치 전에 프로그램 폴더를 통째로 백업하고, "
            "<b>장부 데이터(ledger.db)는 건드리지 않습니다.</b>")
        upd_note.setWordWrap(True)
        upd_note.setStyleSheet("color:#888; font-size:11px;")
        data_layout.addWidget(upd_note)
        data_layout.addStretch()
        lock_backup_row.addWidget(data_box, stretch=2)
        outer.addLayout(lock_backup_row)

        self._load_lock_settings()

        note = QLabel("💡 모든 장부 데이터는 프로그램 폴더의 ledger.db 파일 하나에 저장돼요. "
                      "백업 버튼으로 다른 곳에 복사해두면 컴퓨터를 바꾸거나 문제가 생겨도 안전하게 복구할 수 있어요.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        outer.addWidget(note)

        # ---------- 위험 구역 ----------
        danger_box = QGroupBox("⚠️ 위험 구역")
        danger_layout = QHBoxLayout(danger_box)
        reset_btn = QPushButton("🗑️ 전체 데이터 초기화 (채널 목록은 유지)")
        reset_btn.setStyleSheet("color: red; font-weight: bold;")
        reset_btn.clicked.connect(self.reset_all_data)
        danger_layout.addWidget(reset_btn)
        danger_layout.addStretch()
        outer.addWidget(danger_box)

        # ---------- API 연동 (준비중) ----------
        api_box = QGroupBox("🔌 마켓 API 자동연동 (준비중)")
        api_layout = QVBoxLayout(api_box)
        api_note = QLabel(
            "각 마켓(스마트스토어/11번가/쿠팡/ESM)에서 주문·정산·재고를 자동으로 "
            "가져오는 기능은 아직 준비 중이에요. 이를 위한 기본 틀(api_connectors.py)은 "
            "미리 만들어뒀지만, 실제로 쓰려면 각 마켓 셀러센터에서 오픈API를 신청해서 "
            "발급받은 인증키가 필요합니다 (사업자 등록 필요, 마켓마다 신청 절차가 달라요)."
        )
        api_note.setWordWrap(True)
        api_note.setStyleSheet("color: #666;")
        api_layout.addWidget(api_note)
        outer.addWidget(api_box)

        # ---------- 앱 정보 ----------
        info_box = QGroupBox("ℹ️ 프로그램 정보")
        info_layout = QVBoxLayout(info_box)
        info_layout.addWidget(QLabel("온라인 판매 장부 (스마트스토어 / 11번가 / 쿠팡 / ESM 전용)"))
        db_row = QHBoxLayout()
        self.db_path_label = QLabel(f"데이터 파일 위치: {db.get_db_path()}")
        self.db_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.db_path_label.setWordWrap(True)
        db_row.addWidget(self.db_path_label, stretch=1)
        change_db_btn = QPushButton("📁 위치 변경")
        change_db_btn.setToolTip("데이터 파일(ledger.db)을 다른 폴더로 옮기고, 앞으로 그 위치를 사용합니다")
        change_db_btn.clicked.connect(self.change_db_location)
        db_row.addWidget(change_db_btn)
        reset_db_btn = QPushButton("↩️ 기본 위치로")
        reset_db_btn.clicked.connect(self.reset_db_location)
        db_row.addWidget(reset_db_btn)
        info_layout.addLayout(db_row)
        outer.addWidget(info_box)

        outer.addStretch()
        self.refresh()

    # ---------- 채널 관리 (판매채널 / 거래처 공용) ----------
    def refresh(self):
        channels = db.get_channels()
        sales = [c for c in channels if (c["channel_type"] or "온라인채널") == "온라인채널"]

        sales_ids = [c["id"] for c in sales]
        self._sales_ids = fill_table(
            self.sales_channel_table, ["ID", "채널명", "이번주", "이번달", "올해", "전체"],
            [(c["id"], c["name"]) + tuple(
                f"{n:,}건" for n in db.get_channel_order_counts_by_period(c["id"]))
             + (f"{db.get_channel_order_count(c['id']):,}건",) for c in sales],
            persist_key="settings_sales_channels", sort_state=self._sales_sort_state, id_list=sales_ids
        )

        try:
            self._update_lock_status()
        except Exception:
            pass
        self.reload_fee_channel_combo()
        self.reload_fee_product_combo()

        rates = db.get_channel_fee_rates()
        rate_ids = [r["id"] for r in rates]
        rows = [
            (r["channel_name"], r["product_name"], f"{r['fee_rate']:.1f}%")
            for r in rates
        ]
        self._fee_rate_ids = fill_table(
            self.fee_rate_table, ["채널", "상품", "수수료율"], rows,
            persist_key="settings_channel_fee_rates", sort_state=self._fee_rate_sort_state, id_list=rate_ids
        )
        fit_table_height(self.sales_channel_table, max_rows=8)
        fit_table_height(self.fee_rate_table, max_rows=8)

    def reload_fee_channel_combo(self):
        """수수료는 온라인 마켓에서만 발생하므로 판매채널만 표시 (일반거래처 제외)"""
        current = self.fee_channel_combo.currentData()
        self.fee_channel_combo.clear()
        for ch in db.get_channels():
            if (ch["channel_type"] or "온라인채널") == "온라인채널":
                self.fee_channel_combo.addItem(ch["name"], ch["id"])
        if current:
            idx = self.fee_channel_combo.findData(current)
            if idx >= 0:
                self.fee_channel_combo.setCurrentIndex(idx)

    def reload_fee_product_combo(self):
        """수수료율은 옵션(소분류)마다 다르지 않고 상품 대분류 단위로 같은 경우가
        많아서, 여기서는 상품명(대분류)만 중복 없이 보여줌"""
        current = self.fee_product_combo.currentData()
        self.fee_product_combo.clear()
        seen = []
        for p in db.get_products():
            if p["name"] and p["name"] not in seen:
                seen.append(p["name"])
        for name in seen:
            self.fee_product_combo.addItem(name, name)
        if current:
            idx = self.fee_product_combo.findData(current)
            if idx >= 0:
                self.fee_product_combo.setCurrentIndex(idx)



    def open_company_settings(self):
        CompanyInfoDialog(self).exec()


    def save_channel_fee_rate(self):
        channel_id = self.fee_channel_combo.currentData()
        product_name = self.fee_product_combo.currentData()
        if channel_id is None or not product_name:
            QMessageBox.warning(self, "알림", "채널과 상품을 선택해주세요.")
            return
        try:
            fee_rate = float(self.fee_rate_value_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "알림", "수수료율을 숫자로 입력해주세요. (예: 7.8)")
            return
        db.set_channel_fee_rate(channel_id, product_name, fee_rate)
        # 등록 즉시 기존 주문에도 적용 (설정만 하고 주문관리 버튼을 따로 누르지 않으면
        # 리포트에 반영이 안 되던 문제 해결)
        applied = db.apply_default_fee_rates()
        self.fee_rate_value_input.clear()
        notify_data_changed()
        self.refresh()
        if applied:
            QMessageBox.information(
                self, "완료",
                f"수수료율이 등록되었고, 수수료가 비어있던 주문 {applied}건에 바로 적용됐어요."
            )

    def delete_channel_fee_rate(self):
        row = self.fee_rate_table.currentRow()
        if row < 0 or row >= len(self._fee_rate_ids):
            QMessageBox.warning(self, "알림", "삭제할 항목을 선택해주세요.")
            return
        label = ""
        it = self.fee_rate_table.item(row, 0)
        if it:
            label = it.text()
        if not confirm_delete(
                self, f"수수료율 설정 {('- ' + label) if label else ''}".strip(),
                "이미 계산돼 저장된 주문의 수수료 금액은 그대로 남고, "
                "앞으로 들어오는 주문에만 영향을 줍니다."):
            return
        db.delete_channel_fee_rate(self._fee_rate_ids[row])
        notify_data_changed()
        self.refresh()

    def _selected_row(self, table, ids):
        row = table.currentRow()
        if row < 0 or row >= len(ids):
            return None, None
        cid = ids[row]
        name = table.item(row, 1).text()
        return cid, name

    def add_channel_of_type(self, kind):
        """kind: 'online'(판매채널) 또는 'offline'(거래처) - 해당 유형의 등록 화면으로 바로 이동"""
        dialog = NewChannelDialog(self)
        dialog.stack.setCurrentIndex(1 if kind == "online" else 2)
        if dialog.exec() == QDialog.Accepted and dialog.result_channel_id:
            self.refresh()

    def rename_selected(self, table, ids):
        cid, name = self._selected_row(table, ids)
        if cid is None:
            QMessageBox.warning(self, "알림", "이름을 바꿀 항목을 표에서 선택해주세요.")
            return
        new_name, ok = QInputDialog.getText(self, "이름변경", "새 이름을 입력하세요:", text=name)
        new_name = new_name.strip()
        if ok and new_name:
            try:
                db.rename_channel(cid, new_name)
            except Exception:
                QMessageBox.warning(self, "알림", f"'{new_name}'은(는) 이미 사용 중인 이름입니다.")
                return
            notify_data_changed()
            self.refresh()

    def edit_supplier_via_picker(self):
        picker = SupplierPickerDialog(self)
        if picker.exec() != QDialog.Accepted or not picker.selected_supplier:
            return
        channel = next((c for c in db.get_channels() if c["id"] == picker.selected_supplier["id"]), None)
        if not channel:
            return
        dialog = EditSupplierDialog(channel, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def delete_supplier_via_picker(self):
        picker = SupplierPickerDialog(self)
        if picker.exec() != QDialog.Accepted or not picker.selected_supplier:
            return
        cid = picker.selected_supplier["id"]
        name = picker.selected_supplier["name"]
        related_count = len(db.get_purchases(supplier_id=cid))
        if confirm_delete(
                self, f"'{name}' 거래처",
                "삭제해도 매입 데이터 자체는 남지만, 거래처 이름 정보는 사라집니다.",
                extra_warning=(f"연결된 입고(매입) 내역이 {related_count:,}건 있습니다."
                               if related_count else ""),
                double_check=bool(related_count)):
            db.delete_channel(cid)
            notify_data_changed()
            self.refresh()

    def open_supplier_management(self):
        dialog = SupplierManagementDialog(self)
        dialog.exec()
        self.refresh()

    def delete_selected(self, table, ids, is_supplier):
        cid, name = self._selected_row(table, ids)
        if cid is None:
            QMessageBox.warning(self, "알림", "삭제할 항목을 표에서 선택해주세요.")
            return
        if is_supplier:
            related_count = len(db.get_purchases(supplier_id=cid))
            related_label = "입고(매입) 내역"
        else:
            related_count = db.get_channel_order_count(cid)
            related_label = "주문"
        msg_detail = f"삭제해도 {related_label} 데이터 자체는 남지만, 이름 정보는 사라집니다."
        if confirm_delete(
                self, f"'{name}' {'거래처' if is_supplier else '판매채널'}",
                msg_detail,
                extra_warning=(f"연결된 {related_label}이(가) {related_count:,}건 있습니다."
                               if related_count else ""),
                double_check=bool(related_count)):
            db.delete_channel(cid)
            notify_data_changed()
            self.refresh()

    # ---------- 데이터 백업/복원 ----------
    # ---------- 보안(자동 잠금) 설정 ----------
    def _update_lock_secret_hint(self):
        if self.lock_mode_combo.currentData() == "pin":
            self.lock_secret_input.setEchoMode(QLineEdit.Password)
            self.lock_secret_input.setPlaceholderText("예: 1234")
            self.lock_hint.setText("· 번호 입력: 정한 번호를 입력해야 잠금이 풀립니다.")
        else:
            self.lock_secret_input.setEchoMode(QLineEdit.Normal)
            self.lock_secret_input.setPlaceholderText("예: 5")
            self.lock_hint.setText("· 클릭 횟수: 잠금 화면의 버튼을 정한 횟수만큼 누르면 풀립니다. "
                                    "(번호를 외우기 번거로울 때 간편하게 쓰세요)")

    def open_convenience_settings(self):
        ConvenienceSettingsDialog(self).exec()

    def _load_lock_settings(self):
        minutes = int(_qsettings.value("lock/minutes", 0) or 0)
        idx = self.lock_minutes_combo.findData(minutes)
        self.lock_minutes_combo.setCurrentIndex(idx if idx >= 0 else 0)
        mode = _qsettings.value("lock/mode", "pin")
        idx = self.lock_mode_combo.findData(mode)
        self.lock_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.lock_secret_input.setText(str(_qsettings.value("lock/secret", "") or ""))
        qk = _qsettings.value("lock/quick_key", "off")
        idx = self.quick_lock_combo.findData(qk)
        self.quick_lock_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._update_lock_secret_hint()

    def save_lock_settings(self):
        minutes = self.lock_minutes_combo.currentData() or 0
        mode = self.lock_mode_combo.currentData()
        secret = self.lock_secret_input.text().strip()
        quick_key = self.quick_lock_combo.currentData() or "off"
        # 즉시 잠금만 쓰고 자동 잠금은 안 쓰는 경우도 해제 값은 반드시 필요
        if quick_key != "off" and not secret:
            QMessageBox.warning(self, "알림",
                                "즉시 잠금을 쓰려면 해제 값(PIN/횟수)을 먼저 입력해주세요.")
            return
        if minutes and not secret:
            QMessageBox.warning(self, "알림", "잠금을 켜려면 해제 값을 입력해주세요.")
            return
        if minutes and mode == "click":
            if not secret.isdigit() or not (1 <= int(secret) <= 20):
                QMessageBox.warning(self, "알림", "클릭 횟수는 1~20 사이의 숫자로 입력해주세요.")
                return
        _qsettings.setValue("lock/minutes", minutes)
        _qsettings.setValue("lock/mode", mode)
        _qsettings.setValue("lock/secret", secret)
        _qsettings.setValue("lock/quick_key", quick_key)
        if _main_window_ref is not None:
            _main_window_ref.reset_lock_timer()
        msg = "자동 잠금 설정을 저장했습니다." if minutes else "자동 잠금을 사용하지 않도록 설정했습니다."
        if quick_key != "off":
            label = dict(space2="스페이스바 빠르게 2번", space3="스페이스바 빠르게 3번",
                         esc2="ESC 빠르게 2번", ctrl_l="Ctrl + L").get(quick_key, "")
            msg += f"\n즉시 잠금: {label}"
        QMessageBox.information(self, "완료", msg)

    def lock_now(self):
        if not _qsettings.value("lock/secret"):
            QMessageBox.warning(self, "알림", "먼저 해제 값을 입력하고 저장해주세요.")
            return
        if _main_window_ref is not None:
            _main_window_ref.lock_now()


    def change_db_location(self):
        """데이터 파일을 다른 폴더로 옮기고, 앞으로 그 위치를 쓰도록 저장"""
        folder = ask_directory(self, "데이터 파일을 저장할 폴더 선택", "settings")
        if not folder:
            return
        new_path = os.path.join(folder, "ledger.db")
        current = db.get_db_path()
        if os.path.abspath(new_path) == os.path.abspath(current):
            QMessageBox.information(self, "알림", "이미 그 위치를 사용하고 있습니다.")
            return

        if os.path.exists(new_path):
            reply = QMessageBox.question(
                self, "이미 파일이 있어요",
                f"선택한 폴더에 이미 ledger.db 파일이 있습니다.\n\n"
                f"[예] 그 파일을 그대로 사용합니다 (지금 데이터는 현재 위치에 남아있음)\n"
                f"[아니오] 취소\n\n"
                f"{new_path}")
            if reply != QMessageBox.Yes:
                return
        else:
            try:
                shutil.copy2(current, new_path)
            except Exception as e:
                QMessageBox.critical(self, "오류", f"데이터 파일을 옮기지 못했습니다:\n{e}")
                return

        _qsettings.setValue("db/path", new_path)
        self.db_path_label.setText(f"데이터 파일 위치: {new_path}")
        QMessageBox.information(
            self, "완료",
            f"데이터 파일 위치를 바꿨습니다.\n\n{new_path}\n\n"
            "⚠️ 프로그램을 껐다 다시 켜면 이 위치의 데이터로 작동합니다.\n"
            "(기존 위치의 파일은 그대로 남겨뒀으니, 문제가 없으면 나중에 지우셔도 됩니다)")

    def reset_db_location(self):
        if QMessageBox.question(
                self, "기본 위치로",
                "데이터 파일 위치를 프로그램 폴더(기본값)로 되돌릴까요?\n"
                "다시 시작하면 적용됩니다.") != QMessageBox.Yes:
            return
        _qsettings.remove("db/path")
        default_path = os.path.join(os.path.dirname(os.path.abspath(db.__file__)), "ledger.db")
        self.db_path_label.setText(f"데이터 파일 위치: {default_path}")
        QMessageBox.information(self, "완료", "기본 위치로 되돌렸습니다. 프로그램을 다시 켜주세요.")

    def _pick_update_folder(self):
        folder = ask_directory(self, "업데이트 파일이 들어있는 폴더 선택", "update")
        if folder:
            self.update_src_input.setText(folder)

    def run_update(self):
        """업데이트 확인 -> 내려받기 -> 덮어쓰기 -> 재시작"""
        import updater
        location = self.update_src_input.text().strip()
        if not location:
            QMessageBox.information(
                self, "업데이트 위치 필요",
                "먼저 업데이트 위치를 넣어주세요.\n\n"
                "· 폴더 예) D:\\장부업데이트\n"
                "· 주소 예) https://내주소/update/\n\n"
                "그 위치에 version.json 과 압축파일을 놓아두면 됩니다.")
            return
        _qsettings.setValue("update/location", location)

        has_new, info, msg = updater.check_update(location, BUILD_VERSION)
        if not has_new:
            QMessageBox.information(self, "업데이트 확인", msg)
            return

        notes = (info or {}).get("notes", "")
        if QMessageBox.question(
                self, "업데이트 설치",
                msg + (f"\n\n[변경 내용]\n{notes}" if notes else "")
                + "\n\n설치할까요?\n"
                  "· 설치 전에 프로그램 폴더를 자동으로 백업합니다\n"
                  "· 장부 데이터(ledger.db)는 그대로 유지됩니다\n"
                  "· 설치가 끝나면 프로그램이 다시 시작됩니다") != QMessageBox.Yes:
            return

        try:
            backup_path = updater.backup_current()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"백업에 실패해서 중단했습니다.\n{e}")
            return

        try:
            extract_dir = updater.download_and_extract(location, info)
            changed = updater.apply_update(extract_dir)
        except Exception as e:
            QMessageBox.critical(
                self, "오류",
                f"업데이트 중 문제가 생겼습니다.\n{e}\n\n"
                f"백업해둔 폴더로 되돌릴 수 있습니다:\n{backup_path}")
            return

        if updater.is_frozen():
            QMessageBox.information(
                self, "업데이트 완료",
                f"파일 {changed}개를 새로 받았습니다.\n\n"
                "지금은 exe로 실행 중이라 새 소스가 바로 적용되지 않습니다.\n"
                "EXE_만들기.bat 으로 실행파일을 다시 만든 뒤 켜주세요.\n\n"
                f"백업 폴더: {backup_path}")
            return

        QMessageBox.information(
            self, "업데이트 완료",
            f"파일 {changed}개를 새로 받았습니다.\n"
            "프로그램을 다시 시작합니다.\n\n"
            f"백업 폴더: {backup_path}")
        if updater.restart_app():
            QApplication.instance().quit()
        else:
            QMessageBox.information(self, "알림", "프로그램을 직접 껐다가 다시 켜주세요.")

    def backup_data(self):
        selection_dialog = BackupSelectionDialog(self)
        if selection_dialog.exec() != QDialog.Accepted:
            return
        excluded_tables = selection_dialog.get_excluded_tables()

        default_name = f"ledger_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        filepath = ask_save_file(self, "백업 파일로 저장", default_name, "DB 파일 (*.db)", "backup")
        if not filepath:
            return
        try:
            db.export_selective_backup(filepath, exclude_tables=excluded_tables)
            QMessageBox.information(self, "완료", "백업이 완료되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"백업 중 오류가 발생했습니다:\n{e}")

    def restore_data(self):
        filepath = ask_open_file(self, "백업 파일 선택", "DB 파일 (*.db)", "backup")
        if not filepath:
            return
        if not confirm_delete(
                self, "현재 저장된 모든 데이터 (복원으로 덮어쓰기)",
                f"선택한 백업 파일:<br><b>{os.path.basename(filepath)}</b><br><br>"
                "복원 후에는 프로그램을 껐다가 다시 실행해주세요.",
                extra_warning="지금 장부에 있는 내용이 백업 파일의 내용으로 전부 교체됩니다.",
                double_check=True,
                title="⚠️ 복원 확인"):
            return
        try:
            shutil.copy2(filepath, db.DB_PATH)
            QMessageBox.information(self, "완료", "복원이 완료되었습니다. 프로그램을 재시작해주세요.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"복원 중 오류가 발생했습니다:\n{e}")

    # ---------- 위험 구역 ----------
    def reset_all_data(self):
        counts = ""
        try:
            c = db.get_data_counts()
            counts = "<br>".join(f"· {k} {v:,}건" for k, v in c.items() if v)
        except Exception:
            counts = ""
        if not confirm_delete(
                self, "모든 장부 데이터 (전체 초기화)",
                ("지워지는 항목:<br>" + counts + "<br><br>" if counts else "")
                + "주문/품목/입고(매입)/지출/정산/업로드이력/재고조정 데이터가 모두 삭제됩니다.<br>"
                  "(판매채널 목록과 거래처 정보는 그대로 유지됩니다)",
                extra_warning="장부 전체를 처음 상태로 되돌립니다. 백업이 없으면 절대 복구할 수 없습니다.",
                double_check=True,
                title="🛑 전체 초기화"):
            return
        db.reset_all_data()
        QMessageBox.information(self, "완료", "초기화되었습니다. (판매채널/거래처 정보는 유지됨)")
        self.refresh()


# ---------------------------------------------------------------------------
# 메인 윈도우
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    NAV_GROUPS = [
        ("📋  업무", ["dashboard_tab", "incoming_tab", "orders_tab", "products_tab", "settlement_tab"]),
        ("📈  분석", ["report_tab"]),
        ("⚙️  관리", ["settings_tab"]),
    ]
    NAV_LABELS = {
        "dashboard_tab": "대시보드",
        "incoming_tab": "입고 관리",
        "orders_tab": "주문 관리",
        "products_tab": "품목 관리",
        "settlement_tab": "정산/지출 관리",
        "report_tab": "리포트",
        "settings_tab": "설정",
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"온라인 판매 장부 - 스마트스토어/11번가/쿠팡/ESM ({BUILD_VERSION})")

        self.dashboard_tab = DashboardTab()
        self.incoming_tab = IncomingTab()
        self.orders_tab = OrdersTab(on_data_changed=self.dashboard_tab.refresh)
        self.products_tab = ProductsTab()
        self.settlement_tab = SettlementTab()
        self.report_tab = ReportTab()
        self.settings_tab = SettingsTab()

        self.stack = QStackedWidget()
        self.nav_list = QListWidget()
        # 스페이스바/방향키로 메뉴가 움직이지 않게 함 (즉시 잠금 단축키와 겹침 방지)
        self.nav_list.setFocusPolicy(Qt.NoFocus)
        self.nav_list.setFixedWidth(190)
        self.nav_list.setStyleSheet("""
            QListWidget { background-color: #2C3E50; border: none; outline: none; padding-top: 10px; }
            QListWidget::item { color: #ECF0F1; padding: 12px 16px; font-size: 13px; }
            QListWidget::item:selected { background-color: #2980B9; color: white; font-weight: bold; }
            QListWidget::item:hover:!selected { background-color: #34495E; }
        """)

        self._row_to_page = {}
        row = 0
        for header_text, attr_names in self.NAV_GROUPS:
            header_item = QListWidgetItem(header_text)
            header_item.setFlags(Qt.NoItemFlags)
            f = header_item.font()
            f.setBold(True)
            f.setPointSize(9)
            header_item.setFont(f)
            header_item.setForeground(QColor("#7F8C8D"))
            self.nav_list.addItem(header_item)
            row += 1
            for attr in attr_names:
                widget = getattr(self, attr)
                item = QListWidgetItem("   " + self.NAV_LABELS[attr])
                self.nav_list.addItem(item)
                page_index = self.stack.addWidget(widget)
                self._row_to_page[row] = page_index
                row += 1

        self.nav_list.currentRowChanged.connect(self.on_nav_changed)

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.nav_list)
        central_layout.addWidget(self.stack, stretch=1)
        self.setCentralWidget(central)

        self._restore_window_state()

        global _main_window_ref
        _main_window_ref = self

        # ---------- 자동 잠금 ----------
        self._locked = False
        self.setWindowIcon(make_app_icon())
        self._lock_cover = None   # 잠금 시 화면을 덮는 가림막
        self._quick_timer = QElapsedTimer()   # 즉시잠금 단축키 연타 감지용
        self._quick_count = 0
        self._last_quick_ms = 0
        self._lock_timer = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._lock_screen)
        QApplication.instance().installEventFilter(self)
        self.reset_lock_timer()

    # ---------- 자동 잠금 ----------
    def reset_lock_timer(self):
        """설정된 시간만큼 아무 조작이 없으면 화면을 잠금 (0분이면 사용 안 함)"""
        self._lock_timer.stop()
        try:
            minutes = int(_qsettings.value("lock/minutes", 0) or 0)
        except (TypeError, ValueError):
            minutes = 0
        if minutes > 0 and not self._locked:
            self._lock_timer.start(minutes * 60 * 1000)

    # 즉시 잠금 단축키 종류 (설정에서 고름)
    QUICK_LOCK_KEYS = {
        "space2": (Qt.Key_Space, 2, "스페이스바 빠르게 2번"),
        "space3": (Qt.Key_Space, 3, "스페이스바 빠르게 3번"),
        "esc2": (Qt.Key_Escape, 2, "ESC 빠르게 2번"),
        "ctrl_l": (Qt.Key_L, 1, "Ctrl + L"),
    }

    def _is_typing_now(self):
        """글자를 입력 중인 칸(검색창/금액칸 등)에 커서가 있으면 단축키를 무시.
        (메모에 스페이스 두 번 쳤다고 잠기면 안 되니까)"""
        try:
            w = QApplication.focusWidget()
        except Exception:
            return False
        return isinstance(w, (QLineEdit, QSpinBox, QDateEdit, QComboBox))

    def _check_quick_lock(self, event):
        """설정된 단축키가 눌렸는지 확인해서, 맞으면 즉시 잠금"""
        mode = _qsettings.value("lock/quick_key", "off")
        if mode == "off" or mode not in self.QUICK_LOCK_KEYS:
            return False
        if not _qsettings.value("lock/secret"):
            return False   # 해제 값이 없으면 잠글 수 없음

        key, need, _label = self.QUICK_LOCK_KEYS[mode]
        if event.key() != key:
            return False

        if mode == "ctrl_l":
            if event.modifiers() & Qt.ControlModifier:
                self.lock_now()
                return True
            return False

        # 연타형(스페이스/ESC): 글자 입력 중이면 무시
        if self._is_typing_now():
            return False
        # 키를 누르고 있을 때 자동으로 반복되는 건 연타가 아님
        if event.isAutoRepeat():
            return False

        now = self._quick_timer.elapsed() if self._quick_timer.isValid() else 0
        if not self._quick_timer.isValid():
            self._quick_timer.start()
            now = 0
        # 600ms 안에 다시 눌러야 연타로 인정
        # 한 번 누른 키가 위젯을 타고 올라가며 이 필터를 여러 번 지나감.
        # 50ms 안에 또 들어온 건 같은 눌림이므로 세지 않음
        # (이것 때문에 스페이스바 1번에 잠기던 문제가 있었음)
        if self._quick_count > 0 and now - self._last_quick_ms < 50:
            return False
        if now - self._last_quick_ms > 600:
            self._quick_count = 0
        self._quick_count += 1
        self._last_quick_ms = now
        if self._quick_count >= need:
            self._quick_count = 0
            self.lock_now()
            return True
        return False

    def eventFilter(self, obj, event):
        # 마우스/키보드 조작이 있으면 잠금 대기시간을 다시 셈
        if event.type() == QEvent.KeyPress and not self._locked:
            try:
                if self._check_quick_lock(event):
                    return True
            except Exception:
                pass
        if event.type() in (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
            if not self._locked:
                self.reset_lock_timer()

        # 스페이스바가 버튼·탭·목록을 눌러버리는 걸 막음
        # (글자를 입력하는 칸에서는 그대로 띄어쓰기가 되어야 하므로 예외)
        if (event.type() in (QEvent.KeyPress, QEvent.KeyRelease)
                and event.key() == Qt.Key_Space and not self._is_typing_now()):
            return True
        return super().eventFilter(obj, event)

    def _lock_screen(self):
        if self._locked:
            return
        mode = _qsettings.value("lock/mode", "pin")
        secret = _qsettings.value("lock/secret", "0000")
        if not secret:
            return
        self._locked = True
        # 잠금 중에는 뒤쪽 메뉴/데이터가 그대로 보이면 의미가 없으므로
        # 메인 화면 전체를 흐리게(블러) 가림
        self._apply_lock_blur(True)
        try:
            while True:
                dialog = UnlockDialog(mode, secret, self)
                if dialog.exec() == QDialog.Accepted:
                    break
        finally:
            self._apply_lock_blur(False)
            self._locked = False
            self.reset_lock_timer()

    def _apply_lock_blur(self, on):
        """잠금 상태 표시.
        화면 전체를 새까맣게 덮으면 답답해서, 앱 중앙 기준 85% 영역에만
        '텍스트를 못 읽을 정도'의 약한 블러를 겁니다.
        (테두리 15%는 그대로 보여서 어떤 프로그램인지는 알 수 있음)"""
        if on:
            try:
                effect = QGraphicsBlurEffect(self)
                effect.setBlurRadius(6)   # 글자만 못 읽을 정도의 약한 흐림
                central = self.centralWidget()
                if central is not None:
                    central.setGraphicsEffect(effect)
            except Exception:
                pass
            try:
                if getattr(self, "_lock_cover", None) is None:
                    cover = QWidget(self)
                    cover.setObjectName("lockCover")
                    # 불투명하게 가리지 않고 살짝만 덮음 (블러를 보조하는 정도)
                    cover.setStyleSheet(
                        "#lockCover { background-color: rgba(30, 40, 55, 60);"
                        " border-radius: 12px; }")
                    cv = QVBoxLayout(cover)
                    cv.setAlignment(Qt.AlignCenter)
                    msg = QLabel("🔒  화면이 잠겨 있습니다")
                    msg.setAlignment(Qt.AlignCenter)
                    msg.setStyleSheet(
                        "color: white; font-size: 22px; font-weight: bold;"
                        "background-color: rgba(20, 28, 40, 190);"
                        "padding: 14px 26px; border-radius: 10px;")
                    cv.addWidget(msg)
                    self._lock_cover = cover
                self._lock_cover.setGeometry(self._lock_cover_rect())
                self._lock_cover.raise_()
                self._lock_cover.show()
            except Exception:
                pass
        else:
            try:
                central = self.centralWidget()
                if central is not None:
                    central.setGraphicsEffect(None)
            except Exception:
                pass
            if getattr(self, "_lock_cover", None) is not None:
                self._lock_cover.hide()

    def show_data_status_toast(self, msec=3000):
        """최신 데이터 상태를 화면 위쪽에 잠깐 띄움 (잠금 해제 직후 안내용)"""
        try:
            text = SplashScreen._build_data_info()
        except Exception:
            text = ""
        if not text:
            return
        toast = QLabel(text.replace("\n", "<br>"), self)
        toast.setAlignment(Qt.AlignCenter)
        toast.setStyleSheet(
            "background-color: rgba(23, 32, 42, 235); color: #EAF2F8;"
            "font-size: 14px; padding: 14px 26px; border-radius: 10px;"
            "border: 1px solid rgba(255,255,255,60);")
        toast.adjustSize()
        toast.move(max(10, (self.width() - toast.width()) // 2), 60)
        toast.show()
        toast.raise_()
        QTimer.singleShot(msec, toast.deleteLater)

    def _lock_cover_rect(self):
        """앱 중앙 기준 85% 크기의 사각형 (테두리 15%는 가리지 않음)"""
        r = self.rect()
        w = int(r.width() * 0.85)
        h = int(r.height() * 0.85)
        return QRect(r.x() + (r.width() - w) // 2,
                     r.y() + (r.height() - h) // 2, w, h)

    def resizeEvent(self, event):
        # 잠금 가림막이 떠 있는 동안 창 크기가 바뀌어도 화면 전체를 계속 덮도록
        super().resizeEvent(event)
        if getattr(self, "_lock_cover", None) is not None and self._lock_cover.isVisible():
            self._lock_cover.setGeometry(self._lock_cover_rect())

    def lock_now(self):
        """설정에서 '지금 잠그기'를 눌렀을 때"""
        self._lock_timer.stop()
        self._lock_screen()

    def refresh_all_tabs(self):
        """데이터가 바뀌면 화면을 갱신.
        예전엔 모든 탭을 매번 전부 새로고침해서, 품목 하나만 수정해도 6개 화면이
        동시에 다시 그려지느라 눈에 띄게 느렸음. 이제는 지금 보고 있는 화면만
        즉시 갱신하고, 나머지는 '다시 그려야 함' 표시만 해뒀다가 그 화면으로
        이동할 때 갱신함 (보이는 결과는 같고 속도만 빨라짐)."""
        current = self.stack.currentWidget()
        all_tabs = [self.dashboard_tab, self.incoming_tab, self.orders_tab,
                    self.products_tab, self.settlement_tab, self.report_tab, self.settings_tab]
        # 나머지 탭은 나중에 갱신하도록 표시만 해둠
        self._dirty_tabs = {id(t) for t in all_tabs if t is not current}

        # 콤보박스류(거래처·채널·통장 목록)는 값이 남아있으면 혼란스러우니 항상 즉시 갱신
        for reload_fn in (
            lambda: self.incoming_tab.reload_suppliers(),
            lambda: self.orders_tab.reload_channels(),
            lambda: self.settlement_tab.reload_pp_suppliers(),
            lambda: self.settlement_tab.reload_bank_accounts(),
            lambda: self.settlement_tab.reload_settle_channels(),
            lambda: self.settlement_tab.reload_cards(),
        ):
            try:
                reload_fn()
            except Exception:
                pass

        self._refresh_tab(current)

    def _refresh_tab(self, widget):
        """탭 하나를 갱신하고 '갱신 필요' 표시를 지움"""
        if widget is None:
            return
        try:
            if widget is self.report_tab:
                sub = self.report_tab.stack.currentWidget()
                if sub is not None and hasattr(sub, "refresh"):
                    sub.refresh()
            elif hasattr(widget, "refresh"):
                widget.refresh()
        except Exception:
            pass
        if hasattr(self, "_dirty_tabs"):
            self._dirty_tabs.discard(id(widget))

    def _restore_window_state(self):
        """창 크기/위치, 마지막으로 보고 있던 메뉴를 기억해뒀다가 복원 (항상 자동 저장됨)"""
        geometry = _qsettings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1430, 975)

        # 프로그램을 켜면 항상 대시보드부터 보이게 함
        self.nav_list.setCurrentRow(1)

        # 리포트는 항상 첫 항목(매출분석 > 기간별 이익)에서 시작
        self.report_tab.nav_list.setCurrentRow(1)

    def closeEvent(self, event):
        if not conv_on("confirm_exit"):
            _qsettings.setValue("window/geometry", self.saveGeometry())
            _qsettings.setValue("window/last_nav_row", self.nav_list.currentRow())
            _qsettings.setValue("window/last_report_nav_row", self.report_tab.nav_list.currentRow())
            super().closeEvent(event)
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("종료 확인")
        box.setText("프로그램을 종료할까요?\n\n"
                     "· [저장하고 종료] 데이터를 디스크에 확실히 기록한 뒤 종료합니다\n"
                     "· [그냥 종료] 바로 종료합니다")
        save_btn = box.addButton("💾 저장하고 종료", QMessageBox.AcceptRole)
        quit_btn = box.addButton("그냥 종료", QMessageBox.DestructiveRole)
        box.addButton("취소", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (save_btn, quit_btn):
            event.ignore()
            return

        if clicked is save_btn:
            ok, detail = db.flush_to_disk()
            if ok:
                try:
                    db.auto_backup(keep=10)   # 저장과 함께 백업본도 하나 남겨둠
                except Exception:
                    pass
                QMessageBox.information(
                    self, "저장 완료",
                    f"데이터를 저장했습니다.\n\n{detail}\n\n위치: {db.get_db_path()}")
            else:
                reply = QMessageBox.critical(
                    self, "저장 실패",
                    f"데이터를 저장하지 못했습니다.\n\n{detail}\n\n"
                    f"위치: {db.get_db_path()}\n\n"
                    "네트워크 드라이브(Z: 등)나 USB가 끊겼을 수 있어요.\n"
                    "그래도 종료하시겠습니까? (입력한 내용이 사라질 수 있습니다)",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply != QMessageBox.Yes:
                    event.ignore()
                    return

        _qsettings.setValue("window/geometry", self.saveGeometry())
        _qsettings.setValue("window/last_nav_row", self.nav_list.currentRow())
        _qsettings.setValue("window/last_report_nav_row", self.report_tab.nav_list.currentRow())
        super().closeEvent(event)

    def apply_lock_settings(self):
        """자동 잠금 설정을 바꾸면 즉시 반영 (설정 화면에서 호출)"""
        self.reset_lock_timer()

    def on_nav_changed(self, row):
        if row not in self._row_to_page:
            return
        page_index = self._row_to_page[row]
        self.stack.setCurrentIndex(page_index)
        widget = self.stack.widget(page_index)
        # 그 화면으로 이동할 때 갱신 (뒤에서 바뀐 내용이 있으면 여기서 반영됨)
        self._refresh_tab(widget)
        _qsettings.setValue("window/last_nav_row", row)


def _install_global_exception_handler():
    """어디서든 예외가 발생하면 반드시 오류창이 뜨고 error_log.txt에 기록되게 함.
    (버튼을 눌러도 '아무 반응이 없다'는 문제의 실제 원인이 화면에 안 보이는
    예외일 가능성이 높아서, 그걸 반드시 눈에 보이게 만드는 안전장치)"""
    import traceback

    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error_log.txt")

    def handler(exc_type, exc_value, exc_tb):
        error_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 70}\n{datetime.now()}\n{error_text}\n")
        except Exception:
            pass
        try:
            QMessageBox.critical(
                None, "예상치 못한 오류",
                f"오류가 발생했습니다:\n\n{exc_type.__name__}: {exc_value}\n\n"
                f"프로그램 폴더의 error_log.txt 파일에 자세한 내용이 기록되었습니다."
            )
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = handler


BUILD_VERSION = "2026-08-01-r45-107"  # 파일 교체가 제대로 됐는지 확인용 (창 제목에 표시됨)

_main_window_ref = None  # MainWindow 인스턴스에 대한 전역 참조 (전역 새로고침용)


def safe_db(func, *args, default=None, parent=None, what="작업", **kwargs):
    """DB 작업을 감싸서, 실패해도 프로그램이 멈추지 않고 안내만 하도록 함"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        msg = str(e)
        if parent is not None:
            if "locked" in msg or "unable to open" in msg:
                QMessageBox.warning(
                    parent, "잠시 후 다시 시도해주세요",
                    f"{what} 중 데이터 파일에 접근하지 못했습니다.\n\n"
                    "· 다른 프로그램(엑셀 등)이 파일을 열고 있는지 확인해주세요\n"
                    "· 네트워크 드라이브라면 연결 상태를 확인해주세요")
            else:
                QMessageBox.warning(parent, "알림", f"{what} 중 문제가 있었습니다:\n{msg}")
        return default


def notify_data_changed():
    """거래처/채널/품목/주문/입고/지출/정산/통장 등 어디서든 데이터가 바뀌면
    호출 - 모든 탭이 최신 상태로 갱신되도록 함"""
    if _main_window_ref is not None:
        try:
            _main_window_ref.refresh_all_tabs()
        except Exception:
            pass  # 새로고침 실패가 원래 하려던 작업(저장 등)을 막으면 안 됨


def _warn_if_new_empty_database(parent=None):
    """새 폴더에 압축을 풀고 실행했을 때, 데이터가 텅 빈 새 DB로 시작되는 상황을 알려줌.
    (이전 폴더에 있던 ledger.db를 못 찾아서 '데이터가 사라졌다'고 오해하는 걸 방지)"""
    try:
        if _qsettings.value("db/path"):
            return   # 사용자가 데이터 위치를 직접 지정해둔 경우엔 안내 불필요
        if db.get_orders() or db.get_products():
            return   # 데이터가 있으면 정상
        if _qsettings.value("db/new_db_notice_shown"):
            return   # 한 번 안내했으면 다시 띄우지 않음
        _qsettings.setValue("db/new_db_notice_shown", True)
        QMessageBox.information(
            parent, "데이터 파일 안내",
            "지금 비어 있는 새 장부로 시작합니다.\n\n"
            f"데이터 저장 위치:\n{db.get_db_path()}\n\n"
            "혹시 이전에 쓰던 데이터가 다른 폴더에 있다면(새 버전을 다른 폴더에 푼 경우 등),\n"
            "설정 > 프로그램 정보 > '📁 위치 변경'에서 그 폴더를 지정하면 이어서 쓸 수 있어요.\n"
            "(그 폴더의 ledger.db 파일을 여기로 복사해 오셔도 됩니다)")
    except Exception:
        pass


def _ensure_usable_database(app):
    """데이터 파일을 열 수 있는지 확인하고, 안 되면 쓸 수 있는 위치를 찾아 옮김.
    (예전엔 여기서 실패하면 'unable to open database file' 오류만 뜨고
     프로그램이 아예 안 켜졌음 - 반드시 스스로 복구되게 함)"""
    saved = _qsettings.value("db/path")
    if saved:
        actual = db.set_db_path(saved)
        if os.path.abspath(actual) != os.path.abspath(saved):
            _qsettings.remove("db/path")   # 못 쓰는 위치였으면 설정 정리

    # 파일이 손상됐는지 먼저 확인 (database disk image is malformed 대응)
    try:
        if db.is_db_corrupted():
            mode, detail = db.recover_corrupted_db()
            QMessageBox.warning(
                None, "데이터 파일 복구",
                "데이터 파일이 손상되어 있어 자동으로 복구했습니다.\n\n"
                f"{detail}\n\n"
                "손상된 원본은 같은 폴더에 .broken_날짜 이름으로 보관해뒀습니다.\n\n"
                "※ 프로그램을 강제 종료하거나, 동기화 폴더(OneDrive 등)·USB에서\n"
                "   실행하면 파일이 손상될 수 있어요. 되도록 로컬 폴더에서 쓰시고\n"
                "   종료할 때 [저장하고 종료]를 눌러주세요.")
    except Exception:
        pass

    if db.can_use_db_path(db.get_db_path()):
        # 네트워크 드라이브/USB 등은 연결이 끊기면 입력한 내용이 저장되지 않으므로 미리 알림
        path = db.get_db_path()
        drive = os.path.splitdrive(os.path.abspath(path))[0].upper()
        is_network = path.startswith("\\\\") or (drive and drive not in ("C:", ""))
        if is_network and _qsettings.value("warn/network_drive") != path:
            QMessageBox.warning(
                None, "데이터 위치 확인",
                f"데이터 파일이 이동식·네트워크 드라이브에 있습니다.\n\n{path}\n\n"
                "연결이 끊기면 입력한 내용이 저장되지 않을 수 있어요.\n"
                "설정 > 프로그램 정보에서 '📁 위치 변경'으로 컴퓨터 내부 폴더\n"
                "(예: 내 문서)로 옮기시는 것을 권장합니다.\n\n"
                "(이 안내는 위치를 바꾸기 전까지 한 번만 표시됩니다)")
            _qsettings.setValue("warn/network_drive", path)
        return True

    # 지금 위치를 못 쓰는 경우: 쓸 수 있는 다른 위치를 찾아 자동으로 전환
    old_path = db.get_db_path()
    new_path = db.find_usable_db_path()
    if not new_path:
        QMessageBox.critical(
            None, "데이터 파일을 열 수 없습니다",
            f"데이터 파일을 열 수 없어 프로그램을 시작할 수 없습니다.\n\n"
            f"위치: {old_path}\n\n"
            "· 프로그램 폴더가 읽기 전용이거나 권한이 없을 수 있어요\n"
            "· 압축을 푼 폴더가 OneDrive 같은 동기화 폴더면\n"
            "  동기화되지 않는 폴더(예: 바탕화면)로 옮겨보세요\n"
            "· 백신 프로그램이 막고 있을 수도 있습니다")
        return False

    db.set_db_path(new_path)
    _qsettings.setValue("db/path", new_path)
    QMessageBox.information(
        None, "데이터 위치를 변경했습니다",
        f"기존 위치의 데이터 파일을 열 수 없어서,\n"
        f"사용 가능한 위치로 자동 전환했습니다.\n\n"
        f"이전 위치: {old_path}\n"
        f"새 위치: {new_path}\n\n"
        "기존 데이터가 있다면 설정 > 프로그램 정보에서\n"
        "'📁 위치 변경'으로 원래 폴더를 다시 지정하실 수 있어요.")
    return True



def make_app_icon():
    """작업표시줄·창 제목에 쓰이는 프로그램 아이콘을 직접 그려서 만듦.
    별도 그림 파일 없이 코드로 그리므로 exe로 묶어도 아이콘이 빠지지 않음.
    (파란-보라 그라데이션 원 + 장부 모양 + 원화 표시)"""
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QLinearGradient, QBrush, QPen
    from PySide6.QtCore import QRectF

    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        pt = QPainter(pm)
        pt.setRenderHint(QPainter.Antialiasing)
        s = size

        # 바탕 원 (파랑 -> 보라 그라데이션)
        grad = QLinearGradient(0, 0, s, s)
        grad.setColorAt(0.0, QColor("#4A6CF7"))
        grad.setColorAt(0.55, QColor("#7B4DF3"))
        grad.setColorAt(1.0, QColor("#B14DE8"))
        pt.setBrush(QBrush(grad))
        pt.setPen(Qt.NoPen)
        pt.drawEllipse(QRectF(s * 0.02, s * 0.02, s * 0.96, s * 0.96))

        # 위쪽 하이라이트 (유리 느낌)
        hi = QLinearGradient(0, 0, 0, s * 0.55)
        hi.setColorAt(0.0, QColor(255, 255, 255, 90))
        hi.setColorAt(1.0, QColor(255, 255, 255, 0))
        pt.setBrush(QBrush(hi))
        pt.drawEllipse(QRectF(s * 0.06, s * 0.04, s * 0.88, s * 0.62))

        if s >= 32:
            # 장부(책) 모양
            pt.setBrush(QBrush(QColor(255, 255, 255, 240)))
            pt.drawRoundedRect(QRectF(s * 0.26, s * 0.24, s * 0.48, s * 0.54),
                               s * 0.05, s * 0.05)
            # 책등
            pt.setBrush(QBrush(QColor("#2C3E70")))
            pt.drawRoundedRect(QRectF(s * 0.26, s * 0.24, s * 0.09, s * 0.54),
                               s * 0.04, s * 0.04)
            # 줄
            pt.setPen(QPen(QColor("#9AA6C8"), max(1.0, s * 0.022)))
            for k in range(3):
                y = s * (0.38 + k * 0.11)
                pt.drawLine(int(s * 0.42), int(y), int(s * 0.66), int(y))

        # 원화 표시
        pt.setPen(QPen(QColor("#FFFFFF" if s < 32 else "#F5C542"),
                       max(1.0, s * 0.05)))
        f = pt.font()
        f.setBold(True)
        f.setPointSizeF(max(5.0, s * (0.62 if s < 32 else 0.30)))
        pt.setFont(f)
        rect = (QRectF(0, 0, s, s) if s < 32
                else QRectF(s * 0.52, s * 0.46, s * 0.42, s * 0.42))
        pt.drawText(rect, Qt.AlignCenter, "₩")
        pt.end()
        icon.addPixmap(pm)
    return icon


class SplashScreen(QWidget):
    """시작 스플래시 화면 - 페이드인/페이드아웃 효과"""

    @staticmethod
    def _build_data_info():
        """최신 데이터가 언제까지 들어와 있는지 한 줄로 정리"""
        try:
            d = db.get_last_data_update()
        except Exception:
            return ""
        parts = []
        for key, label in (("order", "주문"), ("purchase", "입고"),
                           ("settlement", "정산"), ("expense", "지출")):
            if d.get(key):
                parts.append(f"{label} {d[key]}")
        if not parts:
            return "아직 등록된 자료가 없습니다"
        head = f"📌 최신 데이터  ({d.get('order_count', 0):,}건)"
        text = head + "\n" + "   ·   ".join(parts)
        if d.get("last_saved_at"):
            text += f"\n🕒 마지막 저장  {d['last_saved_at']}"
        return text

    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setFixedSize(560, 360)
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #1C2833, stop:1 #2E86AB);
                border-radius: 18px;
            }
        """)
        self.setWindowOpacity(0.0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 40)
        layout.setSpacing(14)

        layout.addStretch()
        store = QLabel(STORE_NAME)
        store.setAlignment(Qt.AlignCenter)
        store.setStyleSheet("font-size: 42px; font-weight: 900; color: white;"
                            "letter-spacing: 4px; background: transparent;")
        layout.addWidget(store)

        sub = QLabel("온라인 판매 통합 장부")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("font-size: 16px; color: #AED6F1; background: transparent;")
        layout.addWidget(sub)

        # 장부에 들어있는 자료가 어디까지 입력돼 있는지 시작할 때 잠깐 보여줌
        info = QLabel(self._build_data_info())
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("font-size: 12px; color: #D6EAF8; background: transparent;"
                           "line-height: 150%;")
        layout.addWidget(info)

        layout.addStretch()

        ver = QLabel(f"{APP_VERSION}  |  {BUILD_VERSION}")
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet("font-size: 11px; color: #7F8C8D; background: transparent;")
        layout.addWidget(ver)

        # 중앙 배치
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

        # 페이드인 → 잠깐 표시 → 페이드아웃
        self._opacity = 0.0
        self._phase = "in"
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(20)

    def _tick(self):
        if self._phase == "in":
            self._opacity = min(1.0, self._opacity + 0.05)
            self.setWindowOpacity(self._opacity)
            if self._opacity >= 1.0:
                self._phase = "hold"
                QTimer.singleShot(2200, self._start_out)   # 스플래시 유지 시간(ms)
        elif self._phase == "out":
            self._opacity = max(0.0, self._opacity - 0.05)
            self.setWindowOpacity(self._opacity)
            if self._opacity <= 0.0:
                self._timer.stop()
                self.close()

    def _start_out(self):
        self._phase = "out"


def main():
    _install_global_exception_handler()
    # 윈도우 작업표시줄이 파이썬이 아니라 이 프로그램의 아이콘을 쓰도록 알려줌
    # (이걸 안 하면 파이썬 기본 아이콘이 표시됨)
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "enurihouse.ledger.desktop")
    except Exception:
        pass

    app = QApplication(sys.argv)

    # 이미 실행 중이면 새로 켜지 않고, 켜져 있던 창을 앞으로 불러옴
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    _INSTANCE_KEY = "enurihouse_ledger_single_instance"
    _probe = QLocalSocket()
    _probe.connectToServer(_INSTANCE_KEY)
    if _probe.waitForConnected(300):
        # 실행 중인 창에게 "앞으로 나와라"라고 알리고 이 프로세스는 종료
        _probe.write(b"show")
        _probe.waitForBytesWritten(300)
        _probe.disconnectFromServer()
        QMessageBox.information(
            None, "이미 실행 중",
            "장부 프로그램이 이미 실행 중입니다.\n실행 중인 창을 화면 앞으로 가져옵니다.")
        sys.exit(0)
    QLocalServer.removeServer(_INSTANCE_KEY)   # 비정상 종료로 남은 흔적 정리
    _instance_server = QLocalServer()
    _instance_server.listen(_INSTANCE_KEY)

    app_icon = make_app_icon()
    app.setWindowIcon(app_icon)
    # exe 빌드나 바로가기에서 쓸 수 있도록 아이콘 파일도 만들어둠
    try:
        ico_path = os.path.join(os.path.dirname(db.DB_PATH), "app_icon.ico")
        if not os.path.exists(ico_path):
            app_icon.pixmap(256, 256).save(ico_path)
    except Exception:
        pass
    app.setStyle("Fusion")

    # 데이터 파일부터 확인 (여기서 문제가 있으면 알기 쉽게 안내하고 스스로 복구)
    if not _ensure_usable_database(app):
        sys.exit(1)

    db.init_db()
    # 자동 백업은 하루 한 번만 (매번 하면 시작이 느려짐)
    try:
        today_str = date.today().isoformat()
        if conv_on("auto_backup") and _qsettings.value("backup/last_date") != today_str:
            db.auto_backup(keep=10)
            _qsettings.setValue("backup/last_date", today_str)
    except Exception:
        pass
    # 이전에 등록해둔 채널별 수수료율을, 수수료가 비어있는 기존 주문에 자동 적용
    # (설정에서 수수료율만 등록해두고 자동계산 버튼을 안 눌러서 리포트에 반영이
    #  안 되던 문제 - 앱을 켤 때마다 자동으로 맞춰줌)
    try:
        if conv_on("auto_fee"):
            db.apply_default_fee_rates()
    except Exception:
        pass
    # 스플래시 화면 표시
    splash = SplashScreen()
    splash.show()
    QApplication.processEvents()

    window = MainWindow()
    window.show()

    def _bring_to_front():
        """다른 실행 시도가 있으면 이 창을 앞으로 꺼내줌"""
        conn = _instance_server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(conn.deleteLater)
        try:
            window.setWindowState(
                (window.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
            window.show()
            window.raise_()
            window.activateWindow()
        except Exception:
            pass

    _instance_server.newConnection.connect(_bring_to_front)
    # 자동 잠금이 켜져 있으면 프로그램을 켤 때도 잠금 화면부터 보여줌
    try:
        if int(_qsettings.value("lock/minutes", 0) or 0) > 0 and _qsettings.value("lock/secret"):
            window._lock_screen()
            # 잠금 화면에 가려 시작 안내를 못 봤으므로, 해제 후 다시 잠깐 띄워줌
            window.show_data_status_toast()
    except Exception:
        pass
    _warn_if_new_empty_database(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
