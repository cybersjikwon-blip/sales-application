# -*- coding: utf-8 -*-
"""
database.py
온라인 판매(스마트스토어/11번가/쿠팡/ESM) 장부 프로그램용 SQLite 데이터베이스 모듈
"""
import sqlite3
import os
from datetime import datetime, date, timedelta

def _base_dir():
    """장부 파일(ledger.db)을 둘 폴더.
    EXE로 만들면 sys._MEIPASS(임시폴더)에서 실행되는데, 거기에 저장하면
    프로그램을 끄는 순간 임시폴더가 지워져서 데이터가 사라진다.
    그래서 EXE일 때는 exe 파일이 있는 실제 폴더를 쓴다."""
    import sys
    if getattr(sys, "frozen", False):          # PyInstaller로 만든 EXE
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DB_PATH = os.path.join(_base_dir(), "ledger.db")

DEFAULT_CHANNELS = ["스마트스토어", "11번가", "쿠팡", "ESM(G마켓/옥션)", "기타"]


from contextlib import contextmanager


@contextmanager
def db_session():
    """오류가 나도 연결을 반드시 닫아주는 안전한 연결 사용법.
    (닫히지 않은 연결이 쌓이면 'unable to open database file' 같은
     불안정한 오류가 생기므로, 새 코드는 이 방식을 쓰는 것이 안전)"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _retry_on_lock(fn, attempts=3, delay=0.25):
    """DB가 잠깐 잠겨 있을 때 바로 실패하지 않고 몇 번 다시 시도.
    (네트워크 드라이브·백신 검사 중에 순간적으로 막히는 경우가 있어서)"""
    import time
    last = None
    for i in range(attempts):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            last = e
            if "locked" not in str(e) and "busy" not in str(e):
                raise
            time.sleep(delay * (i + 1))
    raise last


def get_connection():
    """DB 연결. 이 함수는 매우 자주(화면 갱신마다 수십~수백 번) 호출되므로
    여기서는 반드시 가벼운 작업만 해야 함.
    (WAL 설정 같은 무거운 PRAGMA를 여기 넣었더니 프로그램 전체가 눈에 띄게
     느려졌던 적이 있음 - 그런 설정은 init_db에서 딱 한 번만 함)"""
    def _connect():
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    return _retry_on_lock(_connect)


_EXPECTED_COLUMNS = {
    "channels": [
        ("channel_type", "TEXT DEFAULT '온라인채널'"), ("business_number", "TEXT"),
        ("contact", "TEXT"), ("manager", "TEXT"), ("memo", "TEXT"),
        ("platform_type", "TEXT"), ("site_url", "TEXT"), ("settle_cycle", "TEXT"),
        ("discount_rate", "REAL"), ("settle_bank_id", "INTEGER"),
        ("purchase_discount_rate", "REAL DEFAULT 0"),
        ("shipping_fee_rate", "REAL DEFAULT 0"),
    ],
    "products": [
        ("sku", "TEXT"), ("option_name", "TEXT DEFAULT ''"), ("cost_price", "INTEGER DEFAULT 0"),
        ("sale_price", "INTEGER DEFAULT 0"), ("stock_qty", "INTEGER DEFAULT 0"),
        ("memo", "TEXT"), ("fee_rate", "REAL"),
    ],
    "orders": [
        ("option_name", "TEXT DEFAULT ''"), ("matched_product_id", "INTEGER"),
        ("is_settled", "INTEGER DEFAULT 0"), ("settled_date", "TEXT"),
        ("settled_amount", "INTEGER DEFAULT 0"), ("stock_deducted_qty", "INTEGER DEFAULT 0"),
        ("stock_deducted_product_id", "INTEGER"), ("shipping_fee", "INTEGER DEFAULT 0"),
        ("fee_amount", "INTEGER DEFAULT 0"), ("settlement_amount", "INTEGER DEFAULT 0"),
        ("buyer_name", "TEXT"), ("status", "TEXT"), ("memo", "TEXT"),
        ("address", "TEXT"), ("phone", "TEXT"), ("receiver_name", "TEXT"), ("upload_id", "INTEGER"),
        # 배송비를 "수수료를 뺀 순액"으로 별도 수익 항목으로 잡기 위한 컬럼들
        # shipping_fee        : 고객에게 받은 배송비(총액)
        # shipping_fee_rate   : 그 배송비에 적용한 채널 수수료율(%)
        # shipping_fee_charge : 배송비에서 채널이 떼간 수수료 금액
        # shipping_net        : 순배송수익 = shipping_fee - shipping_fee_charge
        ("shipping_fee_rate", "REAL"), ("shipping_fee_charge", "INTEGER DEFAULT 0"),
        ("shipping_net", "INTEGER DEFAULT 0"),
    ],
    "purchases": [
        ("paid_amount", "INTEGER DEFAULT 0"), ("memo", "TEXT"),
        ("discount_rate", "REAL DEFAULT 0"), ("discount_amount", "REAL DEFAULT 0"),
    ],
    "expenses": [("bank_account_id", "INTEGER"), ("memo", "TEXT"),
                  ("payment_method", "TEXT DEFAULT '통장'"), ("card_id", "INTEGER")],
    "purchase_payments": [("payment_method", "TEXT DEFAULT '통장'"), ("card_id", "INTEGER"),
                            ("bank_account_id", "INTEGER"), ("memo", "TEXT"),
                            ("discount_rate", "REAL DEFAULT 0"), ("discount_amount", "INTEGER DEFAULT 0"),
                            ("supply_amount", "INTEGER DEFAULT 0")],
    "cards": [("card_company", "TEXT"), ("card_number", "TEXT"), ("memo", "TEXT")],
    "settlements": [
        ("payment_method", "TEXT DEFAULT '현금'"), ("bank_account_id", "INTEGER"), ("memo", "TEXT"),
        # 어떤 정산 파일 업로드로 만들어진 정산인지 연결 (업로드 이력 삭제 시 함께 지울 수 있게)
        ("settlement_upload_id", "INTEGER"),
    ],
    "bank_accounts": [
        ("bank_name", "TEXT"), ("account_number", "TEXT"),
        ("balance", "INTEGER DEFAULT 0"), ("memo", "TEXT"),
    ],
    "stock_adjustments": [("reason", "TEXT"), ("memo", "TEXT")],
}


def _safe_add_column(cur, table, column, ddl):
    """컬럼 추가 마이그레이션을 안전하게 수행.
    한 단계가 실패해도 init_db 전체가 중단되지 않도록 함 (예전엔 여기서 예외가
    나면 뒤쪽의 신규 테이블 생성까지 통째로 건너뛰어져서, 나중에 그 테이블을
    쓰려고 할 때 'no such table' 오류가 났음)"""
    try:
        cur.execute(f"PRAGMA table_info({table})")
        existing = [row[1] for row in cur.fetchall()]
        if column not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
    except sqlite3.Error:
        pass


def _configure_once():
    """프로그램 시작 시 한 번만 실행되는 DB 설정.
    WAL 모드는 -wal/-shm 보조 파일을 만들어야 해서, 동기화 폴더(OneDrive 등)나
    권한이 제한된 위치에서는 "unable to open database file" 오류를 냈음.
    그래서 가장 호환성이 좋은 기본(delete) 모드를 쓰도록 되돌림."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode = DELETE")
        except sqlite3.Error:
            pass
        conn.close()
    except sqlite3.Error:
        pass


def init_db():
    _configure_once()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        channel_type TEXT DEFAULT '온라인채널',
        business_number TEXT,
        contact TEXT,
        manager TEXT,
        memo TEXT
    )
    """)

    # 기존 DB에 컬럼이 없을 경우 마이그레이션(추가)
    for col_name, col_type in [
        ("channel_type", "TEXT DEFAULT '온라인채널'"),
        ("business_number", "TEXT"),
        ("contact", "TEXT"),
        ("manager", "TEXT"),
        ("memo", "TEXT"),
    ]:
        _safe_add_column(cur, "channels", col_name, f"{col_name} {col_type}")
    _safe_add_column(cur, "channels", "platform_type", "platform_type TEXT")
    _safe_add_column(cur, "channels", "site_url", "site_url TEXT")
    _safe_add_column(cur, "channels", "settle_cycle", "settle_cycle TEXT")
    _safe_add_column(cur, "channels", "discount_rate", "discount_rate REAL")
    _safe_add_column(cur, "channels", "settle_bank_id", "settle_bank_id INTEGER")
    _safe_add_column(cur, "channels", "address", "address TEXT")
    _safe_add_column(cur, "channels", "business_type_ch", "business_type_ch TEXT")
    _safe_add_column(cur, "channels", "business_item_ch", "business_item_ch TEXT")
    _safe_add_column(cur, "channels", "ceo", "ceo TEXT")
    _safe_add_column(cur, "channels", "purchase_discount_rate", "purchase_discount_rate REAL DEFAULT 0")
    # 채널별 "배송비에 붙는 수수료율(%)" - 배송비 순수익 계산에 사용
    _safe_add_column(cur, "channels", "shipping_fee_rate", "shipping_fee_rate REAL DEFAULT 0")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT,
        name TEXT NOT NULL,
        option_name TEXT DEFAULT '',
        cost_price INTEGER DEFAULT 0,
        sale_price INTEGER DEFAULT 0,
        stock_qty INTEGER DEFAULT 0,
        memo TEXT
    )
    """)

    _safe_add_column(cur, "products", "option_name", "option_name TEXT DEFAULT ''")
    _safe_add_column(cur, "products", "fee_rate", "fee_rate REAL")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER,
        order_no TEXT,
        order_date TEXT,
        product_name TEXT,
        option_name TEXT,
        qty INTEGER DEFAULT 1,
        sale_price INTEGER DEFAULT 0,
        total_amount INTEGER DEFAULT 0,
        fee_amount INTEGER DEFAULT 0,
        shipping_fee INTEGER DEFAULT 0,
        settlement_amount INTEGER DEFAULT 0,
        buyer_name TEXT,
        status TEXT,
        memo TEXT,
        matched_product_id INTEGER,
        is_settled INTEGER DEFAULT 0,
        settled_date TEXT,
        settled_amount INTEGER DEFAULT 0,
        FOREIGN KEY (channel_id) REFERENCES channels(id),
        FOREIGN KEY (matched_product_id) REFERENCES products(id)
    )
    """)

    # 기존 DB에 컬럼이 없을 경우 마이그레이션(추가)
    _safe_add_column(cur, "orders", "option_name", "option_name TEXT DEFAULT ''")
    _safe_add_column(cur, "orders", "matched_product_id", "matched_product_id INTEGER")
    _safe_add_column(cur, "orders", "is_settled", "is_settled INTEGER DEFAULT 0")
    _safe_add_column(cur, "orders", "settled_date", "settled_date TEXT")
    _safe_add_column(cur, "orders", "settled_amount", "settled_amount INTEGER DEFAULT 0")
    _safe_add_column(cur, "orders", "stock_deducted_qty", "stock_deducted_qty INTEGER DEFAULT 0")
    _safe_add_column(cur, "orders", "stock_deducted_product_id", "stock_deducted_product_id INTEGER")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        category TEXT,
        amount INTEGER DEFAULT 0,
        memo TEXT,
        bank_account_id INTEGER
    )
    """)

    _safe_add_column(cur, "expenses", "bank_account_id", "bank_account_id INTEGER")
    _safe_add_column(cur, "purchases", "discount_rate", "discount_rate REAL DEFAULT 0")
    _safe_add_column(cur, "purchases", "discount_amount", "discount_amount REAL DEFAULT 0")
    _safe_add_column(cur, "expenses", "payment_method", "payment_method TEXT DEFAULT '통장'")
    _safe_add_column(cur, "expenses", "card_id", "card_id INTEGER")
    _safe_add_column(cur, "purchase_payments", "payment_method", "payment_method TEXT DEFAULT '통장'")
    _safe_add_column(cur, "purchase_payments", "card_id", "card_id INTEGER")
    _safe_add_column(cur, "purchase_payments", "discount_rate", "discount_rate REAL DEFAULT 0")
    _safe_add_column(cur, "purchase_payments", "discount_amount", "discount_amount INTEGER DEFAULT 0")
    _safe_add_column(cur, "purchase_payments", "discount_rate", "discount_rate REAL DEFAULT 0")
    _safe_add_column(cur, "purchase_payments", "discount_amount", "discount_amount INTEGER DEFAULT 0")
    _safe_add_column(cur, "purchase_payments", "supply_amount", "supply_amount INTEGER DEFAULT 0")
    _safe_add_column(cur, "orders", "address", "address TEXT")
    _safe_add_column(cur, "orders", "phone", "phone TEXT")
    _safe_add_column(cur, "orders", "receiver_name", "receiver_name TEXT")
    _safe_add_column(cur, "orders", "upload_id", "upload_id INTEGER")
    # 배송비 순수익(수수료 제외) 관련 컬럼
    _safe_add_column(cur, "orders", "shipping_fee_rate", "shipping_fee_rate REAL")
    _safe_add_column(cur, "orders", "shipping_fee_charge", "shipping_fee_charge INTEGER DEFAULT 0")
    _safe_add_column(cur, "orders", "shipping_net", "shipping_net INTEGER DEFAULT 0")

    # 품목 매입가(원가) 변동 이력
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cost_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        old_cost REAL,
        new_cost REAL,
        source TEXT,
        memo TEXT,
        changed_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cost_history_product ON cost_history(product_id)")

    # 통장간 자금이동(이체) 기록
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bank_transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transfer_date TEXT,
        from_bank_id INTEGER,
        to_bank_id INTEGER,
        amount INTEGER DEFAULT 0,
        fee INTEGER DEFAULT 0,
        memo TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER,
        settle_date TEXT,
        amount INTEGER DEFAULT 0,
        memo TEXT,
        payment_method TEXT DEFAULT '현금',
        bank_account_id INTEGER,
        FOREIGN KEY (channel_id) REFERENCES channels(id),
        FOREIGN KEY (bank_account_id) REFERENCES bank_accounts(id)
    )
    """)

    _safe_add_column(cur, "settlements", "payment_method", "payment_method TEXT DEFAULT '현금'")
    _safe_add_column(cur, "settlements", "bank_account_id", "bank_account_id INTEGER")
    # 정산 파일 업로드와 연결 (업로드 이력 삭제 시 "정산내역까지 삭제" 옵션에 사용)
    _safe_add_column(cur, "settlements", "settlement_upload_id", "settlement_upload_id INTEGER")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_date TEXT,
        supplier_id INTEGER,
        product_id INTEGER,
        qty INTEGER DEFAULT 0,
        unit_cost INTEGER DEFAULT 0,
        total_amount INTEGER DEFAULT 0,
        paid_amount INTEGER DEFAULT 0,
        memo TEXT,
        FOREIGN KEY (supplier_id) REFERENCES channels(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bank_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        bank_name TEXT,
        account_number TEXT,
        balance INTEGER DEFAULT 0,
        memo TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        return_type TEXT NOT NULL,        -- '반품'(고객->우리) / '반출'(우리->거래처)
        return_date TEXT,
        channel_id INTEGER,               -- 반품: 판매채널 / 반출: 거래처
        order_id INTEGER,                 -- 반품일 때 원주문 (있으면)
        product_id INTEGER,
        product_name TEXT,
        option_name TEXT,
        qty INTEGER DEFAULT 0,
        unit_price REAL DEFAULT 0,
        total_amount REAL DEFAULT 0,
        buyer_name TEXT,
        reason TEXT,
        status TEXT DEFAULT '접수',        -- 접수 / 완료
        memo TEXT,
        stock_applied INTEGER DEFAULT 0,  -- 재고 반영 여부(완료 처리 시 1)
        FOREIGN KEY (channel_id) REFERENCES channels(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cash_adjustments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        adjust_date TEXT,
        change_amount INTEGER DEFAULT 0,
        reason TEXT,
        memo TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_bundles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bundle_product_id INTEGER NOT NULL,      -- 조합(세트) 품목
        component_product_id INTEGER NOT NULL,   -- 구성 품목
        qty INTEGER DEFAULT 1,                   -- 세트 1개당 구성품 수량
        FOREIGN KEY (bundle_product_id) REFERENCES products(id),
        FOREIGN KEY (component_product_id) REFERENCES products(id),
        UNIQUE(bundle_product_id, component_product_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        card_company TEXT,
        card_number TEXT,
        memo TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS purchase_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER,
        payment_date TEXT,
        amount INTEGER DEFAULT 0,
        bank_account_id INTEGER,
        memo TEXT,
        FOREIGN KEY (supplier_id) REFERENCES channels(id),
        FOREIGN KEY (bank_account_id) REFERENCES bank_accounts(id)
    )
    """)

    # 구버전에서 product_id 기반으로 만들어진 테이블이 있으면 상품명(대분류) 기반으로 교체
    # (CREATE TABLE IF NOT EXISTS는 이미 있는 테이블의 구조를 바꿔주지 않으므로 직접 처리)
    try:
        cur.execute("PRAGMA table_info(channel_fee_rates)")
        fee_cols = [row[1] for row in cur.fetchall()]
        if fee_cols and "product_name" not in fee_cols:
            cur.execute("DROP TABLE channel_fee_rates")
    except sqlite3.Error:
        pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS channel_fee_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        fee_rate REAL NOT NULL,
        FOREIGN KEY (channel_id) REFERENCES channels(id),
        UNIQUE(channel_id, product_name)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS stock_adjustments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        adjust_date TEXT,
        change_qty INTEGER DEFAULT 0,
        reason TEXT,
        memo TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS upload_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        channel_id INTEGER,
        uploaded_at TEXT,
        row_count INTEGER DEFAULT 0,
        FOREIGN KEY (channel_id) REFERENCES channels(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS option_presets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT UNIQUE NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS qty_presets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT NOT NULL,          -- 'incoming'(입고관리) / 'order'(주문관리)
        qty INTEGER NOT NULL,
        sort_order INTEGER DEFAULT 0,
        UNIQUE(scope, qty)
    )
    """)
    for scope, defaults in (("incoming", [1, 100, 200, 500, 1000, 10000]),
                             ("order", [1, 100, 200, 500, 1000])):
        for i, q in enumerate(defaults):
            cur.execute("INSERT OR IGNORE INTO qty_presets (scope, qty, sort_order) VALUES (?,?,?)",
                        (scope, q, i))

    cur.execute("""
    CREATE TABLE IF NOT EXISTS expense_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    """)
    for name in DEFAULT_EXPENSE_CATEGORIES:
        cur.execute("INSERT OR IGNORE INTO expense_categories (name) VALUES (?)", (name,))

    for name in DEFAULT_CHANNELS:
        cur.execute("INSERT OR IGNORE INTO channels (name) VALUES (?)", (name,))

    # 안전망: 오래된 DB에 빠져있는 컬럼을 자동으로 찾아서 채워줌.
    # (신규 컬럼을 추가할 때 위쪽 마이그레이션 목록에 넣는 걸 깜빡하더라도,
    #  "no such column" / IndexError 같은 오류가 사용자에게 나가지 않도록 보호)
    for table, expected in _EXPECTED_COLUMNS.items():
        try:
            cur.execute(f"PRAGMA table_info({table})")
            existing = [row[1] for row in cur.fetchall()]
            if not existing:
                continue
            for col_name, col_type in expected:
                if col_name not in existing:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
        except sqlite3.Error:
            pass

    conn.commit()
    conn.close()

    # 마켓마다 다른 날짜 형식으로 저장된 기존 주문 데이터를 통일 (리포트 정렬/표기 문제 해결)
    # 여기서 예외가 나도 앱 시작 자체는 막히지 않도록 보호 (테이블 구조가 아주
    # 오래된 DB에서 이 후처리가 실패하면서 init_db 전체가 중단되던 문제 방지)
    try:
        normalize_existing_order_dates()
    except sqlite3.Error:
        pass


# ---------------- Channels ----------------
def get_channels():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM channels ORDER BY id").fetchall()
    conn.close()
    return rows


def get_channel_id_by_name(name):
    conn = get_connection()
    row = conn.execute("SELECT id FROM channels WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row["id"] if row else None


def add_channel(name):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO channels (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def add_channel_detailed(name, channel_type="온라인채널", business_number="", contact="", manager="", memo=""):
    """유형/사업자번호/연락처/담당자/메모까지 포함해서 채널(업체) 등록. 새로 생긴 채널의 id를 반환"""
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO channels
           (name, channel_type, business_number, contact, manager, memo)
           VALUES (?,?,?,?,?,?)""",
        (name, channel_type, business_number, contact, manager, memo),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM channels WHERE name=?", (name,)).fetchone()
    conn.close()
    return row["id"] if row else None


def rename_channel(channel_id, new_name):
    conn = get_connection()
    conn.execute("UPDATE channels SET name=? WHERE id=?", (new_name, channel_id))
    conn.commit()
    conn.close()


def get_channel_order_count(channel_id, date_from=None):
    conn = get_connection()
    if date_from:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM orders WHERE channel_id=? "
            "AND substr(COALESCE(order_date,''),1,10) >= ?", (channel_id, date_from)).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) as c FROM orders WHERE channel_id=?",
                            (channel_id,)).fetchone()
    conn.close()
    return row["c"] if row else 0


