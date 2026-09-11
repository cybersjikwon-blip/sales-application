"""
에누리하우스 온라인 판매 통합 장부 - 태블릿(키오스크) 버전
=========================================================
서피스프로처럼 터치로 쓰는 기기에서 편하게 쓰기 위한 실행 파일입니다.
기능은 기존 프로그램(main.py)과 100% 동일하고, 화면만 터치에 맞게 바꿉니다.

  · 전체화면(키오스크)으로 실행 - 창 테두리 없이 화면을 꽉 채움
  · 버튼·글자·표의 행 높이를 손가락으로 누르기 좋게 키움
  · 왼쪽 메뉴를 크게 만들어 터치로 정확히 고를 수 있게 함
  · 표를 손가락으로 쓸어서(드래그) 스크롤할 수 있게 함
  · 화면 아래에 큰 [◀ 뒤로] [🔒 잠금] [✕ 종료] 버튼을 항상 표시
  · 숫자 입력칸을 누르면 화면 키패드가 떠서 키보드 없이 입력 가능

실행: python main_tablet.py
    (키보드가 있으면 F11로 전체화면 끄고 켤 수 있습니다)

데이터는 기존 프로그램과 같은 ledger.db를 사용합니다.
2층 호스트 PC의 공유 폴더를 지정해두면 같은 장부를 함께 쓸 수 있습니다.
(단, 두 대에서 동시에 열지 말고 한 번에 한 대만 사용하세요)
"""

import sys

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (
    QApplication, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QLabel,
    QMessageBox, QDialog, QGridLayout, QLineEdit, QAbstractItemView,
    QScroller, QTableWidget,
)

import main as app_main
import database as db


TABLET_VERSION = "R5.0-T"   # 태블릿 버전 표시

# 터치로 쓰기 좋은 크기로 키운 스타일
TABLET_STYLE = """
QWidget { font-size: 15px; }
QPushButton {
    min-height: 44px; padding: 8px 16px; font-size: 15px;
    border: 1px solid #B0BEC5; border-radius: 8px; background: #FAFAFA;
}
QPushButton:pressed { background: #D6EAF8; }
QLineEdit, QComboBox, QSpinBox, QDateEdit {
    min-height: 40px; font-size: 15px; padding: 4px 8px;
}
QComboBox QAbstractItemView::item { min-height: 40px; }
QTableWidget { font-size: 14px; }
QHeaderView::section { min-height: 36px; font-size: 14px; }
QTabBar::tab { min-height: 44px; min-width: 110px; font-size: 15px; }
QCheckBox { min-height: 34px; font-size: 15px; }
QCheckBox::indicator { width: 26px; height: 26px; }
QGroupBox { font-size: 15px; }
QListWidget { font-size: 16px; }
QListWidget::item { min-height: 48px; padding-left: 6px; }
QScrollBar:vertical { width: 18px; }
QScrollBar:horizontal { height: 18px; }
"""