def get_channel_order_counts_by_period(channel_id):
    """채널별 주문 건수를 이번주/이번달/올해로 나눠서 반환"""
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    month_start = today.replace(day=1).isoformat()
    year_start = today.replace(month=1, day=1).isoformat()
    conn = get_connection()
    def cnt(since):
        row = conn.execute(
            "SELECT COUNT(*) as c FROM orders WHERE channel_id=? "
            "AND substr(COALESCE(order_date,''),1,10) >= ?", (channel_id, since)).fetchone()
        return row["c"] if row else 0
    result = (cnt(week_start), cnt(month_start), cnt(year_start))
    conn.close()
    return result


def delete_channel(channel_id):
    """채널/거래처 삭제. 연결된 주문(channel_id)과 입고(supplier_id)는 NULL로
    남겨둠 (주문/매입 데이터 자체는 보존하고, 채널 이름 정보만 사라짐)"""
    conn = get_connection()
    conn.execute("UPDATE orders SET channel_id=NULL WHERE channel_id=?", (channel_id,))
    conn.execute("UPDATE purchases SET supplier_id=NULL WHERE supplier_id=?", (channel_id,))
    conn.execute("DELETE FROM channels WHERE id=?", (channel_id,))
    conn.commit()
    conn.close()


def reset_all_data():
    """채널 목록/거래처/통장 정보는 그대로 남기고, 그 외 거래 데이터(주문/품목/입고/
    매입지출/지출/정산/업로드이력/재고조정 내역)를 모두 삭제 (완전 초기화)
    -> products를 참조하는 orders/purchases/stock_adjustments를 먼저 지워야
       FOREIGN KEY constraint failed가 나지 않음 (delete_product()와 동일한 원리)
    ⚠️ 통장 잔액(balance)은 초기화되지 않으니, 필요하면 설정에서 직접 조정해주세요."""
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = OFF")   # 순서 상관없이 지울 수 있게 잠깐 끔
    # 나중에 추가된 테이블까지 모두 포함 (없으면 건너뜀)
    for table in ("returns", "shipment_history", "settlement_uploads",
                  "orders", "purchases", "stock_adjustments",
                  "products", "purchase_payments", "expenses",
                  "settlements", "upload_history", "cash_adjustments"):
        try:
            conn.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            pass   # 아직 만들어지지 않은 테이블은 무시
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()


# ---------------- Products ----------------
def get_products():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return rows


def add_product(sku, name, cost_price, sale_price, stock_qty, memo="", option_name="", fee_rate=None):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO products (sku, name, cost_price, sale_price, stock_qty, memo, option_name, fee_rate) VALUES (?,?,?,?,?,?,?,?)",
        (sku, name, cost_price, sale_price, stock_qty, memo, option_name, fee_rate),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    # 등록할 때 넣은 최초 재고를 "재고조정" 기록으로 남겨둠.
    # (재고 재계산은 입고-판매+조정으로 계산하는데, 이 기록이 없으면 등록 시
    #  입력한 재고가 재계산에서 사라져버리기 때문)
    if stock_qty:
        try:
            conn2 = get_connection()
            conn2.execute(
                """INSERT INTO stock_adjustments (product_id, adjust_date, change_qty, reason, memo)
                   VALUES (?,?,?,?,?)""",
                (new_id, date.today().isoformat(), stock_qty, "최초 등록 재고",
                 "품목 등록 시 입력한 재고"))
            conn2.commit()
            conn2.close()
        except Exception:
            pass
    return new_id


def update_product(pid, sku, name, cost_price, sale_price, stock_qty, memo="", option_name="",
                   fee_rate=None, cost_source="품목관리 수정"):
    """cost_source: 원가가 바뀌었을 때 '어디서 바뀌었는지' 이력에 남길 경로 이름
    (입고 등록 / 품목관리 수정 / 엑셀 일괄등록 등)"""
    conn = get_connection()
    # 매입가(원가)가 실제로 달라졌을 때만 변동 이력을 남김
    try:
        prev = conn.execute("SELECT cost_price FROM products WHERE id=?", (pid,)).fetchone()
        old_cost = float(prev["cost_price"] or 0) if prev else 0.0
        new_cost = float(cost_price or 0)
        if prev is not None and abs(old_cost - new_cost) > 0.001:
            conn.execute(
                """INSERT INTO cost_history (product_id, old_cost, new_cost, source)
                   VALUES (?,?,?,?)""",
                (pid, old_cost, new_cost, cost_source))
    except (sqlite3.Error, TypeError, ValueError):
        pass
    conn.execute(
        "UPDATE products SET sku=?, name=?, cost_price=?, sale_price=?, stock_qty=?, memo=?, option_name=?, fee_rate=? WHERE id=?",
        (sku, name, cost_price, sale_price, stock_qty, memo, option_name, fee_rate, pid),
    )
    conn.commit()
    conn.close()


def delete_product(pid):
    """품목 삭제 전, 이 품목을 참조하고 있는 주문(matched_product_id)과
    입고내역(product_id)의 외래키를 먼저 NULL 처리함.
    (이걸 안 하면 SQLite의 FOREIGN KEY constraint 때문에 삭제가 조용히
    실패하거나 오류가 남 - 반복 신고됐던 "삭제가 안 된다" 버그의 실제 원인)"""
    conn = get_connection()
    # 이 품목을 참조하는 곳을 모두 정리. 테이블/컬럼이 없는 옛 DB에서도 멈추지 않도록
    # 각 구문을 개별적으로 보호함 (한 곳이라도 실패하면 삭제 자체가 안 되던 문제 방지)
    cleanups = [
        ("UPDATE orders SET matched_product_id=NULL WHERE matched_product_id=?", (pid,)),
        ("UPDATE orders SET stock_deducted_product_id=NULL, stock_deducted_qty=0 "
         "WHERE stock_deducted_product_id=?", (pid,)),
        ("UPDATE purchases SET product_id=NULL WHERE product_id=?", (pid,)),
        ("DELETE FROM stock_adjustments WHERE product_id=?", (pid,)),
        ("DELETE FROM product_bundles WHERE bundle_product_id=? OR component_product_id=?", (pid, pid)),
    ]
    for sql, args in cleanups:
        try:
            conn.execute(sql, args)
        except sqlite3.Error:
            pass
    try:
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
    except sqlite3.Error:
        # 그래도 실패하면 외래키를 잠시 끄고 한 번 더 시도 (마지막 안전장치)
        conn.rollback()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
    conn.close()


# ---------------- 배송비(순수익) 계산 ----------------
# 배송비는 "고객에게 받은 총액"이 그대로 우리 수익이 아님.
# 마켓이 배송비에도 수수료를 떼가기 때문에, 수수료를 뺀 순액만 수익으로 잡아야 함.
#   순배송수익 = 받은 배송비 - (받은 배송비 × 채널 배송비 수수료율)
# 채널별 배송비 수수료율은 channels.shipping_fee_rate 에 저장하고,
# 값이 없으면(0/NULL) 배송비 전액을 순수익으로 봄.
_SHIPPING_RATE_CACHE = {}


def _channel_shipping_rate(conn, channel_id):
    """채널의 배송비 수수료율(%)을 가져옴. 대량 저장 시 매번 조회하지 않도록 캐시 사용"""
    if not channel_id:
        return 0.0
    if channel_id in _SHIPPING_RATE_CACHE:
        return _SHIPPING_RATE_CACHE[channel_id]
    rate = 0.0
    try:
        r = conn.execute("SELECT shipping_fee_rate FROM channels WHERE id=?", (channel_id,)).fetchone()
        if r and r[0]:
            rate = float(r[0])
    except sqlite3.Error:
        rate = 0.0
    _SHIPPING_RATE_CACHE[channel_id] = rate
    return rate


def clear_shipping_rate_cache():
    """채널 배송비 수수료율을 바꾼 뒤에 호출해서 캐시를 비움"""
    _SHIPPING_RATE_CACHE.clear()


def calc_shipping_parts(shipping_fee, rate):
    """배송비 총액과 수수료율(%)로 (수수료액, 순수익)을 계산해서 돌려줌"""
    fee = int(shipping_fee or 0)
    try:
        rate = float(rate or 0)
    except (TypeError, ValueError):
        rate = 0.0
    if fee == 0:
        return 0, 0
    charge = int(round(fee * rate / 100.0))
    return charge, fee - charge


# ---------------- Orders ----------------
def _with_order_defaults(row: dict, conn=None):
    """주문 dict에 없는 선택 항목(수취인/주소/연락처 등)을 빈 값으로 채워줌
    (기존 호출부가 이 키들을 넘기지 않아도 오류가 나지 않도록)
    아울러 배송비 순수익(수수료 제외)도 여기서 함께 계산해 넣음"""
    row = dict(row)
    for key in ("receiver_name", "address", "phone", "memo", "status", "buyer_name", "option_name"):
        row.setdefault(key, "")
    row.setdefault("upload_id", None)   # 파일 업로드로 들어온 주문만 값이 있음

    # 배송비 순수익 계산 (호출부가 직접 넣어준 값이 있으면 그대로 존중)
    rate = row.get("shipping_fee_rate")
    if rate is None and conn is not None:
        rate = _channel_shipping_rate(conn, row.get("channel_id"))
    charge, net = calc_shipping_parts(row.get("shipping_fee"), rate)
    row["shipping_fee_rate"] = rate or 0.0
    row.setdefault("shipping_fee_charge", charge)
    row.setdefault("shipping_net", net)
    row["shipping_fee_charge"] = charge
    row["shipping_net"] = net
    return row


def add_order(row: dict):
    """row keys: channel_id, order_no, order_date, product_name, option_name,
    qty, sale_price, total_amount, fee_amount, shipping_fee, settlement_amount,
    buyer_name, status, memo"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO orders
        (channel_id, order_no, order_date, product_name, option_name, qty,
         sale_price, total_amount, fee_amount, shipping_fee, settlement_amount,
         buyer_name, status, memo, receiver_name, address, phone, upload_id,
         shipping_fee_rate, shipping_fee_charge, shipping_net)
        VALUES (:channel_id, :order_no, :order_date, :product_name, :option_name, :qty,
                :sale_price, :total_amount, :fee_amount, :shipping_fee, :settlement_amount,
                :buyer_name, :status, :memo, :receiver_name, :address, :phone, :upload_id,
                :shipping_fee_rate, :shipping_fee_charge, :shipping_net)""",
        _with_order_defaults(row, conn),
    )
    conn.commit()
    conn.close()


def update_order(order_id, row: dict):
    """row keys는 add_order와 동일. 기존 주문(수기입력 포함) 내용을 수정할 때 사용"""
    conn = get_connection()
    row = dict(row)
    row["id"] = order_id
    # 채널이나 배송비가 바뀌었을 수 있으므로 배송비 순수익을 다시 계산해서 저장
    rate = row.get("shipping_fee_rate")
    if rate is None:
        rate = _channel_shipping_rate(conn, row.get("channel_id"))
    charge, net = calc_shipping_parts(row.get("shipping_fee"), rate)
    row["shipping_fee_rate"] = rate or 0.0
    row["shipping_fee_charge"] = charge
    row["shipping_net"] = net
    conn.execute(
        """UPDATE orders SET
            channel_id=:channel_id, order_no=:order_no, order_date=:order_date,
            product_name=:product_name, option_name=:option_name, qty=:qty,
            sale_price=:sale_price, total_amount=:total_amount, fee_amount=:fee_amount,
            shipping_fee=:shipping_fee, settlement_amount=:settlement_amount,
            buyer_name=:buyer_name, status=:status, memo=:memo,
            shipping_fee_rate=:shipping_fee_rate,
            shipping_fee_charge=:shipping_fee_charge, shipping_net=:shipping_net
        WHERE id=:id""",
        row,
    )
    conn.commit()
    conn.close()


def get_order_by_id(order_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return row


def bulk_add_orders(rows: list):
    conn = get_connection()
    conn.executemany(
        """INSERT INTO orders
        (channel_id, order_no, order_date, product_name, option_name, qty,
         sale_price, total_amount, fee_amount, shipping_fee, settlement_amount,
         buyer_name, status, memo, receiver_name, address, phone, upload_id,
         shipping_fee_rate, shipping_fee_charge, shipping_net)
        VALUES (:channel_id, :order_no, :order_date, :product_name, :option_name, :qty,
                :sale_price, :total_amount, :fee_amount, :shipping_fee, :settlement_amount,
                :buyer_name, :status, :memo, :receiver_name, :address, :phone, :upload_id,
                :shipping_fee_rate, :shipping_fee_charge, :shipping_net)""",
        [_with_order_defaults(r, conn) for r in rows],
    )
    conn.commit()
    conn.close()


def get_orders(channel_id=None, date_from=None, date_to=None, buyer_search=None):
    conn = get_connection()
    query = """
    SELECT orders.*, channels.name as channel_name
    FROM orders
    LEFT JOIN channels ON orders.channel_id = channels.id
    WHERE 1=1
    """
    params = []
    if channel_id:
        query += " AND orders.channel_id = ?"
        params.append(channel_id)
    # 날짜가 비어있는 주문(마켓 파일에 결제일이 없는 경우 등)은 날짜 조건에서
    # 걸러지지 않도록 함 - 저장은 됐는데 목록에 안 보이는 일을 막기 위함
    if date_from:
        query += " AND (COALESCE(orders.order_date,'')='' OR substr(orders.order_date, 1, 10) >= ?)"
        params.append(date_from)
    if date_to:
        query += " AND (COALESCE(orders.order_date,'')='' OR substr(orders.order_date, 1, 10) <= ?)"
        params.append(date_to)
    if buyer_search:
        # 구매자명 / 수취인명 / 전화번호로 모두 검색.
        # 전화번호는 하이픈·공백을 무시하고 비교하므로 "01076717573"이나
        # 뒷 4자리 "7573"만 입력해도 찾을 수 있음
        digits = "".join(ch for ch in buyer_search if ch.isdigit())
        clauses = ["orders.buyer_name LIKE ?", "orders.receiver_name LIKE ?"]
        params.append(f"%{buyer_search}%")
        params.append(f"%{buyer_search}%")
        if digits:
            clauses.append(
                "REPLACE(REPLACE(REPLACE(COALESCE(orders.phone,''),'-',''),' ',''),'.','') LIKE ?")
            params.append(f"%{digits}%")
        query += " AND (" + " OR ".join(clauses) + ")"
    query += " ORDER BY orders.order_date DESC, orders.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def delete_order(oid):
    reverse_stock_for_order(oid)  # 삭제 전에 차감됐던 재고를 먼저 복원
    conn = get_connection()
    conn.execute("DELETE FROM orders WHERE id=?", (oid,))
    conn.commit()
    conn.close()


def delete_all_orders():
    """전체 주문 삭제 - 삭제 전에 각 주문이 차감했던 재고를 모두 복원함
    (안 하면 자동재고차감 때문에 재고가 실제보다 부족하게 남게 됨)"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, stock_deducted_qty, stock_deducted_product_id FROM orders "
        "WHERE stock_deducted_product_id IS NOT NULL AND stock_deducted_qty > 0"
    ).fetchall()
    for r in rows:
        conn.execute(
            "UPDATE products SET stock_qty = COALESCE(stock_qty,0) + ? WHERE id=?",
            (r["stock_deducted_qty"], r["stock_deducted_product_id"]),
        )
    conn.execute("DELETE FROM orders")
    conn.commit()
    conn.close()


# ---------------- 업로드 파일 이력 ----------------
def add_upload_history(filename, channel_id, row_count):
    conn = get_connection()
    conn.execute(
        "INSERT INTO upload_history (filename, channel_id, uploaded_at, row_count) VALUES (?,?,datetime('now','localtime'),?)",
        (filename, channel_id, row_count),
    )
    conn.commit()
    conn.close()


def get_upload_history(limit=200, date_from=None, date_to=None):
    conn = get_connection()
    query = """
        SELECT upload_history.*, channels.name as channel_name
        FROM upload_history
        LEFT JOIN channels ON upload_history.channel_id = channels.id
        WHERE 1=1
    """
    params = []
    if date_from:
        query += " AND substr(upload_history.uploaded_at, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(upload_history.uploaded_at, 1, 10) <= ?"
        params.append(date_to)
    query += " ORDER BY upload_history.id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def check_recent_duplicate_upload(filename, days=7):
    """최근 N일 이내에 같은 파일명이 업로드된 적 있는지 확인 (있으면 그 이력 반환, 없으면 None)"""
    conn = get_connection()
    row = conn.execute(
        """SELECT upload_history.*, channels.name as channel_name
           FROM upload_history
           LEFT JOIN channels ON upload_history.channel_id = channels.id
           WHERE filename = ? AND uploaded_at >= datetime('now', ?, 'localtime')
           ORDER BY upload_history.id DESC LIMIT 1""",
        (filename, f"-{days} days"),
    ).fetchone()
    conn.close()
    return row


# ---------------- 품목 매칭 (주문의 상품명+옵션명 <-> 등록된 품목명) ----------------
def get_orders_for_matching():
    """매칭 계산용: 모든 주문의 id/상품명/옵션명만 가볍게 조회"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, product_name, option_name, matched_product_id FROM orders"
    ).fetchall()
    conn.close()
    return rows


def bulk_update_matches(id_to_product_id: dict):
    """{order_id: product_id or None} 형태로 일괄 업데이트"""
    conn = get_connection()
    conn.executemany(
        "UPDATE orders SET matched_product_id=? WHERE id=?",
        [(pid, oid) for oid, pid in id_to_product_id.items()],
    )
    conn.commit()
    conn.close()


# ---------------- Expenses ----------------
def get_expenses(year_month=None):
    """year_month('2026-08')를 주면 그 달의 지출만 반환"""
    conn = get_connection()
    query = """SELECT expenses.*,
                      COALESCE(bank_accounts.bank_name, bank_accounts.name) as bank_account_name,
                      cards.name as card_name
               FROM expenses
               LEFT JOIN bank_accounts ON expenses.bank_account_id = bank_accounts.id
               LEFT JOIN cards ON expenses.card_id = cards.id
               WHERE 1=1"""
    params = []
    if year_month:
        query += " AND substr(expenses.date, 1, 7) = ?"
        params.append(year_month)
    query += " ORDER BY date DESC, expenses.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def add_expense(date, category, amount, memo="", bank_account_id=None,
                payment_method="통장", card_id=None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO expenses (date, category, amount, memo, bank_account_id, payment_method, card_id)
           VALUES (?,?,?,?,?,?,?)""",
        (date, category, amount, memo, bank_account_id, payment_method, card_id),
    )
    conn.commit()
    conn.close()
    # 통장 지출일 때만 통장 잔액을 차감 (카드/현금은 통장 잔액과 무관)
    if payment_method == "통장" and bank_account_id:
        adjust_bank_balance(bank_account_id, -amount)


def update_expense(eid, date, category, amount, memo="", bank_account_id=None,
                    payment_method="통장", card_id=None):
    conn = get_connection()
    old = conn.execute(
        "SELECT amount, bank_account_id, payment_method FROM expenses WHERE id=?", (eid,)).fetchone()
    conn.execute(
        """UPDATE expenses SET date=?, category=?, amount=?, memo=?, bank_account_id=?,
                              payment_method=?, card_id=? WHERE id=?""",
        (date, category, amount, memo, bank_account_id, payment_method, card_id, eid),
    )
    conn.commit()
    conn.close()
    # 기존에 통장에서 나갔던 금액은 되돌리고, 새로 통장 지출이면 다시 차감
    if old and (old["payment_method"] or "통장") == "통장" and old["bank_account_id"]:
        adjust_bank_balance(old["bank_account_id"], old["amount"])
    if payment_method == "통장" and bank_account_id:
        adjust_bank_balance(bank_account_id, -amount)


def delete_expense(eid):
    conn = get_connection()
    row = conn.execute(
        "SELECT amount, bank_account_id, payment_method FROM expenses WHERE id=?", (eid,)).fetchone()
    conn.execute("DELETE FROM expenses WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    if row and (row["payment_method"] or "통장") == "통장" and row["bank_account_id"]:
        adjust_bank_balance(row["bank_account_id"], row["amount"])


# ---------------- Settlements ----------------
def get_settlements(exclude_auto=True):
    """정산 입금 내역 조회.
    exclude_auto=True면 '수동 결제완료 처리'처럼 주문 상태 변경 시
    자동 생성된 건은 제외 (이건 실제 입금이 아니라 상태 표시용)"""
    conn = get_connection()
    where = "WHERE COALESCE(settlements.memo,'') NOT LIKE '%수동 결제완료 처리%'" if exclude_auto else ""
    rows = conn.execute(
        f"""SELECT settlements.*, channels.name as channel_name,
                  channels.channel_type as channel_type,
                  bank_accounts.name as bank_account_name, bank_accounts.bank_name as bank_name
           FROM settlements
           LEFT JOIN channels ON settlements.channel_id = channels.id
           LEFT JOIN bank_accounts ON settlements.bank_account_id = bank_accounts.id
           {where}
           ORDER BY settle_date DESC, settlements.id DESC"""
    ).fetchall()
    conn.close()
    return rows


def add_settlement(channel_id, settle_date, amount, memo="", payment_method="통장",
                   bank_account_id=None, settlement_upload_id=None):
    """settlement_upload_id를 넣으면 어떤 정산 파일 업로드로 생긴 건인지 연결됨.
    (업로드 이력을 지울 때 '정산내역까지 함께 삭제'를 고를 수 있게 하기 위함)"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO settlements (channel_id, settle_date, amount, memo, payment_method,
                                    bank_account_id, settlement_upload_id)
           VALUES (?,?,?,?,?,?,?)""",
        (channel_id, settle_date, amount, memo, payment_method, bank_account_id, settlement_upload_id),
    )
    conn.commit()
    conn.close()
    if payment_method == "통장" and bank_account_id:
        adjust_bank_balance(bank_account_id, amount)  # 입금이므로 잔액 증가


def delete_settlement(sid):
    conn = get_connection()
    row = conn.execute("SELECT amount, payment_method, bank_account_id FROM settlements WHERE id=?", (sid,)).fetchone()
    conn.execute("DELETE FROM settlements WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    if row and row["payment_method"] == "통장" and row["bank_account_id"]:
        adjust_bank_balance(row["bank_account_id"], -row["amount"])


# ---------------- Reports ----------------
def get_monthly_summary():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT substr(order_date,1,7) as ym,
               channels.name as channel_name,
               SUM(orders.total_amount) as total_sales,
               SUM(orders.fee_amount) as total_fee,
               SUM(orders.settlement_amount) as total_settlement,
               COUNT(*) as order_count
        FROM orders
        LEFT JOIN channels ON orders.channel_id = channels.id
        GROUP BY ym, channels.name
        ORDER BY ym DESC
        """
    ).fetchall()
    conn.close()
    return rows


def get_channel_summary():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT channels.id as channel_id, channels.name as channel_name,
               SUM(orders.total_amount) as total_sales,
               SUM(orders.fee_amount) as total_fee,
               SUM(orders.settlement_amount) as total_settlement,
               COUNT(*) as order_count
        FROM orders
        LEFT JOIN channels ON orders.channel_id = channels.id
        GROUP BY channels.id, channels.name
        """
    ).fetchall()
    conn.close()
    return rows


# ---------------- 이익(수익) 리포트: 일별/월별/년도별 ----------------
_PERIOD_LEN = {"day": 10, "month": 7, "year": 4}


def get_profit_by_period(period="day", date_from=None, date_to=None):
    """period: 'day' | 'month' | 'year'
    이익 = 매출(결제금액) - 수수료 - 매칭된 품목 원가 합계 + 배송비 순수익
    · 배송비는 매출에 섞지 않고 '배송비순수익'이라는 별도 수익 항목으로 잡음
    · 배송비 순수익 = 받은 배송비 - 배송비에 붙은 채널 수수료
    (원가가 매칭 안 된 주문은 원가 0으로 계산 -> 이익이 실제보다 높게 잡힐 수 있음을 UI에서 안내)
    """
    n = _PERIOD_LEN.get(period, 10)
    conditions = []
    params = []
    if date_from:
        conditions.append("substr(orders.order_date, 1, 10) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("substr(orders.order_date, 1, 10) <= ?")
        params.append(date_to)
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT substr(orders.order_date, 1, {n}) as period_key,
               COUNT(*) as order_count,
               SUM(orders.total_amount) as total_sales,
               SUM(orders.fee_amount) as total_fee,
               SUM(COALESCE(products.cost_price, 0) * orders.qty) as total_cost,
               COALESCE(SUM(orders.shipping_fee), 0) as shipping_total,
               COALESCE(SUM(orders.shipping_fee_charge), 0) as shipping_charge,
               COALESCE(SUM(orders.shipping_net), 0) as shipping_net,
               SUM(orders.total_amount - orders.fee_amount
                   - COALESCE(products.cost_price, 0) * orders.qty)
                   + COALESCE(SUM(orders.shipping_net), 0) as profit,
               SUM(CASE WHEN orders.matched_product_id IS NULL THEN 1 ELSE 0 END) as unmatched_count
        FROM orders
        LEFT JOIN products ON orders.matched_product_id = products.id
        {where_clause}
        GROUP BY period_key
        ORDER BY period_key DESC
        """,
        params,
    ).fetchall()
    conn.close()
    return rows


def get_profit_detail(period_key, period="day"):
    """특정 기간(예: '2026-07-30', '2026-07', '2026')의 주문 상세 + 이익 내역"""
    n = _PERIOD_LEN.get(period, 10)
    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT orders.*, channels.name as channel_name,
               products.name as matched_product_name, products.cost_price as cost_price,
               (orders.total_amount - orders.fee_amount
                - COALESCE(products.cost_price, 0) * orders.qty
                + COALESCE(orders.shipping_net, 0)) as profit
        FROM orders
        LEFT JOIN channels ON orders.channel_id = channels.id
        LEFT JOIN products ON orders.matched_product_id = products.id
        WHERE substr(orders.order_date, 1, {n}) = ?
        ORDER BY orders.order_date DESC
        """,
        (period_key,),
    ).fetchall()
    conn.close()
    return rows


def get_product_profit_summary():
    """품목별: 판매수량/매출/수수료/원가합계/수익 - 품목관리 탭에서 사용"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT products.id as product_id, products.name as product_name,
               products.cost_price as cost_price,
               COALESCE(SUM(orders.qty), 0) as sold_qty,
               COALESCE(SUM(orders.total_amount), 0) as total_sales,
               COALESCE(SUM(orders.fee_amount), 0) as total_fee,
               COALESCE(SUM(products.cost_price * orders.qty), 0) as total_cost,
               COALESCE(SUM(orders.total_amount - orders.fee_amount
                            - products.cost_price * orders.qty), 0) as profit
        FROM products
        LEFT JOIN orders ON orders.matched_product_id = products.id
        GROUP BY products.id
        """
    ).fetchall()
    conn.close()
    return {r["product_id"]: r for r in rows}


def get_channel_profit_summary(date_from=None, date_to=None):
    """채널별: 주문건수/매출/수수료/원가/이익/수익률(%) - 리포트 '채널별 비교'에서 사용"""
    conditions = []
    params = []
    if date_from:
        conditions.append("substr(orders.order_date, 1, 10) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("substr(orders.order_date, 1, 10) <= ?")
        params.append(date_to)
    date_filter = ("AND " + " AND ".join(conditions)) if conditions else ""

    query = f"""
        SELECT channels.id as channel_id, channels.name as channel_name,
               COUNT(orders.id) as order_count,
               COALESCE(SUM(orders.total_amount), 0) as total_sales,
               COALESCE(SUM(orders.fee_amount), 0) as total_fee,
               COALESCE(SUM(COALESCE(products.cost_price, 0) * orders.qty), 0) as total_cost,
               COALESCE(SUM(orders.shipping_fee), 0) as shipping_total,
               COALESCE(SUM(orders.shipping_fee_charge), 0) as shipping_charge,
               COALESCE(SUM(orders.shipping_net), 0) as shipping_net,
               COALESCE(SUM(orders.total_amount - orders.fee_amount
                            - COALESCE(products.cost_price, 0) * orders.qty), 0)
                   + COALESCE(SUM(orders.shipping_net), 0) as profit
        FROM channels
        LEFT JOIN orders ON orders.channel_id = channels.id {date_filter}
        LEFT JOIN products ON orders.matched_product_id = products.id
        GROUP BY channels.id, channels.name
    """

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        sales = d["total_sales"] or 0
        d["profit_margin"] = round((d["profit"] / sales) * 100, 1) if sales else 0.0
        result.append(d)
    return result


def get_recent_orders(limit=10):
    """대시보드용: 가장 최근 주문 N건"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT orders.*, channels.name as channel_name
        FROM orders
        LEFT JOIN channels ON orders.channel_id = channels.id
        ORDER BY orders.order_date DESC, orders.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def get_daily_sales_trend(days=7):
    """대시보드용: 최근 N일 매출 추이 (오늘 포함)"""
    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT substr(order_date, 1, 10) as d,
               SUM(total_amount) as total_sales,
               SUM(total_amount - fee_amount) as net_sales,
               COUNT(*) as order_count
        FROM orders
        WHERE substr(order_date, 1, 10) >= date('now', '-{int(days) - 1} days')
        GROUP BY d
        ORDER BY d ASC
        """
    ).fetchall()
    conn.close()
    return rows


def get_monthly_trend_by_channel(date_from=None, date_to=None):
    """리포트용: 채널별 월별 매출 추이 (꺾은선 그래프용). date_from/date_to로 기간 제한 가능"""
    conditions = []
    params = []
    if date_from:
        conditions.append("substr(orders.order_date, 1, 10) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("substr(orders.order_date, 1, 10) <= ?")
        params.append(date_to)
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT substr(orders.order_date, 1, 7) as ym,
               channels.name as channel_name,
               SUM(orders.total_amount) as total_sales,
               SUM(orders.total_amount - orders.fee_amount) as net_sales
        FROM orders
        LEFT JOIN channels ON orders.channel_id = channels.id
        {where_clause}
        GROUP BY ym, channels.name
        ORDER BY ym ASC
        """,
        params,
    ).fetchall()
    conn.close()
    return rows


def get_product_ranking(limit=10, date_from=None, date_to=None):
    """리포트용: 매출 상위 품목 순위 (매칭된 주문 기준). date_from/date_to로 기간 제한 가능"""
    conditions = []
    params = []
    if date_from:
        conditions.append("substr(orders.order_date, 1, 10) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("substr(orders.order_date, 1, 10) <= ?")
        params.append(date_to)
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT products.name as product_name, products.option_name as option_name,
               SUM(orders.qty) as sold_qty,
               SUM(orders.total_amount) as total_sales,
               SUM(orders.total_amount - orders.fee_amount
                   - products.cost_price * orders.qty) as profit
        FROM orders
        JOIN products ON orders.matched_product_id = products.id
        {where_clause}
        GROUP BY products.id
        ORDER BY total_sales DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()
    conn.close()
    return rows


def get_product_sales_by_channel(channel_id):
    """특정 채널의 상품별 판매 집계 (대시보드 상세보기용)"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT product_name,
               SUM(qty) as total_qty,
               SUM(total_amount) as total_sales,
               SUM(settlement_amount) as total_settlement,
               COUNT(*) as order_count
        FROM orders
        WHERE channel_id = ?
        GROUP BY product_name
        ORDER BY total_sales DESC
        """,
        (channel_id,),
    ).fetchall()
    conn.close()
    return rows


# ---------------- 거래처(매입처) ----------------
def get_suppliers():
    """channel_type이 '일반업체'인 채널만 거래처(매입처)로 취급"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM channels WHERE channel_type='일반업체' ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


# ---------------- 입고(매입) 관리 ----------------
def add_purchase(purchase_date, supplier_id, product_id, qty, unit_cost, total_amount, paid_amount, memo=""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO purchases
           (purchase_date, supplier_id, product_id, qty, unit_cost, total_amount, paid_amount, memo)
           VALUES (?,?,?,?,?,?,?,?)""",
        (purchase_date, supplier_id, product_id, qty, unit_cost, total_amount, paid_amount, memo),
    )
    conn.commit()
    conn.close()


def update_purchase(purchase_id, purchase_date, supplier_id, product_id, qty, unit_cost,
                     total_amount, paid_amount, memo=""):
    """입고 수정. 품목이 바뀌거나 수량이 바뀌면 재고도 함께 맞춰줌
    (예전엔 재고를 전혀 건드리지 않아서, 수정창에서 품목을 연결해도 입출고
     내역에는 나타나는데 정작 재고는 안 늘어나는 문제가 있었음)"""
    conn = get_connection()
    old = conn.execute("SELECT product_id, qty FROM purchases WHERE id=?", (purchase_id,)).fetchone()

    # 이전 품목에서 예전 수량만큼 되돌리고, 새 품목에 새 수량만큼 반영
    if old and old["product_id"]:
        conn.execute("UPDATE products SET stock_qty = COALESCE(stock_qty,0) - ? WHERE id=?",
                     (old["qty"] or 0, old["product_id"]))
    if product_id:
        conn.execute("UPDATE products SET stock_qty = COALESCE(stock_qty,0) + ? WHERE id=?",
                     (qty or 0, product_id))

    conn.execute(
        """UPDATE purchases SET
             purchase_date=?, supplier_id=?, product_id=?, qty=?, unit_cost=?,
             total_amount=?, paid_amount=?, memo=?
           WHERE id=?""",
        (purchase_date, supplier_id, product_id, qty, unit_cost, total_amount, paid_amount, memo, purchase_id),
    )
    conn.commit()
    conn.close()


def delete_purchase(purchase_id):
    """입고 삭제. 그 입고로 늘어났던 재고도 함께 되돌림"""
    conn = get_connection()
    old = conn.execute("SELECT product_id, qty FROM purchases WHERE id=?", (purchase_id,)).fetchone()
    if old and old["product_id"]:
        conn.execute("UPDATE products SET stock_qty = COALESCE(stock_qty,0) - ? WHERE id=?",
                     (old["qty"] or 0, old["product_id"]))
    conn.execute("DELETE FROM purchases WHERE id=?", (purchase_id,))
    conn.commit()
    conn.close()


def get_purchase_by_id(purchase_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT purchases.*, channels.name as supplier_name, products.name as product_name,
               products.option_name as option_name
        FROM purchases
        LEFT JOIN channels ON purchases.supplier_id = channels.id
        LEFT JOIN products ON purchases.product_id = products.id
        WHERE purchases.id=?
        """,
        (purchase_id,),
    ).fetchone()
    conn.close()
    return row


def get_purchases(supplier_id=None, date_from=None, date_to=None):
    conn = get_connection()
    query = """
        SELECT purchases.*, channels.name as supplier_name, products.name as product_name,
               products.option_name as option_name
        FROM purchases
        LEFT JOIN channels ON purchases.supplier_id = channels.id
        LEFT JOIN products ON purchases.product_id = products.id
        WHERE 1=1
    """
    params = []
    if supplier_id:
        query += " AND purchases.supplier_id = ?"
        params.append(supplier_id)
    if date_from:
        query += " AND substr(purchases.purchase_date, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(purchases.purchase_date, 1, 10) <= ?"
        params.append(date_to)
    query += " ORDER BY purchases.purchase_date DESC, purchases.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


# ---------------- 정산 현황 (판매채널 미정산 / 매입거래처 미결제) ----------------
def get_channel_unsettled_summary():
    """채널별(온라인 마켓 + 일반거래처 매출 모두 포함): 매출액 합계 - 실제 입금액 합계 = 미수금.
    매출액은 주문의 실제 매출금액(total_amount) + 배송비로 계산함.
    (수량×판매단가로 계산하면 마켓 파일의 판매단가가 이미 옵션가가 반영된
     금액이라 매출이 실제보다 크게 잡히는 문제가 있었음.
     total_amount가 비어있는 옛 주문만 수량×단가로 대신 계산)"""
    conn = get_connection()
    order_rows = conn.execute(
        """
        SELECT channels.id as channel_id, channels.name as channel_name,
               COALESCE(SUM(
                   CASE WHEN COALESCE(orders.total_amount,0) > 0 THEN orders.total_amount
                        ELSE COALESCE(orders.qty,0) * COALESCE(orders.sale_price,0) END
                   + COALESCE(orders.shipping_fee,0)), 0) as total_expected,
               COUNT(orders.id) as order_count
        FROM channels
        LEFT JOIN orders ON orders.channel_id = channels.id
             AND COALESCE(orders.status,'') NOT IN ('반품', '취소')
        GROUP BY channels.id, channels.name
        """
    ).fetchall()
    settle_rows = conn.execute(
        "SELECT channel_id, COALESCE(SUM(amount),0) as total_received FROM settlements GROUP BY channel_id"
    ).fetchall()
    conn.close()

    received_map = {r["channel_id"]: r["total_received"] for r in settle_rows}
    result = []
    for r in order_rows:
        d = dict(r)
        d["total_received"] = received_map.get(d["channel_id"], 0)
        d["unsettled"] = d["total_expected"] - d["total_received"]
        result.append(d)
    return result


def get_supplier_unpaid_summary():
    """매입거래처별: 총 매입금액 - 총 지급액 = 미결제금액"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT channels.id as supplier_id, channels.name as supplier_name,
               COALESCE(SUM(purchases.total_amount), 0) as total_purchase,
               COALESCE(SUM(purchases.paid_amount), 0) as total_paid,
               COUNT(purchases.id) as purchase_count
        FROM channels
        LEFT JOIN purchases ON purchases.supplier_id = channels.id
        WHERE channels.channel_type = '일반업체'
        GROUP BY channels.id, channels.name
        """
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["unpaid"] = d["total_purchase"] - d["total_paid"]
        result.append(d)
    return result


def bulk_update_order_channel(order_ids, channel_id):
    """선택한 주문들의 채널을 일괄 변경 (잘못 업로드된 채널 수정용)"""
    conn = get_connection()
    conn.executemany(
        "UPDATE orders SET channel_id=? WHERE id=?",
        [(channel_id, oid) for oid in order_ids],
    )
    conn.commit()
    conn.close()


# ---------------- 기존 데이터의 날짜 형식 정리 (마켓마다 표기가 달라 통일 필요) ----------------
_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y.%m.%d %H:%M:%S",
    "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y.%m.%d %H:%M",
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
]


def _normalize_date_string(raw):
    if not raw:
        return raw
    s = str(raw).strip()
    if not s:
        return raw
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if ":" in s:
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d")
    return raw  # 알 수 없는 형식은 원본 유지 (데이터 손실 방지)


def normalize_existing_order_dates():
    """이미 저장된 주문의 order_date를 통일된 형식으로 정리 (마켓마다 표기가 달라
    리포트에서 날짜 정렬/표기가 어긋나던 문제 해결). 프로그램 시작 시 자동 실행됨."""
    conn = get_connection()
    rows = conn.execute("SELECT id, order_date FROM orders").fetchall()
    updates = []
    for r in rows:
        new_val = _normalize_date_string(r["order_date"])
        if new_val != r["order_date"]:
            updates.append((new_val, r["id"]))
    if updates:
        conn.executemany("UPDATE orders SET order_date=? WHERE id=?", updates)
        conn.commit()
    conn.close()
    return len(updates)


# ---------------- 재고 조정 (품목관리 - 재고관리) ----------------
def add_stock_adjustment(product_id, adjust_date, change_qty, reason, memo=""):
    """재고를 +/-로 조정하고 이력을 남김. change_qty는 양수(증가)/음수(감소) 모두 가능."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO stock_adjustments (product_id, adjust_date, change_qty, reason, memo) VALUES (?,?,?,?,?)",
        (product_id, adjust_date, change_qty, reason, memo),
    )
    conn.execute(
        "UPDATE products SET stock_qty = COALESCE(stock_qty, 0) + ? WHERE id=?",
        (change_qty, product_id),
    )
    conn.commit()
    conn.close()


def get_stock_adjustments(product_id=None, limit=50):
    conn = get_connection()
    query = """
        SELECT stock_adjustments.*, products.name as product_name,
               products.option_name as option_name
        FROM stock_adjustments
        LEFT JOIN products ON stock_adjustments.product_id = products.id
        WHERE 1=1
    """
    params = []
    if product_id:
        query += " AND stock_adjustments.product_id = ?"
        params.append(product_id)
    query += " ORDER BY stock_adjustments.id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


# ---------------- 지출 항목(카테고리) 관리 ----------------
DEFAULT_EXPENSE_CATEGORIES = (
    ["포장비", "배송비", "사입/원가", "수수료", "기타"]
    + [f"광고비-{name}" for name in DEFAULT_CHANNELS if name != "기타"]
)


def get_expense_categories():
    conn = get_connection()
    rows = conn.execute("SELECT name FROM expense_categories ORDER BY id").fetchall()
    conn.close()
    return [r["name"] for r in rows]


def add_expense_category(name):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO expense_categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def delete_expense_category(name):
    conn = get_connection()
    conn.execute("DELETE FROM expense_categories WHERE name=?", (name,))
    conn.commit()
    conn.close()


# ---------------- 정산 매칭 (정산내역 파일 업로드로 주문의 정산완료 여부 표시) ----------------
def get_order_by_order_no(order_no):
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    conn.close()
    return row


def get_unsettled_orders_for_matching(channel_id=None):
    """정산파일 매칭용: 아직 정산 안 된 주문의 주문번호/구매자명/상품명만 가볍게 조회"""
    conn = get_connection()
    query = "SELECT id, order_no, buyer_name, product_name, channel_id, settlement_amount FROM orders WHERE is_settled=0"
    params = []
    if channel_id:
        query += " AND channel_id=?"
        params.append(channel_id)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def mark_orders_settled(matches):
    """matches: [(order_id, settled_amount, settled_date), ...]"""
    if not matches:
        return
    conn = get_connection()
    conn.executemany(
        "UPDATE orders SET is_settled=1, settled_amount=?, settled_date=? WHERE id=?",
        [(amt, date, oid) for oid, amt, date in matches],
    )
    conn.commit()
    conn.close()