class NumberPadDialog(QDialog):
    """키보드 없이 숫자를 입력하는 화면 키패드"""

    def __init__(self, title, initial="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(320, 420)

        layout = QVBoxLayout(self)
        self.display = QLineEdit(str(initial or ""))
        self.display.setAlignment(Qt.AlignRight)
        self.display.setStyleSheet("font-size: 28px; padding: 12px;")
        self.display.setMinimumHeight(60)
        layout.addWidget(self.display)

        grid = QGridLayout()
        keys = [("7", 0, 0), ("8", 0, 1), ("9", 0, 2),
                ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
                ("1", 2, 0), ("2", 2, 1), ("3", 2, 2),
                ("0", 3, 0), (".", 3, 1), ("←", 3, 2)]
        for text, r, col in keys:
            btn = QPushButton(text)
            btn.setMinimumHeight(58)
            btn.setStyleSheet("font-size: 20px; font-weight: bold;")
            btn.clicked.connect(lambda checked=False, t=text: self._press(t))
            grid.addWidget(btn, r, col)
        layout.addLayout(grid)

        quick = QHBoxLayout()
        for amount in ("+1000", "+10000", "000"):
            b = QPushButton(amount)
            b.setMinimumHeight(48)
            b.clicked.connect(lambda checked=False, a=amount: self._quick(a))
            quick.addWidget(b)
        layout.addLayout(quick)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("전체 지우기")
        clear_btn.clicked.connect(lambda: self.display.setText(""))
        btn_row.addWidget(clear_btn)
        ok_btn = QPushButton("✅ 확인")
        ok_btn.setStyleSheet("font-weight: bold; background: #D5F5E3;")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _press(self, key):
        if key == "←":
            self.display.setText(self.display.text()[:-1])
        else:
            self.display.setText(self.display.text() + key)

    def _quick(self, token):
        text = self.display.text().strip()
        if token == "000":
            self.display.setText(text + "000")
            return
        try:
            base = float(text) if text else 0
        except ValueError:
            base = 0
        base += int(token)
        self.display.setText(str(int(base)) if base == int(base) else str(base))

    def value(self):
        return self.display.text().strip()


class TouchLineEdit:
    """숫자 입력칸을 터치하면 키패드를 띄워주는 도우미 (기존 위젯에 덧입힘)"""

    @staticmethod
    def install(window):
        app = QApplication.instance()
        app.installEventFilter(_KeypadFilter(window))


class _KeypadFilter(QWidget):
    """숫자 입력칸을 눌렀을 때 화면 키패드를 띄우는 이벤트 필터"""

    NUMERIC_HINTS = ("금액", "단가", "수량", "가격", "원가", "수수료", "배송비",
                     "재고", "율", "번호", "잔액")

    def __init__(self, window):
        super().__init__(window)
        self.window_ref = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonDblClick and isinstance(obj, QLineEdit):
            if obj.isReadOnly() or not obj.isEnabled():
                return False
            hint = (obj.placeholderText() or "") + (obj.toolTip() or "")
            looks_numeric = any(h in hint for h in self.NUMERIC_HINTS)
            current = obj.text().replace(",", "")
            if looks_numeric or current.replace(".", "").replace("-", "").isdigit():
                dialog = NumberPadDialog("숫자 입력", obj.text(), self.window_ref)
                if dialog.exec() == QDialog.Accepted:
                    obj.setText(dialog.value())
                return True
        return False


def _enable_touch_scroll(widget):
    """표를 손가락으로 쓸어서 스크롤할 수 있게 함"""
    for table in widget.findChildren(QTableWidget):
        try:
            QScroller.grabGesture(table.viewport(), QScroller.LeftMouseButtonGesture)
            table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.verticalHeader().setDefaultSectionSize(40)   # 행 높이 키우기
        except Exception:
            pass


class TabletMainWindow(app_main.MainWindow):
    """기존 MainWindow를 그대로 쓰되, 터치에 맞게 화면만 손봄"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            f"에누리하우스 장부 (태블릿) - {TABLET_VERSION} / {app_main.BUILD_VERSION}")

        # 왼쪽 메뉴를 터치하기 좋게 넓힘
        try:
            self.nav_list.setMinimumWidth(210)
            self.nav_list.setIconSize(self.nav_list.iconSize())
        except Exception:
            pass

        self._add_bottom_bar()
        _enable_touch_scroll(self)
        self.showFullScreen()

    def _add_bottom_bar(self):
        """화면 아래에 항상 보이는 큰 버튼 줄 (터치 전용)"""
        central = self.centralWidget()
        old_layout = central.layout()
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)

        inner = QWidget()
        inner.setLayout(old_layout)
        wrapper_layout.addWidget(inner, stretch=1)

        bar = QWidget()
        bar.setStyleSheet("background: #2C3E50;")
        bar.setFixedHeight(64)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 6, 10, 6)

        def make_btn(text, handler, color="#34495E"):
            b = QPushButton(text)
            b.setMinimumHeight(50)
            b.setMinimumWidth(120)
            b.setStyleSheet(
                f"QPushButton {{ background: {color}; color: white; font-size: 16px;"
                f"font-weight: bold; border-radius: 8px; border: none; }}"
                f"QPushButton:pressed {{ background: #1B2631; }}")
            b.clicked.connect(handler)
            return b

        bar_layout.addWidget(make_btn("◀ 이전 메뉴", self._go_prev))
        bar_layout.addWidget(make_btn("메뉴 ▶", self._go_next))
        bar_layout.addStretch()

        self.tablet_title = QLabel("")
        self.tablet_title.setStyleSheet("color: #ECF0F1; font-size: 17px; font-weight: bold;")
        bar_layout.addWidget(self.tablet_title)
        bar_layout.addStretch()

        bar_layout.addWidget(make_btn("🔄 새로고침", self._refresh_current, "#16A085"))
        bar_layout.addWidget(make_btn("🔒 잠금", self._lock, "#B7950B"))
        bar_layout.addWidget(make_btn("⛶ 창모드", self._toggle_fullscreen))
        bar_layout.addWidget(make_btn("✕ 종료", self.close, "#C0392B"))

        wrapper_layout.addWidget(bar)
        self.setCentralWidget(wrapper)
        self.nav_list.currentRowChanged.connect(self._update_title)
        self._update_title(self.nav_list.currentRow())

    def _update_title(self, row):
        item = self.nav_list.item(row) if row is not None else None
        if item is not None:
            self.tablet_title.setText(item.text().strip())

    def _selectable_rows(self):
        return sorted(self._row_to_page.keys())

    def _go_prev(self):
        rows = self._selectable_rows()
        if not rows:
            return
        cur = self.nav_list.currentRow()
        idx = rows.index(cur) if cur in rows else 0
        self.nav_list.setCurrentRow(rows[max(idx - 1, 0)])

    def _go_next(self):
        rows = self._selectable_rows()
        if not rows:
            return
        cur = self.nav_list.currentRow()
        idx = rows.index(cur) if cur in rows else 0
        self.nav_list.setCurrentRow(rows[min(idx + 1, len(rows) - 1)])

    def _refresh_current(self):
        try:
            self._refresh_tab(self.stack.currentWidget())
            _enable_touch_scroll(self)
        except Exception:
            pass

    def _lock(self):
        try:
            self.lock_now()
        except Exception:
            QMessageBox.information(
                self, "알림", "설정 > 보안에서 자동 잠금을 먼저 설정해주세요.")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            self._toggle_fullscreen()
            return
        super().keyPressEvent(event)


def main():
    app_main._install_global_exception_handler()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(TABLET_STYLE)

    if not app_main._ensure_usable_database(app):
        sys.exit(1)

    db.init_db()
    try:
        if app_main.conv_on("auto_fee"):
            db.apply_default_fee_rates()
    except Exception:
        pass

    window = TabletMainWindow()
    window.show()
    TouchLineEdit.install(window)

    try:
        if (int(app_main._qsettings.value("lock/minutes", 0) or 0) > 0
                and app_main._qsettings.value("lock/secret")):
            window._lock_screen()
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