def get_settlement_status_counts(channel_id=None):
    """채널별 정산완료/미정산 건수 요약"""
    conn = get_connection()
    query = """
        SELECT channels.id as channel_id, channels.name as channel_name,
               SUM(CASE WHEN orders.id IS NOT NULL AND orders.is_settled=1 THEN 1 ELSE 0 END) as settled_count,
               SUM(CASE WHEN orders.id IS NOT NULL AND (orders.is_settled=0 OR orders.is_settled IS NULL) THEN 1 ELSE 0 END) as unsettled_count,
               SUM(CASE WHEN orders.id IS NOT NULL AND orders.is_settled=1 THEN orders.settled_amount ELSE 0 END) as settled_amount_total,
               SUM(CASE WHEN orders.id IS NOT NULL AND (orders.is_settled=0 OR orders.is_settled IS NULL) THEN orders.settlement_amount ELSE 0 END) as unsettled_amount_total
        FROM channels
        LEFT JOIN orders ON orders.channel_id = channels.id
        WHERE COALESCE(channels.channel_type, '온라인채널') = '온라인채널'
    """
    params = []
    if channel_id:
        query += " AND channels.id=?"
        params.append(channel_id)
    query += " GROUP BY channels.id, channels.name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_stock_status():
    """리포트 '재고 현황' 탭용: 품목별 재고수량/재고금액(원가×수량) 등"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, sku, name, option_name, cost_price, sale_price, stock_qty,
               COALESCE(cost_price, 0) * COALESCE(stock_qty, 0) as stock_value
        FROM products
        ORDER BY stock_value DESC
        """
    ).fetchall()
    conn.close()
    return rows


def get_ledger_entries(channel_id, date_from=None, date_to=None):
    """거래원장 출력용: 특정 거래처(채널)의 모든 거래내역(매출 + 입금)을 원장 라인
    형식으로 반환. 주문 1건당 품목 라인 + (배송비가 있으면) 배송비 라인을 별도 행으로,
    그리고 받은 입금(정산)도 별도 행으로 나눠서 반환.
    각 행: {"date":.., "kind":.., "product":.., "qty":.., "unit_price":.., "amount":.., "buyer":.., "memo":..}
    amount는 매출이면 양수(받을 돈), 입금이면 음수(받은 돈)로 표기됨"""
    orders = [o for o in get_orders(channel_id=channel_id, date_from=date_from, date_to=date_to)
              if (o["status"] or "") not in ("반품", "취소")]
    entries = []
    for o in orders:
        # 품목란에는 옵션만 표시 (옵션이 없으면 상품명으로 대체)
        product_label = o["option_name"] or o["product_name"] or ""
        entries.append({
            "date": o["order_date"],
            "kind": "매출",
            "product": product_label,
            "qty": o["qty"] or 0,
            "unit_price": o["sale_price"] or 0,
            # 마켓 파일의 실제 매출금액을 우선 사용 (없으면 수량×단가)
            "amount": (o["total_amount"] or 0) or ((o["qty"] or 0) * (o["sale_price"] or 0)),
            "buyer": o["buyer_name"] or "",
            "memo": o["order_no"] or "",
            "settled": "✅ 정산완료" if o["is_settled"] else "미정산",
        })
        if o["shipping_fee"]:
            entries.append({
                "date": o["order_date"],
                "kind": "매출",
                "product": "배송비",
                "qty": 1,
                "unit_price": o["shipping_fee"],
                "amount": o["shipping_fee"],
                "buyer": o["buyer_name"] or "",
                "memo": o["order_no"] or "",
                "settled": "✅ 정산완료" if o["is_settled"] else "미정산",
            })

    # 받은 입금(정산) 내역도 함께 표시 - 매출만 나오고 입금이 안 보이던 문제 해결
    conn = get_connection()
    # 통장 입금이면 어느 은행인지도 함께 표시하기 위해 bank_accounts를 조인
    query = """SELECT settlements.*, bank_accounts.bank_name as bank_name,
                      bank_accounts.name as bank_alias
               FROM settlements
               LEFT JOIN bank_accounts ON settlements.bank_account_id = bank_accounts.id
               WHERE settlements.channel_id=?"""
    params = [channel_id]
    if date_from:
        query += " AND substr(settlements.settle_date, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(settlements.settle_date, 1, 10) <= ?"
        params.append(date_to)
    settle_rows = conn.execute(query, params).fetchall()
    conn.close()
    for s in settle_rows:
        method = s["payment_method"] or "현금"
        if method == "통장":
            bank_label = s["bank_name"] or s["bank_alias"] or "통장"
            label = f"입금 ({bank_label})"
        else:
            label = "입금 (현금)"
        entries.append({
            "date": s["settle_date"],
            "kind": "입금",
            "product": label,
            "qty": 1,
            "unit_price": s["amount"] or 0,
            "amount": -(s["amount"] or 0),  # 받은 돈이므로 미수금을 줄이는 방향(음수)
            "buyer": "",
            "memo": s["memo"] or "",
            "settled": "입금됨",
        })

    # 날짜순 정렬 (오래된 순 - 원장은 보통 시간순으로 봄)
    entries.sort(key=lambda e: e["date"] or "")

    # 조회 시작일 이전까지의 잔액(이월금)을 먼저 구해서 거기서부터 누적함.
    # 이걸 안 하면 8월 매출이 9월에 입금됐을 때 9월만 조회하면
    # 입금만 잡혀서 미수금이 마이너스로 나옴
    opening = get_channel_opening_balance(channel_id, date_from) if date_from else 0
    if opening:
        entries.insert(0, {
            "date": date_from,
            "kind": "이월",
            "product": "전기이월 (조회 시작일 이전 잔액)",
            "qty": 0,
            "unit_price": 0,
            "amount": 0,          # 매출/입금 합계에는 넣지 않음
            "buyer": "",
            "memo": "",
            "settled": "",
            "balance": opening,
            "is_opening": True,
        })

    running = opening
    for e in entries:
        if e.get("is_opening"):
            continue
        running += e["amount"]
        e["balance"] = running
    return entries


def get_channel_opening_balance(channel_id, date_from):
    """조회 시작일 '이전'까지의 미수금 잔액(이월금).
    = 그 전까지의 매출(배송비 포함) − 그 전까지 받은 입금"""
    if not date_from:
        return 0
    conn = get_connection()
    try:
        r = conn.execute("""
            SELECT COALESCE(SUM(
                       CASE WHEN COALESCE(total_amount,0) <> 0 THEN total_amount
                            ELSE COALESCE(qty,0) * COALESCE(sale_price,0) END
                       + COALESCE(shipping_fee,0)), 0) as sales
            FROM orders
            WHERE channel_id = ?
              AND substr(COALESCE(order_date,''),1,10) < ?
              AND COALESCE(status,'') NOT IN ('반품','취소')
        """, (channel_id, date_from)).fetchone()
        sales = r["sales"] or 0
        r2 = conn.execute("""
            SELECT COALESCE(SUM(amount),0) as paid FROM settlements
            WHERE channel_id = ? AND substr(COALESCE(settle_date,''),1,10) < ?
        """, (channel_id, date_from)).fetchone()
        paid = r2["paid"] or 0
    except sqlite3.Error:
        sales, paid = 0, 0
    conn.close()
    return sales - paid


def update_channel_details(channel_id, name, business_number="", contact="", manager="", memo=""):
    """거래처(채널)의 상세정보를 전부 수정 (이름 포함)"""
    conn = get_connection()
    conn.execute(
        """UPDATE channels SET name=?, business_number=?, contact=?, manager=?, memo=?
           WHERE id=?""",
        (name, business_number, contact, manager, memo, channel_id),
    )
    conn.commit()
    conn.close()


# ---------------- 옵션명 프리셋 (주문관리 수동입력 - 옵션 선택/등록용) ----------------
def get_option_presets():
    conn = get_connection()
    rows = conn.execute("SELECT label FROM option_presets ORDER BY id DESC").fetchall()
    conn.close()
    return [r["label"] for r in rows]


def add_option_preset(label):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO option_presets (label) VALUES (?)", (label,))
    conn.commit()
    conn.close()


def get_distinct_order_options(limit=200):
    """기존 주문들에서 실제로 쓰인 옵션명(중복제거) - 옵션 선택 목록 보강용"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT DISTINCT option_name FROM orders
           WHERE option_name IS NOT NULL AND option_name != ''
           ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [r["option_name"] for r in rows]


def get_monthly_expense_totals(date_from=None, date_to=None):
    conn = get_connection()
    query = "SELECT substr(date, 1, 7) as ym, SUM(amount) as total_expense FROM expenses WHERE 1=1"
    params = []
    if date_from:
        query += " AND substr(date, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(date, 1, 10) <= ?"
        params.append(date_to)
    query += " GROUP BY ym"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {r["ym"]: (r["total_expense"] or 0) for r in rows}


def get_monthly_settlement(date_from=None, date_to=None):
    """리포트 '월별결산' 탭용: 월별 매출/원가/영업이익(매출-수수료-원가)/지출/순이익(영업이익-지출).
    date_from/date_to로 조회 기간을 제한할 수 있음"""
    profit_rows = get_profit_by_period("month", date_from=date_from, date_to=date_to)
    expense_map = get_monthly_expense_totals(date_from=date_from, date_to=date_to)
    profit_map = {r["period_key"]: r for r in profit_rows}

    all_yms = sorted(set(profit_map.keys()) | set(expense_map.keys()), reverse=True)
    result = []
    for ym in all_yms:
        p = profit_map.get(ym)
        sales = p["total_sales"] if p else 0
        fee = p["total_fee"] if p else 0
        cost = p["total_cost"] if p else 0
        gross_profit = p["profit"] if p else 0
        expense = expense_map.get(ym, 0)
        net_profit = gross_profit - expense
        result.append({
            "ym": ym, "sales": sales or 0, "fee": fee or 0, "cost": cost or 0,
            "gross_profit": gross_profit or 0, "expense": expense, "net_profit": net_profit,
        })
    return result


# ---------------- 통장(은행계좌) 관리 ----------------
def get_bank_accounts():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM bank_accounts ORDER BY id").fetchall()
    conn.close()
    return rows


def add_bank_account(name, bank_name="", account_number="", balance=0, memo=""):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO bank_accounts (name, bank_name, account_number, balance, memo) VALUES (?,?,?,?,?)",
        (name, bank_name, account_number, balance, memo),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_bank_account(account_id, name, bank_name="", account_number="", balance=0, memo=""):
    conn = get_connection()
    conn.execute(
        "UPDATE bank_accounts SET name=?, bank_name=?, account_number=?, balance=?, memo=? WHERE id=?",
        (name, bank_name, account_number, balance, memo, account_id),
    )
    conn.commit()
    conn.close()


def delete_bank_account(account_id):
    conn = get_connection()
    conn.execute("UPDATE expenses SET bank_account_id=NULL WHERE bank_account_id=?", (account_id,))
    conn.execute("UPDATE purchase_payments SET bank_account_id=NULL WHERE bank_account_id=?", (account_id,))
    conn.execute("DELETE FROM bank_accounts WHERE id=?", (account_id,))
    conn.commit()
    conn.close()


def adjust_bank_balance(account_id, delta):
    if not account_id:
        return
    conn = get_connection()
    conn.execute("UPDATE bank_accounts SET balance = COALESCE(balance,0) + ? WHERE id=?", (delta, account_id))
    conn.commit()
    conn.close()


# ---------------- 매입 지출(거래처에 대금 지급) ----------------
def add_purchase_payment(supplier_id, payment_date, amount, bank_account_id=None, memo="",
                          payment_method="통장", card_id=None,
                          supply_amount=0, discount_rate=0, discount_amount=0):
    """거래처에 매입대금을 지급 - 기록을 남기고, 통장 잔액을 차감하고,
    그 거래처의 미결제 입고건에 오래된 순서대로 자동 충당(paid_amount 증가)"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO purchase_payments
             (supplier_id, payment_date, amount, bank_account_id, memo, payment_method, card_id,
              supply_amount, discount_rate, discount_amount)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (supplier_id, payment_date, amount, bank_account_id, memo, payment_method, card_id,
         supply_amount, discount_rate, discount_amount),
    )
    conn.commit()

    if payment_method == "통장" and bank_account_id:
        conn.execute("UPDATE bank_accounts SET balance = COALESCE(balance,0) - ? WHERE id=?", (amount, bank_account_id))
        conn.commit()

    # 미결제 입고건에 오래된 순서대로 충당
    # 할인을 받은 경우, 실제 송금액(amount)이 아니라 할인 전 공급가액만큼 채무가 없어짐
    remaining = supply_amount if supply_amount else amount
    unpaid_purchases = conn.execute(
        """SELECT id, total_amount, paid_amount FROM purchases
           WHERE supplier_id=? AND COALESCE(paid_amount,0) < COALESCE(total_amount,0)
           ORDER BY purchase_date ASC, id ASC""",
        (supplier_id,),
    ).fetchall()
    for p in unpaid_purchases:
        if remaining <= 0:
            break
        outstanding = (p["total_amount"] or 0) - (p["paid_amount"] or 0)
        pay_now = min(outstanding, remaining)
        conn.execute("UPDATE purchases SET paid_amount = COALESCE(paid_amount,0) + ? WHERE id=?", (pay_now, p["id"]))
        remaining -= pay_now
    conn.commit()
    conn.close()


def get_purchase_payments(supplier_id=None, year_month=None):
    conn = get_connection()
    query = """
        SELECT purchase_payments.*, channels.name as supplier_name,
               COALESCE(bank_accounts.bank_name, bank_accounts.name) as bank_account_name,
               cards.name as card_name
        FROM purchase_payments
        LEFT JOIN cards ON purchase_payments.card_id = cards.id
        LEFT JOIN channels ON purchase_payments.supplier_id = channels.id
        LEFT JOIN bank_accounts ON purchase_payments.bank_account_id = bank_accounts.id
        WHERE 1=1
    """
    params = []
    if supplier_id:
        query += " AND purchase_payments.supplier_id=?"
        params.append(supplier_id)
    if year_month:
        query += " AND substr(purchase_payments.payment_date, 1, 7) = ?"
        params.append(year_month)
    query += " ORDER BY purchase_payments.payment_date DESC, purchase_payments.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def delete_purchase_payment(payment_id):
    """매입지출 삭제 - 통장 잔액을 되돌리고(복원) 기록을 삭제.
    (이미 여러 입고건에 나눠 충당된 paid_amount는 되돌리지 않음 - 복잡도상 수동조정 권장)"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM purchase_payments WHERE id=?", (payment_id,)).fetchone()
    if row:
        if row["bank_account_id"]:
            conn.execute("UPDATE bank_accounts SET balance = COALESCE(balance,0) + ? WHERE id=?",
                         (row["amount"], row["bank_account_id"]))
        conn.execute("DELETE FROM purchase_payments WHERE id=?", (payment_id,))
        conn.commit()
    conn.close()


def get_last_purchase_price(supplier_id, product_id):
    """해당 거래처+품목 조합의 가장 최근 입고 단가를 반환 (없으면 None)"""
    if not supplier_id or not product_id:
        return None
    conn = get_connection()
    row = conn.execute(
        """SELECT unit_cost FROM purchases
           WHERE supplier_id=? AND product_id=?
           ORDER BY purchase_date DESC, id DESC LIMIT 1""",
        (supplier_id, product_id),
    ).fetchone()
    conn.close()
    return row["unit_cost"] if row else None


DEFAULT_DB_PATH = DB_PATH


def set_db_path(path):
    """데이터 파일(ledger.db) 위치를 바꿈. 앱 시작 시 저장된 경로로 지정하는 용도.
    지정한 위치를 실제로 열 수 없으면(폴더 없음/USB 빠짐/권한 없음 등)
    프로그램이 아예 안 켜지는 일이 없도록 기본 위치로 되돌림."""
    global DB_PATH
    if not path:
        DB_PATH = DEFAULT_DB_PATH
        return DB_PATH
    if can_use_db_path(path):
        DB_PATH = path
    else:
        DB_PATH = DEFAULT_DB_PATH   # 열 수 없으면 안전하게 기본 위치 사용
    return DB_PATH


def is_db_corrupted(path=None):
    """데이터 파일이 손상됐는지 확인 (malformed / not a database 등)"""
    target = path or DB_PATH
    if not os.path.exists(target):
        return False
    try:
        conn = sqlite3.connect(target, timeout=5.0)
        try:
            conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
            row = conn.execute("PRAGMA quick_check").fetchone()
            return bool(row) and row[0] != "ok"
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return True
    except Exception:
        return False


def find_latest_backup():
    """backups 폴더에서 가장 최근의 정상 백업 파일을 찾음"""
    import glob
    folder = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "backups")
    if not os.path.isdir(folder):
        return None
    for path in sorted(glob.glob(os.path.join(folder, "ledger_*.db")), reverse=True):
        if not is_db_corrupted(path):
            return path
    return None


def recover_corrupted_db():
    """손상된 데이터 파일을 복구.
    1) 최근 정상 백업이 있으면 그것으로 되돌림
    2) 없으면 손상 파일을 따로 보관하고 새 DB로 시작
    반환: (방식, 설명문구)"""
    import shutil
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    broken = f"{DB_PATH}.broken_{stamp}"
    try:
        shutil.move(DB_PATH, broken)
    except Exception:
        try:
            os.remove(DB_PATH)
        except Exception:
            pass
        broken = None
    # WAL 잔여 파일도 정리 (손상 원인이 되기도 함)
    for suffix in ("-wal", "-shm"):
        try:
            os.remove(DB_PATH + suffix)
        except OSError:
            pass

    backup = find_latest_backup()
    if backup:
        try:
            shutil.copy2(backup, DB_PATH)
            return "backup", f"최근 백업({os.path.basename(backup)})으로 되돌렸습니다."
        except Exception:
            pass
    return "new", "복구할 백업이 없어 새 데이터 파일로 시작합니다."


def can_use_db_path(path):
    """그 위치에 데이터 파일을 실제로 열고 쓸 수 있는지 확인.
    (SELECT 1 같은 건 파일을 건드리지 않아 검사가 안 되므로, 실제로 파일에
     접근하는 구문으로 확인해야 함)"""
    try:
        folder = os.path.dirname(os.path.abspath(path))
        if folder:
            os.makedirs(folder, exist_ok=True)
        conn = sqlite3.connect(path, timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("SELECT COUNT(*) FROM sqlite_master")   # 파일을 실제로 읽음
            conn.execute("CREATE TABLE IF NOT EXISTS _write_test (x INTEGER)")  # 쓰기 확인
            conn.execute("DROP TABLE IF EXISTS _write_test")
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        return False


def find_usable_db_path():
    """지금 위치를 쓸 수 없을 때, 쓸 수 있는 다른 위치를 찾아줌
    (내 문서 폴더 -> 홈 폴더 순으로 시도)"""
    candidates = [DB_PATH, DEFAULT_DB_PATH]
    home = os.path.expanduser("~")
    candidates.append(os.path.join(home, "Documents", "에누리하우스", "ledger.db"))
    candidates.append(os.path.join(home, "에누리하우스", "ledger.db"))
    for p in candidates:
        if p and can_use_db_path(p):
            return p
    return None


def get_db_path():
    return DB_PATH


def export_selective_backup(dest_path, exclude_tables=None):
    """DB 파일 전체를 복사한 뒤, 제외하기로 선택한 테이블의 데이터만 비움.
    (품목/채널·거래처/설정값(카테고리·프리셋·통장)은 항상 포함되고,
    exclude_tables로 지정한 거래 데이터만 선택적으로 빠짐)"""
    import shutil
    shutil.copy2(DB_PATH, dest_path)
    if not exclude_tables:
        return
    conn = sqlite3.connect(dest_path)
    # 복사본에서만 지우는 것이라 외래키 제약은 끄고 진행 (자식→부모 순서 신경 안 쓰도록)
    conn.execute("PRAGMA foreign_keys = OFF")
    for t in exclude_tables:
        try:
            conn.execute(f"DELETE FROM {t}")
        except sqlite3.Error:
            pass  # 그 테이블이 없는 옛 백업 구조여도 나머지는 계속 진행
    conn.commit()
    conn.close()


def get_bank_transactions(limit=100, bank_account_id=None, date_from=None, date_to=None):
    """통장 관련 거래내역(입금/출금)을 통합 조회 - 리포트 통장현황용.
    bank_account_id를 지정하면 그 통장의 내역만,
    date_from/date_to를 주면 그 기간의 내역만 반환"""
    conn = get_connection()
    bank_filter = "AND bank_account_id = ?" if bank_account_id else ""
    transfer_from_filter = "AND from_bank_id = ?" if bank_account_id else ""
    transfer_to_filter = "AND to_bank_id = ?" if bank_account_id else ""
    params = [bank_account_id] * 5 if bank_account_id else []
    rows = conn.execute(
        f"""
        SELECT payment_date as date, '출금(매입지출)' as kind, -amount as amount,
               bank_account_id, memo, supplier_id as ref_name_id, 'supplier' as ref_type,
               '' as category
        FROM purchase_payments WHERE bank_account_id IS NOT NULL
              AND COALESCE(payment_method,'통장')='통장' {bank_filter}
        UNION ALL
        SELECT date as date, '출금(지출)' as kind, -amount as amount,
               bank_account_id, memo, NULL as ref_name_id, 'none' as ref_type,
               category as category
        FROM expenses WHERE bank_account_id IS NOT NULL
              AND COALESCE(payment_method,'통장')='통장' {bank_filter}
        UNION ALL
        SELECT settle_date as date, '입금(정산)' as kind, amount as amount,
               bank_account_id, memo, channel_id as ref_name_id, 'channel' as ref_type,
               '' as category
        FROM settlements WHERE bank_account_id IS NOT NULL AND payment_method='통장' {bank_filter}
        UNION ALL
        SELECT transfer_date as date, '출금(이체)' as kind, -(amount + COALESCE(fee,0)) as amount,
               from_bank_id as bank_account_id, memo, to_bank_id as ref_name_id, 'bank' as ref_type,
               '' as category
        FROM bank_transfers WHERE from_bank_id IS NOT NULL {transfer_from_filter}
        UNION ALL
        SELECT transfer_date as date, '입금(이체)' as kind, amount as amount,
               to_bank_id as bank_account_id, memo, from_bank_id as ref_name_id, 'bank' as ref_type,
               '' as category
        FROM bank_transfers WHERE to_bank_id IS NOT NULL {transfer_to_filter}
        ORDER BY date DESC
        """,
        params,
    ).fetchall()
    conn.close()

    # 기간으로 걸러낸 뒤 개수를 제한 (합쳐진 결과라 SQL에서 한 번에 자르면 누락될 수 있음)
    if date_from or date_to:
        filtered = []
        for r in rows:
            d10 = (r["date"] or "")[:10]
            if date_from and d10 < date_from:
                continue
            if date_to and d10 > date_to:
                continue
            filtered.append(r)
        rows = filtered
    rows = rows[:limit]

    # 통장 별칭이 겹칠 때 구분되도록 은행명을 우선 표시
    bank_map = {a["id"]: ((a["bank_name"] or "").strip() or a["name"])
                for a in get_bank_accounts()}
    channel_map = {c["id"]: c["name"] for c in get_channels()}
    result = []
    for r in rows:
        d = dict(r)
        d["bank_account_name"] = bank_map.get(d["bank_account_id"], "")
        if d["ref_type"] == "channel":
            d["ref_name"] = channel_map.get(d["ref_name_id"], "")
        elif d["ref_type"] == "supplier":
            d["ref_name"] = channel_map.get(d["ref_name_id"], "")
        elif d["ref_type"] == "bank":
            # 이체는 상대 통장 이름을 보여줌
            d["ref_name"] = bank_map.get(d["ref_name_id"], "")
        else:
            d["ref_name"] = ""
        result.append(d)
    return result


def _adjust_stock_for_product(conn, product_id, qty_delta):
    """품목 재고를 qty_delta만큼 조정. 조합(세트) 품목이면 자기 재고 대신
    구성품 재고를 각각 조정함.
    예) '컴팩트릴 20M(가이드)' 1개 판매 -> 컴팩트릴 20M 1개, 가이드 1개 차감"""
    if not product_id or not qty_delta:
        return
    components = conn.execute(
        "SELECT component_product_id, qty FROM product_bundles WHERE bundle_product_id=?",
        (product_id,)).fetchall()
    if components:
        for comp in components:
            conn.execute(
                "UPDATE products SET stock_qty = COALESCE(stock_qty,0) + ? WHERE id=?",
                (qty_delta * (comp["qty"] or 1), comp["component_product_id"]))
    else:
        conn.execute("UPDATE products SET stock_qty = COALESCE(stock_qty,0) + ? WHERE id=?",
                     (qty_delta, product_id))


def sync_stock_for_order(order_id):
    """주문 1건의 재고 반영 상태를 현재 matched_product_id/qty에 맞게 동기화.
    이미 반영된 만큼(stock_deducted_qty/stock_deducted_product_id)과 비교해서
    차이만큼만 재고를 조정하므로, 여러 번 반복 호출해도(예: rematch가 매번 돌 때)
    중복으로 차감되지 않음. 품목이 바뀌면 이전 품목엔 복원하고 새 품목에서 차감.
    조합(세트) 품목이면 구성품 재고가 대신 차감됨."""
    conn = get_connection()
    order = conn.execute(
        "SELECT qty, matched_product_id, stock_deducted_qty, stock_deducted_product_id FROM orders WHERE id=?",
        (order_id,),
    ).fetchone()
    if not order:
        conn.close()
        return

    old_product_id = order["stock_deducted_product_id"]
    old_qty = order["stock_deducted_qty"] or 0
    new_product_id = order["matched_product_id"]
    new_qty = order["qty"] or 0

    if old_product_id == new_product_id:
        diff = new_qty - old_qty  # 양수: 더 차감, 음수: 되돌림
        if diff:
            _adjust_stock_for_product(conn, new_product_id, -diff)
    else:
        # 이전 품목에는 되돌리고, 새 품목(또는 그 구성품)에서 차감
        _adjust_stock_for_product(conn, old_product_id, old_qty)
        _adjust_stock_for_product(conn, new_product_id, -new_qty)

    conn.execute(
        "UPDATE orders SET stock_deducted_qty=?, stock_deducted_product_id=? WHERE id=?",
        (new_qty if new_product_id else 0, new_product_id, order_id),
    )
    conn.commit()
    conn.close()


def reverse_stock_for_order(order_id):
    """주문을 삭제하기 전에 호출 - 그 주문 때문에 차감됐던 재고를 복원"""
    conn = get_connection()
    order = conn.execute(
        "SELECT stock_deducted_qty, stock_deducted_product_id FROM orders WHERE id=?", (order_id,)
    ).fetchone()
    if order and order["stock_deducted_product_id"] and order["stock_deducted_qty"]:
        _adjust_stock_for_product(conn, order["stock_deducted_product_id"], order["stock_deducted_qty"])
        conn.commit()
    conn.close()


def get_product_stock_history(product_id):
    """품목관리에서 품목 더블클릭 시 보여줄 입출고 내역 - 입고(매입)/판매(주문)/
    재고조정을 하나의 시간순 타임라인으로 합쳐서 반환.
    각 행: {"date":.., "kind":.., "change":.., "related":.., "memo":..}"""
    conn = get_connection()

    purchase_rows = conn.execute(
        """SELECT purchases.purchase_date as d, purchases.qty as qty,
                  channels.name as supplier_name, purchases.memo as memo
           FROM purchases LEFT JOIN channels ON purchases.supplier_id = channels.id
           WHERE purchases.product_id = ?""",
        (product_id,),
    ).fetchall()

    order_rows = conn.execute(
        """SELECT orders.order_date as d, orders.qty as qty, orders.stock_deducted_qty as deducted,
                  channels.name as channel_name, orders.buyer_name as buyer_name, orders.order_no as order_no
           FROM orders LEFT JOIN channels ON orders.channel_id = channels.id
           WHERE orders.matched_product_id = ? AND COALESCE(orders.stock_deducted_qty, 0) > 0""",
        (product_id,),
    ).fetchall()

    adjustment_rows = conn.execute(
        """SELECT adjust_date as d, change_qty, reason, memo FROM stock_adjustments WHERE product_id = ?""",
        (product_id,),
    ).fetchall()
    conn.close()

    history = []
    for p in purchase_rows:
        history.append({
            "date": p["d"], "kind": "📥 입고", "change": p["qty"] or 0,
            "related": p["supplier_name"] or "", "memo": p["memo"] or "",
        })
    for o in order_rows:
        history.append({
            "date": o["d"], "kind": "📤 판매", "change": -(o["deducted"] or 0),
            "related": f"{o['channel_name'] or ''} / {o['buyer_name'] or ''}", "memo": o["order_no"] or "",
        })
    for a in adjustment_rows:
        history.append({
            "date": a["d"], "kind": "🔧 재고조정", "change": a["change_qty"] or 0,
            "related": a["reason"] or "", "memo": a["memo"] or "",
        })

    history.sort(key=lambda h: h["date"] or "", reverse=True)
    return history


def get_channel_profit_for_month(year_month):
    """월별결산에서 특정 월(예: '2026-08')을 더블클릭했을 때 보여줄 채널/거래처별
    이익현황. 매출액/수수료/수수료율/이익금/이익률을 채널별로 집계"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT channels.name as channel_name,
               SUM(orders.total_amount) as total_sales,
               SUM(orders.fee_amount) as total_fee,
               SUM(orders.total_amount - orders.fee_amount
                   - COALESCE(products.cost_price, 0) * orders.qty) as profit
        FROM orders
        LEFT JOIN channels ON orders.channel_id = channels.id
        LEFT JOIN products ON orders.matched_product_id = products.id
        WHERE substr(orders.order_date, 1, 7) = ?
        GROUP BY orders.channel_id
        ORDER BY total_sales DESC
        """,
        (year_month,),
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        sales = r["total_sales"] or 0
        fee = r["total_fee"] or 0
        profit = r["profit"] or 0
        fee_rate = (fee / sales * 100) if sales else 0
        profit_rate = (profit / sales * 100) if sales else 0
        result.append({
            "channel_name": r["channel_name"] or "(채널없음)",
            "total_sales": sales, "total_fee": fee, "fee_rate": fee_rate,
            "profit": profit, "profit_rate": profit_rate,
        })
    return result


def get_last_expense_amount(category):
    """경비 지출 항목(카테고리)을 선택했을 때, 그 항목으로 마지막에 지출했던
    금액을 자동으로 채워주기 위한 조회"""
    conn = get_connection()
    row = conn.execute(
        "SELECT amount FROM expenses WHERE category=? ORDER BY id DESC LIMIT 1",
        (category,),
    ).fetchone()
    conn.close()
    return row["amount"] if row else None


def apply_default_fee_rates():
    """수수료가 비어있는(0원) 주문들 중에서, "설정 > 채널별 수수료율 적용"에
    (해당 채널, 매칭된 품목) 조합의 수수료율이 등록되어 있으면 그 비율로
    수수료를 자동 계산해서 채워줌 (쿠팡처럼 주문파일에 수수료 컬럼이 아예
    없는 마켓 대응용). 정산예정금액도 같이 재계산.
    반환: 적용된 건수"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT orders.id, orders.total_amount, orders.shipping_fee, channel_fee_rates.fee_rate
           FROM orders
           JOIN products ON orders.matched_product_id = products.id
           JOIN channel_fee_rates
             ON channel_fee_rates.channel_id = orders.channel_id
            AND channel_fee_rates.product_name = products.name
           WHERE COALESCE(orders.fee_amount, 0) = 0"""
    ).fetchall()
    count = 0
    for r in rows:
        fee = round((r["total_amount"] or 0) * r["fee_rate"] / 100)
        settlement = (r["total_amount"] or 0) - fee + (r["shipping_fee"] or 0)
        conn.execute(
            "UPDATE orders SET fee_amount=?, settlement_amount=? WHERE id=?",
            (fee, settlement, r["id"]),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


# ---------------- 채널별 수수료율 (설정 > 채널별 수수료율 적용) ----------------
def get_channel_fee_rates():
    conn = get_connection()
    rows = conn.execute(
        """SELECT channel_fee_rates.*, channels.name as channel_name
           FROM channel_fee_rates
           LEFT JOIN channels ON channel_fee_rates.channel_id = channels.id
           ORDER BY channels.name, channel_fee_rates.product_name"""
    ).fetchall()
    conn.close()
    return rows


def set_channel_fee_rate(channel_id, product_name, fee_rate):
    """이미 그 채널+상품명(대분류) 조합이 있으면 수수료율만 갱신, 없으면 새로 등록"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO channel_fee_rates (channel_id, product_name, fee_rate) VALUES (?,?,?)
           ON CONFLICT(channel_id, product_name) DO UPDATE SET fee_rate=excluded.fee_rate""",
        (channel_id, product_name, fee_rate),
    )
    conn.commit()
    conn.close()


def delete_channel_fee_rate(rate_id):
    conn = get_connection()
    conn.execute("DELETE FROM channel_fee_rates WHERE id=?", (rate_id,))
    conn.commit()
    conn.close()


def get_fee_rate_for(channel_id, product_name):
    if not channel_id or not product_name:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT fee_rate FROM channel_fee_rates WHERE channel_id=? AND product_name=?",
        (channel_id, product_name),
    ).fetchone()
    conn.close()
    return row["fee_rate"] if row else None


def recalculate_all_stock():
    """모든 품목의 재고를 실제 기록(입고 - 판매 + 재고조정)으로부터 다시 계산해서 맞춤.
    이전 버전의 버그나 중간에 꼬인 데이터 때문에 재고 숫자가 실제와 안 맞을 때
    복구용으로 사용. 반환: (수정된 품목수, [(품목명, 이전재고, 새재고), ...])"""
    conn = get_connection()
    products = conn.execute("SELECT id, name, option_name, stock_qty FROM products").fetchall()

    purchase_map = {r["product_id"]: r["total"] for r in conn.execute(
        "SELECT product_id, COALESCE(SUM(qty),0) as total FROM purchases "
        "WHERE product_id IS NOT NULL GROUP BY product_id").fetchall()}
    sold_raw = {r["matched_product_id"]: r["total"] for r in conn.execute(
        "SELECT matched_product_id, COALESCE(SUM(qty),0) as total FROM orders "
        "WHERE matched_product_id IS NOT NULL GROUP BY matched_product_id").fetchall()}
    # 조합(세트) 품목의 판매분은 그 구성품의 판매량으로 환산해서 반영
    bundle_rows = conn.execute(
        "SELECT bundle_product_id, component_product_id, qty FROM product_bundles").fetchall()
    bundle_map = {}
    for b in bundle_rows:
        bundle_map.setdefault(b["bundle_product_id"], []).append(
            (b["component_product_id"], b["qty"] or 1))
    sold_map = {}
    for pid, total in sold_raw.items():
        if pid in bundle_map:
            for comp_id, comp_qty in bundle_map[pid]:
                sold_map[comp_id] = sold_map.get(comp_id, 0) + total * comp_qty
        else:
            sold_map[pid] = sold_map.get(pid, 0) + total
    adjust_map = {r["product_id"]: r["total"] for r in conn.execute(
        "SELECT product_id, COALESCE(SUM(change_qty),0) as total FROM stock_adjustments "
        "WHERE product_id IS NOT NULL GROUP BY product_id").fetchall()}

    changes = []
    for p in products:
        pid = p["id"]
        correct = purchase_map.get(pid, 0) - sold_map.get(pid, 0) + adjust_map.get(pid, 0)
        old = p["stock_qty"] or 0
        if correct != old:
            label = f"{p['name']} {p['option_name'] or ''}".strip()
            changes.append((label, old, correct))
            conn.execute("UPDATE products SET stock_qty=? WHERE id=?", (correct, pid))
            # 주문의 재고차감 추적값도 실제 수량과 일치시켜 다음 매칭 때 또 어긋나지 않게 함
            conn.execute(
                "UPDATE orders SET stock_deducted_qty=qty, stock_deducted_product_id=matched_product_id "
                "WHERE matched_product_id=?", (pid,))
    conn.commit()
    conn.close()
    return len(changes), changes


def get_last_sale_price(channel_id, product_name, option_name=None):
    """그 채널(거래처)에 그 상품을 마지막으로 판매했던 단가를 반환.
    주문관리 수동등록에서 업체+상품을 고르면 직전 판매단가를 자동으로 채워주기 위함"""
    if not channel_id or not product_name:
        return None
    conn = get_connection()
    query = ("SELECT sale_price FROM orders WHERE channel_id=? AND product_name=? "
             "AND COALESCE(sale_price,0) > 0")
    params = [channel_id, product_name]
    if option_name:
        query += " AND COALESCE(option_name,'')=?"
        params.append(option_name)
    query += " ORDER BY order_date DESC, id DESC LIMIT 1"
    row = conn.execute(query, params).fetchone()
    if row is None and option_name:
        # 옵션까지 맞는 이력이 없으면 상품명만으로 다시 조회
        row = conn.execute(
            "SELECT sale_price FROM orders WHERE channel_id=? AND product_name=? "
            "AND COALESCE(sale_price,0) > 0 ORDER BY order_date DESC, id DESC LIMIT 1",
            (channel_id, product_name)).fetchone()
    conn.close()
    return row["sale_price"] if row else None


def get_qty_presets(scope):
    """수량 선택 드롭다운에 보여줄 수량 목록 (사용자가 직접 편집 가능)"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT qty FROM qty_presets WHERE scope=? ORDER BY sort_order, qty", (scope,)).fetchall()
    conn.close()
    return [r["qty"] for r in rows]


def set_qty_presets(scope, qty_list):
    """수량 목록을 통째로 교체 (설정 창에서 저장할 때 사용)"""
    conn = get_connection()
    conn.execute("DELETE FROM qty_presets WHERE scope=?", (scope,))
    for i, q in enumerate(qty_list):
        conn.execute("INSERT OR IGNORE INTO qty_presets (scope, qty, sort_order) VALUES (?,?,?)",
                     (scope, int(q), i))
    conn.commit()
    conn.close()


def get_recent_product_ids(source="order", limit=30):
    """최근에 사용한 품목 id를 최신순으로 반환.
    source='order'  -> 수동 주문등록 이력 기준 (주문관리 상품선택창에서 상위 노출)
    source='purchase' -> 입고 이력 기준 (입고관리 상품선택창에서 상위 노출)"""
    conn = get_connection()
    if source == "purchase":
        rows = conn.execute(
            """SELECT product_id as pid, MAX(purchase_date) as last_used
               FROM purchases WHERE product_id IS NOT NULL
               GROUP BY product_id ORDER BY last_used DESC, MAX(id) DESC LIMIT ?""",
            (limit,)).fetchall()
    else:
        rows = conn.execute(
            """SELECT matched_product_id as pid, MAX(order_date) as last_used
               FROM orders WHERE matched_product_id IS NOT NULL
               GROUP BY matched_product_id ORDER BY last_used DESC, MAX(id) DESC LIMIT ?""",
            (limit,)).fetchall()
    conn.close()
    return [r["pid"] for r in rows]


# ---------------- 카드 관리 ----------------
def get_cards():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM cards ORDER BY id").fetchall()
    conn.close()
    return rows


def add_card(name, card_company="", card_number="", memo=""):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO cards (name, card_company, card_number, memo) VALUES (?,?,?,?)",
        (name, card_company, card_number, memo))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_card(card_id, name, card_company="", card_number="", memo=""):
    conn = get_connection()
    conn.execute("UPDATE cards SET name=?, card_company=?, card_number=?, memo=? WHERE id=?",
                 (name, card_company, card_number, memo, card_id))
    conn.commit()
    conn.close()


def delete_card(card_id):
    conn = get_connection()
    conn.execute("UPDATE expenses SET card_id=NULL WHERE card_id=?", (card_id,))
    conn.execute("UPDATE purchase_payments SET card_id=NULL WHERE card_id=?", (card_id,))
    conn.execute("DELETE FROM cards WHERE id=?", (card_id,))
    conn.commit()
    conn.close()


# ---------------- 현금 시재 (리포트 > 자금현황 > 현금현황) ----------------
def get_cash_summary():
    """현금으로 들어오고 나간 내역을 모아 현재 현금 시재를 계산.
    현금 시재 = 현금으로 받은 정산입금 - 현금으로 나간 경비지출/매입지출"""
    conn = get_connection()
    cash_in = conn.execute(
        """SELECT settle_date as date, amount, memo, channel_id
           FROM settlements WHERE COALESCE(payment_method,'현금')='현금'"""
    ).fetchall()
    cash_expense = conn.execute(
        """SELECT date, amount, memo, category
           FROM expenses WHERE COALESCE(payment_method,'통장')='현금'"""
    ).fetchall()
    cash_purchase = conn.execute(
        """SELECT payment_date as date, amount, memo, supplier_id
           FROM purchase_payments WHERE COALESCE(payment_method,'통장')='현금'"""
    ).fetchall()
    conn.close()

    channel_map = {c["id"]: c["name"] for c in get_channels()}
    entries = []
    for r in cash_in:
        entries.append({"date": r["date"], "kind": "입금", "desc": f"정산입금 - {channel_map.get(r['channel_id'], '')}",
                        "amount": r["amount"] or 0, "memo": r["memo"] or ""})
    for r in cash_expense:
        entries.append({"date": r["date"], "kind": "출금", "desc": f"경비 - {r['category'] or ''}",
                        "amount": -(r["amount"] or 0), "memo": r["memo"] or ""})
    for r in cash_purchase:
        entries.append({"date": r["date"], "kind": "출금", "desc": f"매입대금 - {channel_map.get(r['supplier_id'], '')}",
                        "amount": -(r["amount"] or 0), "memo": r["memo"] or ""})

    conn2 = get_connection()
    cash_adj = conn2.execute(
        "SELECT adjust_date as date, change_amount, reason, memo FROM cash_adjustments").fetchall()
    conn2.close()
    for r in cash_adj:
        amt = r["change_amount"] or 0
        entries.append({"date": r["date"], "kind": "조정",
                        "desc": f"현금조정 - {r['reason'] or ''}",
                        "amount": amt, "memo": r["memo"] or ""})

    entries.sort(key=lambda e: e["date"] or "")
    running = 0
    for e in entries:
        running += e["amount"]
        e["balance"] = running
    return entries


def backfill_order_contact_info(rows):
    """이미 등록된 주문에 수취인·주소·연락처만 채워 넣음 (주문번호로 찾아서 갱신).
    예전 버전에서 업로드해 이 정보가 비어 있는 주문을 나중에 보완할 때 사용.
    새 주문을 만들지 않으므로 중복이 생기지 않음. 반환: 갱신된 건수"""
    conn = get_connection()
    updated = 0
    for r in rows:
        order_no = (r.get("order_no") or "").strip()
        if not order_no:
            continue
        receiver = (r.get("receiver_name") or "").strip()
        address = (r.get("address") or "").strip()
        phone = (r.get("phone") or "").strip()
        if not (receiver or address or phone):
            continue
        cur = conn.execute(
            """UPDATE orders SET
                 receiver_name = CASE WHEN COALESCE(receiver_name,'')='' THEN ? ELSE receiver_name END,
                 address       = CASE WHEN COALESCE(address,'')=''       THEN ? ELSE address END,
                 phone         = CASE WHEN COALESCE(phone,'')=''         THEN ? ELSE phone END
               WHERE order_no = ?
                 AND (COALESCE(receiver_name,'')='' OR COALESCE(address,'')='' OR COALESCE(phone,'')='')""",
            (receiver, address, phone, order_no))
        updated += cur.rowcount
    conn.commit()
    conn.close()
    return updated


# ---------------- 조합(세트) 상품 ----------------
def get_bundle_components(bundle_product_id):
    """조합 품목의 구성 품목 목록 반환"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT product_bundles.*, products.name as component_name,
                  products.option_name as component_option, products.stock_qty as component_stock
           FROM product_bundles
           JOIN products ON product_bundles.component_product_id = products.id
           WHERE bundle_product_id=? ORDER BY product_bundles.id""",
        (bundle_product_id,)).fetchall()
    conn.close()
    return rows


def get_all_bundle_ids():
    """조합 품목인 품목 id들의 집합 (구성품이 등록된 품목)"""
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT bundle_product_id FROM product_bundles").fetchall()
    conn.close()
    return {r["bundle_product_id"] for r in rows}


def create_bundle_product(component_ids, sale_price=0, memo="", option_name=None):
    """여러 품목을 묶어 조합(세트) 품목을 새로 만듦.
    첫 번째 품목이 기준이 되고, 나머지 품목의 옵션명(없으면 상품명)을 괄호로 덧붙임.
    예) '캠핑 릴선/컴팩트릴 20M' + '부품/가이드' -> '캠핑 릴선' / '컴팩트릴 20M(가이드)'
    조합 품목 자체는 재고를 갖지 않고, 판매되면 구성품 재고가 대신 차감됨.
    반환: (새 품목 id, 표시이름) / 이미 같은 이름이 있으면 (기존 id, 이름)"""
    if len(component_ids) < 2:
        raise ValueError("조합은 2개 이상의 품목을 선택해야 합니다.")

    products = {p["id"]: p for p in get_products()}
    base = products[component_ids[0]]
    extras = []
    for pid in component_ids[1:]:
        p = products[pid]
        extras.append((p["option_name"] or p["name"] or "").strip())

    if option_name:
        new_option = option_name.strip()
    else:
        base_option = (base["option_name"] or "").strip()
        suffix = "+".join(x for x in extras if x)
        new_option = f"{base_option}+{suffix}" if base_option else suffix
    new_name = base["name"]

    # 이미 같은 조합 품목이 있으면 그걸 그대로 사용
    for p in products.values():
        if p["name"] == new_name and (p["option_name"] or "") == new_option:
            return p["id"], f"{new_name} {new_option}".strip()

    total_cost = sum((products[pid]["cost_price"] or 0) for pid in component_ids)
    if not sale_price:
        sale_price = base["sale_price"] or 0

    bundle_id = add_product("", new_name, total_cost, sale_price, 0,
                             memo or "조합상품(구성품 재고에서 차감)", option_name=new_option)

    conn = get_connection()
    for pid in component_ids:
        conn.execute(
            "INSERT OR IGNORE INTO product_bundles (bundle_product_id, component_product_id, qty) VALUES (?,?,1)",
            (bundle_id, pid))
    conn.commit()
    conn.close()
    return bundle_id, f"{new_name} {new_option}".strip()


def delete_bundle(bundle_product_id):
    """조합 설정만 해제 (품목 자체는 남김)"""
    conn = get_connection()
    conn.execute("DELETE FROM product_bundles WHERE bundle_product_id=?", (bundle_product_id,))
    conn.commit()
    conn.close()


def add_upload_history_returning_id(filename, channel_id, row_count):
    """업로드 이력을 남기고 그 id를 반환 (주문에 연결해서 나중에 파일별 조회에 사용)"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO upload_history (filename, channel_id, uploaded_at, row_count) "
        "VALUES (?,?,datetime('now','localtime'),?)",
        (filename, channel_id, row_count))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_orders_by_upload(upload_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT orders.*, channels.name as channel_name FROM orders
           LEFT JOIN channels ON orders.channel_id = channels.id
           WHERE orders.upload_id=? ORDER BY orders.order_date DESC, orders.id DESC""",
        (upload_id,)).fetchall()
    conn.close()
    return rows


def get_related_order_history(buyer_name=None, receiver_name=None, address=None,
                               phone=None, months=12, exclude_order_id=None,
                               include_order_id=None):
    """주문 상세의 '과거 주문내역'용.
    구매자명이 같거나, (구매자가 달라도) 수취인명+주소가 같거나, 전화번호가 같은
    주문을 최근 N개월 범위에서 찾아 반환. 담당자가 바뀌어도 같은 거래처의
    과거 구매 이력을 확인할 수 있게 하기 위함."""
    cutoff = (date.today() - timedelta(days=30 * months)).isoformat()
    conn = get_connection()
    clauses, params = [], []
    if buyer_name:
        clauses.append("COALESCE(orders.buyer_name,'') = ?")
        params.append(buyer_name)
    if receiver_name and address:
        clauses.append("(COALESCE(orders.receiver_name,'') = ? AND COALESCE(orders.address,'') = ?)")
        params.extend([receiver_name, address])
    if phone:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits:
            clauses.append(
                "REPLACE(REPLACE(COALESCE(orders.phone,''),'-',''),' ','') = ?")
            params.append(digits)
    # 아무 기준도 없으면(구매자·수취인·전화 모두 비어있는 주문) 최소한 그 주문 자체는 보여줌
    if not clauses and include_order_id:
        rows = conn.execute(
            """SELECT orders.*, channels.name as channel_name FROM orders
               LEFT JOIN channels ON orders.channel_id = channels.id WHERE orders.id=?""",
            (include_order_id,)).fetchall()
        conn.close()
        return rows
    if not clauses:
        conn.close()
        return []

    # 기준에 맞는 주문 + (기간을 벗어나더라도) 지금 보고 있는 주문은 항상 포함
    include_clause = " OR orders.id = ?" if include_order_id else ""
    query = f"""SELECT orders.*, channels.name as channel_name FROM orders
                LEFT JOIN channels ON orders.channel_id = channels.id
                WHERE (({' OR '.join(clauses)})
                       AND substr(COALESCE(orders.order_date,''), 1, 10) >= ?){include_clause}"""
    params.append(cutoff)
    if include_order_id:
        params.append(include_order_id)
    if exclude_order_id:
        query += " AND orders.id <> ?"
        params.append(exclude_order_id)
    query += " ORDER BY orders.order_date DESC, orders.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


# ---------------- 현금 조정 ----------------
def add_cash_adjustment(adjust_date, change_amount, reason, memo=""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO cash_adjustments (adjust_date, change_amount, reason, memo) VALUES (?,?,?,?)",
        (adjust_date, change_amount, reason, memo))
    conn.commit()
    conn.close()


def get_bundle_shipment_history(date_from=None, date_to=None):
    """조합(세트) 품목의 출고(판매) 내역 - 어떤 구성품이 얼마나 나갔는지 함께 보여줌"""
    conn = get_connection()
    query = """SELECT orders.id, orders.order_date, orders.order_no, orders.qty,
                      orders.matched_product_id, channels.name as channel_name,
                      orders.buyer_name, products.name as product_name,
                      products.option_name as option_name
               FROM orders
               JOIN products ON orders.matched_product_id = products.id
               LEFT JOIN channels ON orders.channel_id = channels.id
               WHERE orders.matched_product_id IN (SELECT DISTINCT bundle_product_id FROM product_bundles)"""
    params = []
    if date_from:
        query += " AND substr(COALESCE(orders.order_date,''),1,10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(COALESCE(orders.order_date,''),1,10) <= ?"
        params.append(date_to)
    query += " ORDER BY orders.order_date DESC, orders.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        comps = get_bundle_components(r["matched_product_id"])
        comp_text = ", ".join(
            f"{(c['component_option'] or c['component_name'])} {(c['qty'] or 1) * (r['qty'] or 0)}개"
            for c in comps)
        result.append({
            "date": r["order_date"], "order_no": r["order_no"],
            "channel_name": r["channel_name"] or "", "buyer_name": r["buyer_name"] or "",
            "bundle_label": f"{r['product_name']} {r['option_name'] or ''}".strip(),
            "qty": r["qty"] or 0, "components": comp_text,
        })
    return result


# ---------------- 고객별 순위 (리포트 > 매출분석) ----------------
def get_customer_ranking(date_from=None, date_to=None, min_orders=3, limit=10):
    """기간 내 고객별 매출 순위.
    같은 사람을 최대한 하나로 묶기 위해 '전화번호(숫자만) > 수취인+주소 > 구매자명' 순으로
    식별키를 정함. min_orders 이상 구매한 고객만 반환(반복구매 고객)."""
    conn = get_connection()
    query = """SELECT orders.*, channels.name as channel_name FROM orders
               LEFT JOIN channels ON orders.channel_id = channels.id WHERE 1=1"""
    params = []
    if date_from:
        query += " AND substr(COALESCE(orders.order_date,''),1,10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(COALESCE(orders.order_date,''),1,10) <= ?"
        params.append(date_to)
    rows = conn.execute(query, params).fetchall()
    conn.close()

    groups = {}
    for r in rows:
        phone_digits = "".join(ch for ch in (r["phone"] or "") if ch.isdigit())
        receiver = (r["receiver_name"] or "").strip()
        address = (r["address"] or "").strip()
        buyer = (r["buyer_name"] or "").strip()
        if phone_digits:
            key = ("phone", phone_digits)
        elif receiver and address:
            key = ("addr", receiver, address)
        elif buyer:
            key = ("buyer", buyer)
        else:
            continue

        g = groups.setdefault(key, {
            "name": buyer or receiver or "(이름없음)",
            "receiver": receiver, "phone": r["phone"] or "", "address": address,
            "order_count": 0, "total_qty": 0, "total_amount": 0,
            "channels": set(), "last_order": "", "orders": [],
            "order_days": set(),   # 같은 날 여러 종류를 사도 1건으로 세기 위한 날짜 모음
        })
        # 주문횟수는 "구매한 날짜 수"로 계산 (같은 날 여러 상품을 담아도 1건)
        g["order_days"].add((r["order_date"] or "")[:10])
        g["total_qty"] += r["qty"] or 0
        g["total_amount"] += r["total_amount"] or 0
        if r["channel_name"]:
            g["channels"].add(r["channel_name"])
        if (r["order_date"] or "") > g["last_order"]:
            g["last_order"] = r["order_date"] or ""
        if not g["receiver"] and receiver:
            g["receiver"] = receiver
        if not g["phone"] and r["phone"]:
            g["phone"] = r["phone"]
        if not g["address"] and address:
            g["address"] = address
        g["orders"].append(r)

    for g in groups.values():
        g["order_count"] = len(g["order_days"])

    result = [g for g in groups.values() if g["order_count"] >= min_orders]
    result.sort(key=lambda g: g["total_amount"], reverse=True)
    for g in result:
        g["channels"] = ", ".join(sorted(g["channels"]))
    return result[:limit]


def delete_upload_history(upload_id, delete_orders=False):
    """업로드 이력 삭제. delete_orders=True면 그 파일로 등록된 주문도 함께 삭제
    (주문 삭제 시 차감됐던 재고도 정상 복원됨)"""
    conn = get_connection()
    order_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM orders WHERE upload_id=?", (upload_id,)).fetchall()]
    conn.close()

    deleted_orders = 0
    if delete_orders:
        for oid in order_ids:
            delete_order(oid)      # 재고 복원 포함
            deleted_orders += 1
    else:
        conn = get_connection()
        conn.execute("UPDATE orders SET upload_id=NULL WHERE upload_id=?", (upload_id,))
        conn.commit()
        conn.close()

    conn = get_connection()
    conn.execute("DELETE FROM upload_history WHERE id=?", (upload_id,))
    conn.commit()
    conn.close()
    return len(order_ids), deleted_orders


def update_channel_platform_info(channel_id, platform_type="", site_url="", settle_cycle=""):
    """판매채널의 부가 정보(판매형태/셀러센터주소/정산주기) 저장"""
    conn = get_connection()
    conn.execute(
        "UPDATE channels SET platform_type=?, site_url=?, settle_cycle=? WHERE id=?",
        (platform_type, site_url, settle_cycle, channel_id))
    conn.commit()
    conn.close()


def get_product_sales_ranking_ids(channel_id=None, limit=200):
    """매출이 높은 순으로 품목 id 목록 반환 (상품 선택창 정렬용)"""
    conn = get_connection()
    query = """SELECT matched_product_id as pid, COALESCE(SUM(total_amount),0) as total
               FROM orders WHERE matched_product_id IS NOT NULL"""
    params = []
    if channel_id:
        query += " AND channel_id=?"
        params.append(channel_id)
    query += " GROUP BY matched_product_id ORDER BY total DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [r["pid"] for r in rows]




def get_all_expenses_overview(date_from=None, date_to=None):
    """리포트 자금현황 > 지출 종합 - 경비지출 + 매입지출을 한 곳에 모아서 반환"""
    conn = get_connection()
    exp_q = """SELECT expenses.date as date, '경비' as kind, expenses.category as category,
                      expenses.amount as amount, expenses.payment_method as method,
                      COALESCE(bank_accounts.bank_name, bank_accounts.name) as bank_name,
                      cards.name as card_name, expenses.memo as memo, '' as partner
               FROM expenses
               LEFT JOIN bank_accounts ON expenses.bank_account_id = bank_accounts.id
               LEFT JOIN cards ON expenses.card_id = cards.id WHERE 1=1"""
    pp_q = """SELECT purchase_payments.payment_date as date, '매입대금' as kind,
                     '매입결제' as category, purchase_payments.amount as amount,
                     purchase_payments.payment_method as method,
                     COALESCE(bank_accounts.bank_name, bank_accounts.name) as bank_name,
                     cards.name as card_name, purchase_payments.memo as memo,
                     channels.name as partner
              FROM purchase_payments
              LEFT JOIN bank_accounts ON purchase_payments.bank_account_id = bank_accounts.id
              LEFT JOIN cards ON purchase_payments.card_id = cards.id
              LEFT JOIN channels ON purchase_payments.supplier_id = channels.id WHERE 1=1"""
    params = []
    for _ in range(2):
        pass
    cond = ""
    if date_from:
        cond += " AND substr(date, 1, 10) >= ?"
    if date_to:
        cond += " AND substr(date, 1, 10) <= ?"

    exp_cond = cond.replace("date", "expenses.date")
    pp_cond = cond.replace("date", "purchase_payments.payment_date")
    p = []
    if date_from:
        p.append(date_from)
    if date_to:
        p.append(date_to)

    rows = conn.execute(
        f"SELECT * FROM ({exp_q}{exp_cond}) UNION ALL SELECT * FROM ({pp_q}{pp_cond}) "
        f"ORDER BY date DESC", p + p).fetchall()
    conn.close()
    return rows


# ---------------- 반품 / 반출 ----------------
def add_return(return_type, return_date, channel_id, product_id, product_name, option_name,
               qty, unit_price, customer_name="", reason="", memo="", order_id=None,
               status="접수"):
    """반품(고객->우리) 또는 반출(우리->거래처) 기록.
    완료 상태면 재고도 함께 반영 (반품=재고 증가 / 반출=재고 감소)"""
    total = (qty or 0) * (unit_price or 0)
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO returns (return_type, return_date, channel_id, order_id, product_id,
                                 product_name, option_name, qty, unit_price, total_amount,
                                 buyer_name, reason, status, memo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (return_type, return_date, channel_id, order_id, product_id, product_name, option_name,
         qty, unit_price, total, customer_name, reason, status, memo))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    if status == "완료":
        _apply_return_stock(new_id)
    return new_id


def _apply_return_stock(return_id):
    """반품/반출 완료 시 재고 반영 (조합상품이면 구성품까지). 중복 반영 방지."""
    conn = get_connection()
    r = conn.execute(
        "SELECT return_type, product_id, qty, stock_applied FROM returns WHERE id=?",
        (return_id,)).fetchone()
    if r and r["product_id"] and not r["stock_applied"]:
        delta = (r["qty"] or 0) if r["return_type"] == "반품" else -(r["qty"] or 0)
        _adjust_stock_for_product(conn, r["product_id"], delta)
        conn.execute("UPDATE returns SET stock_applied=1 WHERE id=?", (return_id,))
        conn.commit()
    conn.close()


def complete_return(return_id):
    """접수 상태의 반품/반출을 완료 처리 (재고 반영)"""
    conn = get_connection()
    r = conn.execute("SELECT status FROM returns WHERE id=?", (return_id,)).fetchone()
    if not r or r["status"] == "완료":
        conn.close()
        return False
    conn.execute("UPDATE returns SET status='완료' WHERE id=?", (return_id,))
    conn.commit()
    conn.close()
    _apply_return_stock(return_id)
    return True


def get_returns(return_type=None, date_from=None, date_to=None):
    conn = get_connection()
    query = """SELECT returns.*, channels.name as channel_name FROM returns
               LEFT JOIN channels ON returns.channel_id = channels.id WHERE 1=1"""
    params = []
    if return_type:
        query += " AND returns.return_type=?"
        params.append(return_type)
    if date_from:
        query += " AND substr(COALESCE(returns.return_date,''),1,10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(COALESCE(returns.return_date,''),1,10) <= ?"
        params.append(date_to)
    query += " ORDER BY returns.return_date DESC, returns.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def delete_return(return_id):
    """반품/반출 삭제 - 재고에 반영됐던 것은 되돌림"""
    conn = get_connection()
    r = conn.execute(
        "SELECT return_type, product_id, qty, stock_applied FROM returns WHERE id=?",
        (return_id,)).fetchone()
    if r and r["stock_applied"] and r["product_id"]:
        delta = -(r["qty"] or 0) if r["return_type"] == "반품" else (r["qty"] or 0)
        _adjust_stock_for_product(conn, r["product_id"], delta)
    conn.execute("DELETE FROM returns WHERE id=?", (return_id,))
    conn.commit()
    conn.close()


def find_orders_for_return(channel_id, customer_name):
    """반품 수동입력 도우미 - 채널+고객명으로 최근 주문을 찾아옴"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT orders.*, channels.name as channel_name FROM orders
           LEFT JOIN channels ON orders.channel_id = channels.id
           WHERE orders.channel_id=?
             AND (orders.buyer_name LIKE ? OR COALESCE(orders.receiver_name,'') LIKE ?)
           ORDER BY orders.order_date DESC, orders.id DESC LIMIT 100""",
        (channel_id, f"%{customer_name}%", f"%{customer_name}%")).fetchall()
    conn.close()
    return rows



def get_product_ranking_for_channel(channel_id, limit=200):
    """특정 거래처에서 매출이 높은 순으로 품목 id 목록 (상품선택창 상단 노출용)"""
    if not channel_id:
        return []
    conn = get_connection()
    rows = conn.execute(
        """SELECT matched_product_id as pid, SUM(total_amount) as amt FROM orders
           WHERE channel_id=? AND matched_product_id IS NOT NULL
           GROUP BY matched_product_id ORDER BY amt DESC LIMIT ?""",
        (channel_id, limit)).fetchall()
    conn.close()
    return [r["pid"] for r in rows]


def get_general_sales_total(year_month=None):
    """온라인 판매채널이 아닌 일반거래처(직거래·도매 등)의 매출 합계.
    대시보드의 '일반매출' 카드에 사용됨"""
    conn = get_connection()
    query = """SELECT COALESCE(SUM(COALESCE(orders.qty,0) * COALESCE(orders.sale_price,0)
                                   + COALESCE(orders.shipping_fee,0)), 0) as total
               FROM orders
               JOIN channels ON orders.channel_id = channels.id
               WHERE COALESCE(channels.channel_type,'온라인채널') = '일반업체'"""
    params = []
    if year_month:
        query += " AND substr(COALESCE(orders.order_date,''),1,7) = ?"
        params.append(year_month)
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row["total"] or 0


def get_top_selling_product_ids(channel_id=None, limit=100):
    """매출이 높은 순서의 품목 id 목록.
    channel_id를 주면 그 거래처(채널)에서 많이 팔린 순서로 반환 -
    수동 주문등록의 상품 선택창에서 자주 파는 상품을 위로 올리는 데 사용"""
    conn = get_connection()
    query = """SELECT matched_product_id as pid,
                      SUM(COALESCE(qty,0) * COALESCE(sale_price,0)) as amount
               FROM orders WHERE matched_product_id IS NOT NULL"""
    params = []
    if channel_id:
        query += " AND channel_id = ?"
        params.append(channel_id)
    query += " GROUP BY matched_product_id ORDER BY amount DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [r["pid"] for r in rows]


def get_all_expenses_combined(date_from=None, date_to=None):
    """모든 지출을 한 곳에 모아 보여주기 위한 통합 조회
    (경비지출 + 매입지출). 리포트 > 자금현황 > 지출 현황용"""
    conn = get_connection()
    rows = []

    q1 = """SELECT expenses.date as d, expenses.category as category, expenses.amount as amount,
                   expenses.memo as memo, expenses.payment_method as method,
                   COALESCE(bank_accounts.bank_name, bank_accounts.name) as bank_name,
                   cards.name as card_name
            FROM expenses
            LEFT JOIN bank_accounts ON expenses.bank_account_id = bank_accounts.id
            LEFT JOIN cards ON expenses.card_id = cards.id
            WHERE 1=1"""
    q2 = """SELECT purchase_payments.payment_date as d, channels.name as category,
                   purchase_payments.amount as amount, purchase_payments.memo as memo,
                   purchase_payments.payment_method as method,
                   COALESCE(bank_accounts.bank_name, bank_accounts.name) as bank_name,
                   cards.name as card_name
            FROM purchase_payments
            LEFT JOIN channels ON purchase_payments.supplier_id = channels.id
            LEFT JOIN bank_accounts ON purchase_payments.bank_account_id = bank_accounts.id
            LEFT JOIN cards ON purchase_payments.card_id = cards.id
            WHERE 1=1"""
    params = []
    date_clause = ""
    if date_from:
        date_clause += " AND substr(d_col,1,10) >= ?"
    if date_to:
        date_clause += " AND substr(d_col,1,10) <= ?"

    for q, kind, col in ((q1, "경비지출", "expenses.date"),
                          (q2, "매입지출", "purchase_payments.payment_date")):
        qq = q + date_clause.replace("d_col", col)
        p = []
        if date_from:
            p.append(date_from)
        if date_to:
            p.append(date_to)
        for r in conn.execute(qq, p).fetchall():
            method = r["method"] or "통장"
            if method == "통장":
                method_label = f"통장 - {r['bank_name']}" if r["bank_name"] else "통장"
            elif method == "카드":
                method_label = f"카드 - {r['card_name']}" if r["card_name"] else "카드"
            else:
                method_label = "현금"
            rows.append({
                "date": r["d"] or "", "kind": kind,
                "category": r["category"] or "", "amount": r["amount"] or 0,
                "method": method_label, "raw_method": method, "memo": r["memo"] or "",
            })
    conn.close()
    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows


def set_supplier_discount_rate(supplier_id, rate):
    """거래처별 매입 할인율(%) 저장. 공급가액 기준 -3%~-5% 같은 상시 할인 반영용"""
    conn = get_connection()
    conn.execute("UPDATE channels SET discount_rate=? WHERE id=?", (rate, supplier_id))
    conn.commit()
    conn.close()


def get_supplier_discount_rate(supplier_id):
    if not supplier_id:
        return 0.0
    conn = get_connection()
    row = conn.execute("SELECT discount_rate FROM channels WHERE id=?", (supplier_id,)).fetchone()
    conn.close()
    return (row["discount_rate"] or 0.0) if row else 0.0


def get_supplier_unpaid_with_discount(supplier_id):
    """거래처의 미결제 금액에 할인율을 적용한 '실제 결제할 금액'을 계산.
    반환: (미결제원금, 할인율, 할인액, 결제할금액)"""
    conn = get_connection()
    row = conn.execute(
        """SELECT COALESCE(SUM(COALESCE(total_amount,0) - COALESCE(paid_amount,0)), 0) as unpaid
           FROM purchases WHERE supplier_id=?""", (supplier_id,)).fetchone()
    conn.close()
    unpaid = row["unpaid"] or 0
    rate = get_supplier_discount_rate(supplier_id)
    discount = round(unpaid * rate / 100)
    return unpaid, rate, discount, unpaid - discount


def sync_stock_for_all_orders():
    """모든 주문의 재고 반영 상태를 한 번의 연결로 일괄 동기화.
    주문마다 연결을 새로 여는 방식(sync_stock_for_order 반복)은 주문이 많아지면
    매우 느려서, 매칭 후 일괄 처리를 위해 따로 만든 버전."""
    conn = get_connection()
    orders = conn.execute(
        "SELECT id, qty, matched_product_id, stock_deducted_qty, stock_deducted_product_id "
        "FROM orders").fetchall()

    bundle_map = {}
    for b in conn.execute(
            "SELECT bundle_product_id, component_product_id, qty FROM product_bundles").fetchall():
        bundle_map.setdefault(b["bundle_product_id"], []).append(
            (b["component_product_id"], b["qty"] or 1))

    deltas = {}   # product_id -> 재고 증감 합계
    updates = []  # (deducted_qty, deducted_product_id, order_id)

    def add_delta(pid, qty_delta):
        if not pid or not qty_delta:
            return
        if pid in bundle_map:
            for comp_id, comp_qty in bundle_map[pid]:
                deltas[comp_id] = deltas.get(comp_id, 0) + qty_delta * comp_qty
        else:
            deltas[pid] = deltas.get(pid, 0) + qty_delta

    for o in orders:
        old_pid = o["stock_deducted_product_id"]
        old_qty = o["stock_deducted_qty"] or 0
        new_pid = o["matched_product_id"]
        new_qty = o["qty"] or 0
        if old_pid == new_pid:
            diff = new_qty - old_qty
            if diff:
                add_delta(new_pid, -diff)
            else:
                continue   # 바뀐 게 없으면 UPDATE도 생략
        else:
            add_delta(old_pid, old_qty)
            add_delta(new_pid, -new_qty)
        updates.append((new_qty if new_pid else 0, new_pid, o["id"]))

    for pid, delta in deltas.items():
        conn.execute("UPDATE products SET stock_qty = COALESCE(stock_qty,0) + ? WHERE id=?",
                     (delta, pid))
    if updates:
        conn.executemany(
            "UPDATE orders SET stock_deducted_qty=?, stock_deducted_product_id=? WHERE id=?",
            updates)
    conn.commit()
    conn.close()


def auto_backup(keep=10):
    """앱을 켤 때 데이터 파일을 자동으로 백업해둠 (최근 keep개만 유지).
    실수로 데이터가 지워지거나 파일이 깨져도 되돌릴 수 있게 하기 위함."""
    import shutil, glob
    if not os.path.exists(DB_PATH):
        return None
    folder = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "backups")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    try:
        shutil.copy2(DB_PATH, dest)
    except Exception:
        return None
    files = sorted(glob.glob(os.path.join(folder, "ledger_*.db")))
    for old in files[:-keep]:
        try:
            os.remove(old)
        except OSError:
            pass
    return dest


def check_integrity():
    """DB 무결성 검사. 문제가 있으면 메시지를 반환, 정상이면 None"""
    try:
        conn = get_connection()
        row = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        result = row[0] if row else "unknown"
        return None if result == "ok" else result
    except sqlite3.Error as e:
        return str(e)


def get_data_counts():
    """주요 데이터 건수 - 화면에 '전체 몇 건'을 보여줘서 데이터가 사라진 게 아님을 확인시켜줌"""
    conn = get_connection()
    counts = {}
    for label, table in [("주문", "orders"), ("입고", "purchases"), ("품목", "products"),
                          ("업로드", "upload_history")]:
        try:
            counts[label] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            counts[label] = 0
    conn.close()
    return counts


def flush_to_disk():
    """열려 있는 변경사항을 디스크에 확실히 기록.
    네트워크 드라이브(Z: 등)나 동기화 폴더에서는 쓰기가 지연될 수 있어,
    종료할 때 한 번 강제로 반영해줌. 반환: (성공여부, 메시지)"""
    try:
        conn = get_connection()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        conn.execute("PRAGMA synchronous = FULL")
        conn.commit()
        row = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        conn.close()
        return True, f"주문 {row[0]:,}건 포함 모든 데이터가 저장되었습니다."
    except Exception as e:
        return False, str(e)


def verify_write_access():
    """데이터 파일에 실제로 쓸 수 있는지 확인 (네트워크 드라이브 끊김 등 감지)"""
    try:
        conn = get_connection()
        conn.execute("CREATE TABLE IF NOT EXISTS _wtest (x INTEGER)")
        conn.execute("DROP TABLE IF EXISTS _wtest")
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_suppliers_by_sales():
    """일반거래처 목록을 매출 많은 순 -> 같으면 가나다순으로 반환
    (수동 주문등록 드롭다운에서 자주 거래하는 곳이 위에 오도록)"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT channels.*, COALESCE(SUM(orders.total_amount), 0) as sales
           FROM channels LEFT JOIN orders ON orders.channel_id = channels.id
           WHERE COALESCE(channels.channel_type,'온라인채널') = '일반업체'
           GROUP BY channels.id
           ORDER BY sales DESC, channels.name COLLATE NOCASE"""
    ).fetchall()
    conn.close()
    return rows


def filter_new_orders(rows):
    """이미 등록된 주문번호는 걸러내고 새 주문만 반환.
    같은 파일을 다시 올려도 새로 추가된 주문만 들어가게 하기 위함.
    반환: (새 주문 목록, 건너뛴 건수)"""
    if not rows:
        return [], 0
    # 같은 주문번호라도 옵션·수량이 다르면 서로 다른 건임 (분할배송 등).
    # 그래서 주문번호만으로 판단하지 않고 "주문번호+옵션+수량+금액"을 함께 비교함
    # (예전엔 주문번호만 봐서, 한 주문에 여러 줄로 나뉜 건이 통째로 빠졌음)
    def key_of(order_no, option_name, qty, amount):
        return (str(order_no or "").strip(), str(option_name or "").strip(),
                int(qty or 0), int(amount or 0))

    # DB에 이미 있는 건수를 키별로 세어두고, 파일에 그보다 많이 들어온 만큼만 새로 등록
    from collections import Counter
    conn = get_connection()
    existing = Counter(
        key_of(r["order_no"], r["option_name"], r["qty"], r["total_amount"])
        for r in conn.execute(
            "SELECT order_no, option_name, qty, total_amount FROM orders "
            "WHERE order_no IS NOT NULL").fetchall()
    )
    conn.close()

    new_rows, skipped = [], 0
    for r in rows:
        no = (r.get("order_no") or "").strip()
        if not no:
            new_rows.append(r)
            continue
        k = key_of(no, r.get("option_name"), r.get("qty"), r.get("total_amount"))
        if existing.get(k, 0) > 0:
            existing[k] -= 1     # 이미 있는 만큼은 건너뜀
            skipped += 1
            continue
        new_rows.append(r)
    return new_rows, skipped


def _now_ts():
    """타임스탬프 정수 반환 (주문번호 생성용)"""
    import time
    return int(time.time() * 1000)


def get_channel_sales_summary(date_from=None, date_to=None):
    """채널별 매출/수수료/원가/이익 요약 (리포트용)"""
    conn = get_connection()
    params, where = [], []
    if date_from:
        where.append("substr(o.order_date,1,10) >= ?"); params.append(date_from)
    if date_to:
        where.append("substr(o.order_date,1,10) <= ?"); params.append(date_to)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(f"""
        SELECT ch.name as channel_name,
               COALESCE(ch.channel_type,'온라인채널') as channel_type,
               COUNT(o.id) as order_count,
               SUM(o.total_amount) as total_sales,
               SUM(o.fee_amount) as total_fee,
               SUM(COALESCE(p.cost_price,0)*o.qty) as total_cost,
               COALESCE(SUM(o.shipping_fee),0) as shipping_total,
               COALESCE(SUM(o.shipping_fee_charge),0) as shipping_charge,
               COALESCE(SUM(o.shipping_net),0) as shipping_net,
               SUM(o.total_amount - o.fee_amount - COALESCE(p.cost_price,0)*o.qty)
                   + COALESCE(SUM(o.shipping_net),0) as profit
        FROM orders o
        LEFT JOIN channels ch ON o.channel_id=ch.id
        LEFT JOIN products p ON o.matched_product_id=p.id
        {clause}
        GROUP BY o.channel_id ORDER BY total_sales DESC
    """, params).fetchall()
    conn.close()
    return rows


def set_channel_settle_bank(channel_id, bank_account_id):
    """채널별 정산 입금통장 지정 (마켓 정산은 현금이 아니라 통장으로만 들어옴)"""
    conn = get_connection()
    conn.execute("UPDATE channels SET settle_bank_id=? WHERE id=?", (bank_account_id, channel_id))
    conn.commit()
    conn.close()


def get_channel_settle_bank(channel_id):
    if not channel_id:
        return None
    conn = get_connection()
    row = conn.execute("SELECT settle_bank_id FROM channels WHERE id=?", (channel_id,)).fetchone()
    conn.close()
    return row["settle_bank_id"] if row else None


def mark_order_returned(order_id):
    """주문을 반품 처리. 매출에서 빠지도록 금액을 0으로 만들고,
    차감됐던 재고는 되돌림 (조합상품이면 구성품 재고도 함께 복원)"""
    reverse_stock_for_order(order_id)   # 차감했던 재고 복원
    conn = get_connection()
    conn.execute(
        """UPDATE orders SET status='반품', total_amount=0, settlement_amount=0,
                             fee_amount=0, stock_deducted_qty=0,
                             stock_deducted_product_id=NULL
           WHERE id=?""", (order_id,))
    conn.commit()
    conn.close()


def get_my_company_info():
    """설정에 저장된 우리 회사(공급자) 정보"""
    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS company_info (
        key TEXT PRIMARY KEY, value TEXT)""")
    rows = conn.execute("SELECT key, value FROM company_info").fetchall()
    conn.commit()
    conn.close()
    info = {r["key"]: r["value"] for r in rows}
    info.setdefault("name", "")
    info.setdefault("ceo", "")
    info.setdefault("biznum", "")
    info.setdefault("address", "")
    info.setdefault("business_type", "")
    info.setdefault("business_item", "")
    info.setdefault("bank_info", "")
    return info


def save_my_company_info(info):
    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS company_info (
        key TEXT PRIMARY KEY, value TEXT)""")
    for k, v in info.items():
        conn.execute("INSERT INTO company_info (key, value) VALUES (?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v or ""))
    conn.commit()
    conn.close()


def return_order_partial(order_id, return_qty, reason=""):
    """반품 처리. 전체면 주문상태를 '반품'으로, 일부면 그만큼 수량·금액을 줄임.
    어느 쪽이든 반품한 수량만큼 재고는 되돌아옴."""
    order = get_order_by_id(order_id)
    if not order:
        return
    total_qty = int(order["qty"] or 0)
    return_qty = max(0, min(int(return_qty or 0), total_qty))
    if not return_qty:
        return

    unit = order["sale_price"] or 0
    memo = (order["memo"] or "")
    tag = f"[반품 {return_qty}개{(' - ' + reason) if reason else ''}]"

    if return_qty >= total_qty:
        mark_order_returned(order_id)
        conn = get_connection()
        conn.execute("UPDATE orders SET memo=? WHERE id=?",
                     ((memo + " " + tag).strip(), order_id))
        conn.commit()
        conn.close()
        return

    # 일부 반품: 남은 수량 기준으로 금액을 다시 계산
    left_qty = total_qty - return_qty
    new_total = unit * left_qty
    fee = order["fee_amount"] or 0
    new_fee = round(fee * left_qty / total_qty) if total_qty else 0
    ship = order["shipping_fee"] or 0
    conn = get_connection()
    conn.execute(
        """UPDATE orders SET qty=?, total_amount=?, fee_amount=?,
                             settlement_amount=?, memo=? WHERE id=?""",
        (left_qty, new_total, new_fee, new_total - new_fee + ship,
         (memo + " " + tag).strip(), order_id))
    conn.commit()
    conn.close()
    sync_stock_for_order(order_id)   # 줄어든 수량만큼 재고 복원


def save_shipment_history(rows):
    """송장요청서로 보낸 내역을 저장 (다음에 같은 곳으로 보낼 때 골라 쓰려고)"""
    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS shipment_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sent_date TEXT, receiver TEXT, phone TEXT, address TEXT,
        product TEXT, qty INTEGER, box_qty INTEGER, message TEXT)""")
    for r in rows:
        conn.execute(
            """INSERT INTO shipment_history
               (sent_date, receiver, phone, address, product, qty, box_qty, message)
               VALUES (date('now','localtime'),?,?,?,?,?,?,?)""",
            (r.get("receiver", ""), r.get("phone", ""), r.get("address", ""),
             r.get("product", ""), int(r.get("qty") or 0), int(r.get("box_qty") or 1),
             r.get("message", "")))
    conn.commit()
    conn.close()


def get_shipment_history(limit=100):
    """과거 송장 발송 이력 (받는분+주소 기준으로 최근 것만)"""
    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS shipment_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sent_date TEXT, receiver TEXT, phone TEXT, address TEXT,
        product TEXT, qty INTEGER, box_qty INTEGER, message TEXT)""")
    rows = conn.execute(
        """SELECT * FROM shipment_history WHERE id IN (
               SELECT MAX(id) FROM shipment_history GROUP BY receiver, address)
           ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return rows


def update_channel_extra(channel_id, address="", business_type="", business_item="", ceo=None):
    """거래처의 주소·업태·종목·대표자 저장 - 거래명세표 공급받는자 칸에 들어가는 정보"""
    conn = get_connection()
    if ceo is None:
        conn.execute("UPDATE channels SET address=?, business_type_ch=?, business_item_ch=? WHERE id=?",
                     (address, business_type, business_item, channel_id))
    else:
        conn.execute("UPDATE channels SET address=?, business_type_ch=?, business_item_ch=?, ceo=? WHERE id=?",
                     (address, business_type, business_item, ceo, channel_id))
    conn.commit()
    conn.close()


def fix_settlement_bank_accounts():
    """파일 업로드로 들어온 정산 내역 중 bank_account_id가 없는 건에
    채널별 지정 통장을 소급 적용. 설정에서 통장을 지정한 뒤 이 함수를 실행하면
    기존 내역도 통장현황에 반영됩니다."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, channel_id, amount FROM settlements WHERE bank_account_id IS NULL"
    ).fetchall()
    fixed = 0
    bank_totals = {}   # 같은 연결 안에서 잔액을 합산해 한 번에 업데이트
    for r in rows:
        bank_id = get_channel_settle_bank(r["channel_id"])
        if bank_id:
            conn.execute(
                "UPDATE settlements SET bank_account_id=?, payment_method='통장' WHERE id=?",
                (bank_id, r["id"]))
            bank_totals[bank_id] = bank_totals.get(bank_id, 0) + (r["amount"] or 0)
            fixed += 1
    for bank_id, total in bank_totals.items():
        conn.execute("UPDATE bank_accounts SET balance = COALESCE(balance,0) + ? WHERE id=?",
                     (total, bank_id))
    conn.commit()
    conn.close()
    return fixed


def add_settlement_upload(filename, channel_id, row_count, file_total=0):
    """정산 파일 업로드 이력을 별도 테이블에 저장"""
    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS settlement_uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT, channel_id INTEGER, row_count INTEGER,
        file_total INTEGER DEFAULT 0,
        uploaded_at TEXT DEFAULT (datetime('now','localtime')))""")
    cur = conn.execute(
        "INSERT INTO settlement_uploads (filename, channel_id, row_count, file_total) VALUES (?,?,?,?)",
        (filename, channel_id, row_count, file_total))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_settlement_uploads(limit=100):
    """정산 파일 업로드 이력 조회 (최신 순)"""
    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS settlement_uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT, channel_id INTEGER, row_count INTEGER,
        file_total INTEGER DEFAULT 0,
        uploaded_at TEXT DEFAULT (datetime('now','localtime')))""")
    rows = conn.execute(
        """SELECT s.*, c.name as channel_name FROM settlement_uploads s
           LEFT JOIN channels c ON c.id=s.channel_id
           ORDER BY s.id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return rows


def get_insight_data(days=7):
    """대시보드 판매 인사이트 계산용 데이터"""
    from datetime import date, timedelta
    since = (date.today() - timedelta(days=days)).isoformat()
    conn = get_connection()

    # 상품별 판매량/매출/원가
    products = conn.execute("""
        SELECT o.product_name,
               SUM(o.qty) as total_qty,
               SUM(o.total_amount) as total_sales,
               SUM(COALESCE(p.cost_price,0) * o.qty) as total_cost
        FROM orders o
        LEFT JOIN products p ON p.name=o.product_name
        WHERE substr(COALESCE(o.order_date,''),1,10) >= ?
          AND COALESCE(o.status,'') NOT IN ('반품','취소')
        GROUP BY o.product_name
        ORDER BY total_qty DESC
    """, (since,)).fetchall()

    # 지출 합계
    expenses = conn.execute("""
        SELECT COALESCE(category,'기타') as category, SUM(amount) as total
        FROM expenses
        WHERE substr(COALESCE(date,''),1,10) >= ?
        GROUP BY category ORDER BY total DESC
    """, (since,)).fetchall()

    # 총 매출/이익
    totals = conn.execute("""
        SELECT SUM(o.total_amount) as sales,
               SUM(o.fee_amount) as fee,
               SUM(COALESCE(p.cost_price,0) * o.qty) as total_cost
        FROM orders o
        LEFT JOIN products p ON p.name=o.product_name
        WHERE substr(COALESCE(o.order_date,''),1,10) >= ?
          AND COALESCE(o.status,'') NOT IN ('반품','취소')
    """, (since,)).fetchone()
    conn.close()
    return dict(products=[dict(r) for r in products],
                expenses=[dict(r) for r in expenses],
                totals=dict(totals) if totals else {})


def get_insight_data_range(since, today):
    """인사이트 데이터 - 정확한 날짜 범위로 조회 (get_profit_by_period와 동일한 계산)"""
    conn = get_connection()
    products = conn.execute("""
        SELECT o.product_name, o.option_name,
               SUM(o.qty) as total_qty,
               SUM(o.total_amount) as total_sales,
               SUM(o.total_amount - o.fee_amount - COALESCE(p.cost_price,0)*o.qty) as profit,
               SUM(COALESCE(p.cost_price,0)*o.qty) as total_cost,
               MAX(CASE WHEN o.matched_product_id IS NOT NULL THEN 1 ELSE 0 END) as has_cost
        FROM orders o
        LEFT JOIN products p ON o.matched_product_id = p.id
        WHERE substr(COALESCE(o.order_date,''),1,10) BETWEEN ? AND ?
          AND COALESCE(o.status,'') NOT IN ('반품','취소')
        GROUP BY o.product_name
        ORDER BY total_qty DESC
    """, (since, today)).fetchall()

    expenses = conn.execute("""
        SELECT COALESCE(category,'기타') as category, SUM(amount) as total
        FROM expenses
        WHERE substr(COALESCE(date,''),1,10) BETWEEN ? AND ?
        GROUP BY category ORDER BY total DESC
    """, (since, today)).fetchall()
    conn.close()
    return dict(products=[dict(r) for r in products],
                expenses=[dict(r) for r in expenses],
                since=since, today=today)


def get_settlement_upload_linked_count(upload_id):
    """이 업로드로 만들어진 정산 입금 내역이 몇 건인지 (금액 합계도 함께)"""
    conn = get_connection()
    try:
        r = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as total "
            "FROM settlements WHERE settlement_upload_id=?", (upload_id,)).fetchone()
        result = (r["cnt"] or 0, r["total"] or 0)
    except sqlite3.Error:
        result = (0, 0)
    conn.close()
    return result


def get_settlements_by_upload(upload_id):
    """이 업로드로 만들어진 정산 입금 내역 목록"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT s.*, c.name as channel_name FROM settlements s
               LEFT JOIN channels c ON c.id = s.channel_id
               WHERE s.settlement_upload_id=? ORDER BY s.id DESC""", (upload_id,)).fetchall()
    except sqlite3.Error:
        rows = []
    conn.close()
    return rows


def delete_settlement_upload(upload_id, delete_settlements=False):
    """정산 파일 업로드 이력 삭제.

    delete_settlements=False : 업로드 이력만 지움 (등록된 정산 데이터는 그대로 남음)
    delete_settlements=True  : 이 업로드로 만들어진 정산 입금 내역까지 함께 지움
                               (통장으로 들어온 것으로 처리했던 금액은 잔액에서 되돌림)

    반환값: (지운 정산건수, 되돌린 금액)
    """
    conn = get_connection()
    deleted, reverted = 0, 0
    if delete_settlements:
        try:
            rows = conn.execute(
                "SELECT id, amount, bank_account_id FROM settlements WHERE settlement_upload_id=?",
                (upload_id,)).fetchall()
            bank_totals = {}
            for r in rows:
                amt = r["amount"] or 0
                if r["bank_account_id"]:
                    bank_totals[r["bank_account_id"]] = bank_totals.get(r["bank_account_id"], 0) + amt
                reverted += amt
                deleted += 1
            # 통장 잔액 되돌리기 (입금됐던 만큼 다시 빼줌)
            for bank_id, total in bank_totals.items():
                conn.execute(
                    "UPDATE bank_accounts SET balance = COALESCE(balance,0) - ? WHERE id=?",
                    (total, bank_id))
            conn.execute("DELETE FROM settlements WHERE settlement_upload_id=?", (upload_id,))
        except sqlite3.Error:
            deleted, reverted = 0, 0
    conn.execute("DELETE FROM settlement_uploads WHERE id=?", (upload_id,))
    conn.commit()
    conn.close()
    return deleted, reverted


# ---------------------------------------------------------------------------
# 배송비 수익 (수수료 제외 순액) - 채널별 집계
# ---------------------------------------------------------------------------
def get_channel_shipping_fee_rate(channel_id):
    """채널의 배송비 수수료율(%) 조회"""
    conn = get_connection()
    try:
        r = conn.execute("SELECT shipping_fee_rate FROM channels WHERE id=?", (channel_id,)).fetchone()
        rate = float(r[0]) if r and r[0] else 0.0
    except (sqlite3.Error, TypeError, ValueError):
        rate = 0.0
    conn.close()
    return rate


def set_channel_shipping_fee_rate(channel_id, rate):
    """채널의 배송비 수수료율(%) 저장. 저장 후 기존 주문의 순배송수익도 다시 계산해줌"""
    conn = get_connection()
    conn.execute("UPDATE channels SET shipping_fee_rate=? WHERE id=?", (float(rate or 0), channel_id))
    conn.commit()
    conn.close()
    clear_shipping_rate_cache()
    return recalc_shipping_revenue(channel_id=channel_id)


def get_all_channel_shipping_rates():
    """모든 채널의 배송비 수수료율 목록 (설정 화면용)"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, name, COALESCE(channel_type,'온라인채널') as channel_type,
                  COALESCE(shipping_fee_rate,0) as shipping_fee_rate
           FROM channels ORDER BY name"""
    ).fetchall()
    conn.close()
    return rows


def recalc_shipping_revenue(channel_id=None):
    """주문에 저장된 배송비 순수익(수수료 제외)을 채널 수수료율 기준으로 다시 계산.
    수수료율을 바꾸거나, 예전 버전에서 넘어온 데이터를 정리할 때 사용.
    반환값: 갱신된 주문 건수"""
    conn = get_connection()
    if channel_id:
        rows = conn.execute(
            "SELECT id, channel_id, shipping_fee FROM orders "
            "WHERE channel_id=? AND COALESCE(shipping_fee,0) <> 0", (channel_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, channel_id, shipping_fee FROM orders "
            "WHERE COALESCE(shipping_fee,0) <> 0").fetchall()

    rate_cache = {}
    updates = []
    for r in rows:
        cid = r["channel_id"]
        if cid not in rate_cache:
            rr = conn.execute("SELECT shipping_fee_rate FROM channels WHERE id=?", (cid,)).fetchone()
            try:
                rate_cache[cid] = float(rr[0]) if rr and rr[0] else 0.0
            except (TypeError, ValueError):
                rate_cache[cid] = 0.0
        rate = rate_cache[cid]
        charge, net = calc_shipping_parts(r["shipping_fee"], rate)
        updates.append((rate, charge, net, r["id"]))

    if updates:
        conn.executemany(
            "UPDATE orders SET shipping_fee_rate=?, shipping_fee_charge=?, shipping_net=? WHERE id=?",
            updates)
    # 배송비가 0인 건은 순액도 0으로 정리
    conn.execute("UPDATE orders SET shipping_fee_charge=0, shipping_net=0 "
                 "WHERE COALESCE(shipping_fee,0) = 0")
    conn.commit()
    conn.close()
    return len(updates)


def _shipping_where(date_from, date_to, channel_id=None, alias="o"):
    where = [f"COALESCE({alias}.shipping_fee,0) <> 0"]
    params = []
    if date_from:
        where.append(f"substr(COALESCE({alias}.order_date,''),1,10) >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"substr(COALESCE({alias}.order_date,''),1,10) <= ?")
        params.append(date_to)
    if channel_id:
        where.append(f"{alias}.channel_id = ?")
        params.append(channel_id)
    return "WHERE " + " AND ".join(where), params


def get_shipping_summary_by_channel(date_from=None, date_to=None):
    """채널별 배송비 발생 현황.
    반환 컬럼: channel_id, channel_name, channel_type, order_count,
              shipping_total(고객에게 받은 배송비 총액),
              shipping_charge(배송비에 붙은 수수료),
              shipping_net(수수료 뺀 순수익), rate(적용 수수료율)"""
    clause, params = _shipping_where(date_from, date_to)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT o.channel_id as channel_id,
               COALESCE(ch.name, '(채널없음)') as channel_name,
               COALESCE(ch.channel_type, '온라인채널') as channel_type,
               COALESCE(ch.shipping_fee_rate, 0) as rate,
               COUNT(o.id) as order_count,
               COALESCE(SUM(o.shipping_fee), 0) as shipping_total,
               COALESCE(SUM(o.shipping_fee_charge), 0) as shipping_charge,
               COALESCE(SUM(o.shipping_net), 0) as shipping_net
        FROM orders o
        LEFT JOIN channels ch ON ch.id = o.channel_id
        {clause}
        GROUP BY o.channel_id
        ORDER BY shipping_net DESC
    """, params).fetchall()
    conn.close()
    return rows


def get_shipping_summary_by_period(period="month", date_from=None, date_to=None, channel_id=None):
    """기간(일/월/년)별 배송비 발생 현황"""
    n = _PERIOD_LEN.get(period, 7)
    clause, params = _shipping_where(date_from, date_to, channel_id)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT substr(COALESCE(o.order_date,''), 1, {n}) as period_key,
               COUNT(o.id) as order_count,
               COALESCE(SUM(o.shipping_fee), 0) as shipping_total,
               COALESCE(SUM(o.shipping_fee_charge), 0) as shipping_charge,
               COALESCE(SUM(o.shipping_net), 0) as shipping_net
        FROM orders o
        {clause}
        GROUP BY period_key
        ORDER BY period_key DESC
    """, params).fetchall()
    conn.close()
    return rows


def get_shipping_orders(channel_id=None, date_from=None, date_to=None, limit=1000):
    """배송비가 발생한 주문 상세 목록 (채널별 배송비 화면에서 더블클릭 시 사용)"""
    clause, params = _shipping_where(date_from, date_to, channel_id)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT o.id, o.order_date, o.order_no, o.product_name, o.option_name,
               o.buyer_name, o.qty, o.total_amount,
               COALESCE(o.shipping_fee,0) as shipping_fee,
               COALESCE(o.shipping_fee_charge,0) as shipping_fee_charge,
               COALESCE(o.shipping_net,0) as shipping_net,
               COALESCE(o.shipping_fee_rate,0) as shipping_fee_rate,
               COALESCE(ch.name,'(채널없음)') as channel_name
        FROM orders o
        LEFT JOIN channels ch ON ch.id = o.channel_id
        {clause}
        ORDER BY o.order_date DESC, o.id DESC
        LIMIT ?
    """, params + [limit]).fetchall()
    conn.close()
    return rows


def get_shipping_total(date_from=None, date_to=None, channel_id=None):
    """기간 전체 배송비 합계 (대시보드/요약 표시용)"""
    clause, params = _shipping_where(date_from, date_to, channel_id)
    conn = get_connection()
    r = conn.execute(f"""
        SELECT COUNT(o.id) as order_count,
               COALESCE(SUM(o.shipping_fee), 0) as shipping_total,
               COALESCE(SUM(o.shipping_fee_charge), 0) as shipping_charge,
               COALESCE(SUM(o.shipping_net), 0) as shipping_net
        FROM orders o {clause}
    """, params).fetchone()
    conn.close()
    return dict(r) if r else {"order_count": 0, "shipping_total": 0,
                              "shipping_charge": 0, "shipping_net": 0}


# ---------------------------------------------------------------------------
# 통장간 자금이동(이체)
#   · 보내는 통장에서 (금액 + 이체수수료)를 빼고, 받는 통장에 금액을 더함
#   · 회사 내부에서 돈이 옮겨가는 것이므로 매출/지출로는 잡지 않음
#     (다만 이체수수료는 실제로 나간 돈이라 합계에서 빠짐)
# ---------------------------------------------------------------------------
def add_bank_transfer(transfer_date, from_bank_id, to_bank_id, amount, fee=0, memo=""):
    """통장간 이체를 기록하고 양쪽 잔액을 실제로 반영"""
    amount = int(amount or 0)
    fee = int(fee or 0)
    if not from_bank_id or not to_bank_id:
        raise ValueError("보내는 통장과 받는 통장을 모두 골라주세요.")
    if from_bank_id == to_bank_id:
        raise ValueError("보내는 통장과 받는 통장이 같습니다.")
    if amount <= 0:
        raise ValueError("이체 금액은 0보다 커야 합니다.")

    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO bank_transfers
             (transfer_date, from_bank_id, to_bank_id, amount, fee, memo)
           VALUES (?,?,?,?,?,?)""",
        (transfer_date, from_bank_id, to_bank_id, amount, fee, memo))
    new_id = cur.lastrowid
    # 보내는 통장: 금액 + 수수료 차감 / 받는 통장: 금액 입금
    conn.execute("UPDATE bank_accounts SET balance = COALESCE(balance,0) - ? WHERE id=?",
                 (amount + fee, from_bank_id))
    conn.execute("UPDATE bank_accounts SET balance = COALESCE(balance,0) + ? WHERE id=?",
                 (amount, to_bank_id))
    conn.commit()
    conn.close()
    return new_id


def get_bank_transfers(limit=200, bank_account_id=None):
    """이체 내역 조회. bank_account_id를 주면 그 통장이 보내거나 받은 건만"""
    conn = get_connection()
    where, params = "", []
    if bank_account_id:
        where = "WHERE t.from_bank_id=? OR t.to_bank_id=?"
        params = [bank_account_id, bank_account_id]
    rows = conn.execute(f"""
        SELECT t.*,
               COALESCE(NULLIF(TRIM(f.bank_name),''), f.name) as from_name,
               COALESCE(NULLIF(TRIM(o.bank_name),''), o.name) as to_name
        FROM bank_transfers t
        LEFT JOIN bank_accounts f ON f.id = t.from_bank_id
        LEFT JOIN bank_accounts o ON o.id = t.to_bank_id
        {where}
        ORDER BY t.transfer_date DESC, t.id DESC
        LIMIT ?
    """, params + [limit]).fetchall()
    conn.close()
    return rows


def delete_bank_transfer(transfer_id):
    """이체 기록을 지우고 양쪽 통장 잔액을 원래대로 되돌림"""
    conn = get_connection()
    r = conn.execute("SELECT * FROM bank_transfers WHERE id=?", (transfer_id,)).fetchone()
    if r:
        amount = r["amount"] or 0
        fee = r["fee"] or 0
        # 되돌리기: 보낸 통장에 다시 넣고, 받은 통장에서 다시 뺌
        conn.execute("UPDATE bank_accounts SET balance = COALESCE(balance,0) + ? WHERE id=?",
                     (amount + fee, r["from_bank_id"]))
        conn.execute("UPDATE bank_accounts SET balance = COALESCE(balance,0) - ? WHERE id=?",
                     (amount, r["to_bank_id"]))
        conn.execute("DELETE FROM bank_transfers WHERE id=?", (transfer_id,))
        conn.commit()
    conn.close()


def get_transfer_fee_total(date_from=None, date_to=None):
    """기간 내 이체수수료 합계 (실제로 빠져나간 돈)"""
    conn = get_connection()
    where, params = [], []
    if date_from:
        where.append("substr(COALESCE(transfer_date,''),1,10) >= ?")
        params.append(date_from)
    if date_to:
        where.append("substr(COALESCE(transfer_date,''),1,10) <= ?")
        params.append(date_to)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    r = conn.execute(f"SELECT COALESCE(SUM(fee),0) as total FROM bank_transfers {clause}",
                     params).fetchone()
    conn.close()
    return r["total"] if r else 0


# ---------------------------------------------------------------------------
# 매입가(원가) 변동 이력
# ---------------------------------------------------------------------------
def get_cost_history(product_id=None, limit=500):
    """원가 변동 이력 조회. product_id를 주면 그 품목 것만"""
    conn = get_connection()
    where, params = "", []
    if product_id:
        where = "WHERE h.product_id = ?"
        params = [product_id]
    rows = conn.execute(f"""
        SELECT h.*, p.name as product_name, COALESCE(p.option_name,'') as option_name,
               COALESCE(p.sku,'') as sku
        FROM cost_history h
        LEFT JOIN products p ON p.id = h.product_id
        {where}
        ORDER BY h.changed_at DESC, h.id DESC
        LIMIT ?
    """, params + [limit]).fetchall()
    conn.close()
    return rows


def get_cost_change_count(product_id=None):
    """원가 변동 건수 (요약 표시용)"""
    conn = get_connection()
    if product_id:
        r = conn.execute("SELECT COUNT(*) as c FROM cost_history WHERE product_id=?",
                         (product_id,)).fetchone()
    else:
        r = conn.execute("SELECT COUNT(*) as c FROM cost_history").fetchone()
    conn.close()
    return r["c"] if r else 0


def add_cost_history(product_id, old_cost, new_cost, source="수동 기록", memo=""):
    """원가 변동을 직접 기록 (update_product를 거치지 않는 경로용)"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO cost_history (product_id, old_cost, new_cost, source, memo)
           VALUES (?,?,?,?,?)""",
        (product_id, float(old_cost or 0), float(new_cost or 0), source, memo))
    conn.commit()
    conn.close()


def fix_negative_fees():
    """이미 저장된 주문 중 수수료가 음수로 들어간 건을 양수로 바로잡음.

    마켓 파일은 수수료를 차감 항목이라 음수로 적는데, 예전 버전이 그걸
    그대로 저장해서 이익이 실제보다 부풀려 계산되던 문제를 정리하는 용도.
    (정산예정금액은 파일에서 읽은 값이라 건드리지 않음)
    반환: 바로잡은 건수
    """
    conn = get_connection()
    cur = conn.execute(
        "UPDATE orders SET fee_amount = -fee_amount WHERE COALESCE(fee_amount,0) < 0")
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def count_negative_fees():
    """수수료가 음수로 저장된 주문 건수와 합계"""
    conn = get_connection()
    r = conn.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(fee_amount),0) as total "
        "FROM orders WHERE COALESCE(fee_amount,0) < 0").fetchone()
    conn.close()
    return (r["cnt"] or 0, r["total"] or 0)


def get_last_data_update():
    """장부에 들어있는 자료 중 가장 최근 날짜들을 모아서 돌려줌.
    프로그램을 켤 때 '어디까지 입력돼 있는지' 한눈에 확인하는 용도"""
    conn = get_connection()

    def _max(sql):
        try:
            r = conn.execute(sql).fetchone()
            return (r[0] or "")[:10] if r and r[0] else ""
        except sqlite3.Error:
            return ""

    result = {
        "order": _max("SELECT MAX(substr(order_date,1,10)) FROM orders"),
        "purchase": _max("SELECT MAX(substr(purchase_date,1,10)) FROM purchases"),
        "settlement": _max("SELECT MAX(substr(settle_date,1,10)) FROM settlements"),
        "expense": _max("SELECT MAX(substr(date,1,10)) FROM expenses"),
        "upload": _max("SELECT MAX(substr(uploaded_at,1,10)) FROM upload_history"),
    }
    try:
        r = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        result["order_count"] = r[0] if r else 0
    except sqlite3.Error:
        result["order_count"] = 0
    # 마지막으로 자료가 들어온 실제 시각 (날짜 + 시간)
    stamps = []
    for sql in ("SELECT MAX(uploaded_at) FROM upload_history",
                "SELECT MAX(uploaded_at) FROM settlement_uploads",
                "SELECT MAX(changed_at) FROM cost_history",
                "SELECT MAX(created_at) FROM bank_transfers"):
        try:
            r = conn.execute(sql).fetchone()
            if r and r[0]:
                stamps.append(str(r[0]))
        except sqlite3.Error:
            continue
    # 기록된 시각이 하나도 없으면(수기 입력만 한 경우) DB 파일이 마지막으로
    # 바뀐 시각을 대신 사용
    if not stamps:
        try:
            import os as _os
            from datetime import datetime as _dt
            mtime = _os.path.getmtime(DB_PATH)
            stamps.append(_dt.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
    result["last_saved_at"] = max(stamps)[:19] if stamps else ""
    conn.close()
    return result
