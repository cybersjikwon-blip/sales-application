# -*- coding: utf-8 -*-
"""
api_connectors.py
각 판매채널(스마트스토어/11번가/쿠팡/ESM)의 오픈API 연동을 위한 기본 틀(스켈레톤).

⚠️ 이 파일은 아직 "설계도"입니다. 실제로 동작하는 코드가 아니라,
나중에 각 마켓의 API 키를 발급받은 뒤 채워 넣을 자리를 미리 만들어둔 것입니다.
아래 각 클래스의 메서드 안 TODO 주석을 실제 API 호출 코드로 교체하면 됩니다.

=====================================================================
■ 왜 지금 당장 "완성된" 연동을 만들 수 없는가?
=====================================================================
1. 각 마켓은 서로 완전히 다른 API 체계를 씁니다:
   - 스마트스토어: 네이버 커머스API센터에서 발급받는 애플리케이션 ID/Secret으로
     OAuth2 client_credentials 방식 인증 (문서: https://apicenter.commerce.naver.com)
   - 11번가: Open API 신청 후 발급되는 API Key를 헤더에 실어 호출하는 방식
     (문서: https://openapi.11st.co.kr)
   - 쿠팡: WING(쿠팡윙)에서 Open API 신청 -> Access Key/Secret Key로
     HMAC 서명을 만들어 요청마다 서명해야 함 (문서: https://developers.coupangcorp.com)
   - ESM(지마켓/옥션): ESM PLUS 오픈API -> 별도 인증서/키 발급 필요
     (문서는 이베이코리아 판매자 문의를 통해 확인 필요)

2. 이 API들은 전부 "사업자 등록 + 각 마켓 판매자 계정으로 로그인해서 개발자센터에서
   직접 신청"해야 발급됩니다. 즉, 사장님이 아래 절차를 먼저 진행하셔야 합니다:
   - 각 마켓 셀러센터(스마트스토어센터/11번가 셀러오피스/쿠팡 WING/ESM PLUS)에 로그인
   - "오픈API" 또는 "개발자센터" 메뉴에서 앱 등록/API 이용 신청
   - 승인 후 발급되는 Client ID / Secret Key / Access Key 등을 안전하게 보관

3. API마다 "할 수 있는 일"이 다릅니다. 예를 들어 재고 수정(푸시)은 지원해도
   정산 내역 조회는 지원하지 않거나, 조회 가능한 기간에 제한이 있는 경우가 많습니다.
   실제 연동 전에 각 마켓 문서에서 "주문 조회/정산 조회/재고 수정/발송 처리" 각각의
   엔드포인트가 있는지 반드시 확인이 필요합니다.

4. 보안: API Key/Secret은 절대 코드에 하드코딩하면 안 되고, 이 프로그램에서는
   설정(SettingsTab)에 입력받아 로컬 DB나 OS 자격증명 저장소에 암호화해서
   보관하는 방식으로 확장하는 게 좋습니다. (지금은 그 저장 UI도 아직 없습니다)

=====================================================================
■ 지금 이 파일이 해두는 일
=====================================================================
- 모든 마켓이 공통으로 구현해야 할 동작(주문 조회, 정산 조회, 재고 조회/수정,
  발송처리)을 추상 인터페이스로 정의해뒀습니다.
- 마켓별 클래스는 일단 틀만 있고, 실제 호출부는 TODO로 남겨뒀습니다.
- 나중에 API 키가 준비되면 해당 클래스의 __init__과 각 메서드만 채우면 되고,
  main.py 쪽 UI/DB 로직은 이미 있는 importer.py / database.py 구조를 거의
  그대로 재사용할 수 있도록 반환 형식을 기존 주문 스키마와 맞춰뒀습니다.
"""
from abc import ABC, abstractmethod


class MarketplaceAPIClient(ABC):
    """모든 마켓 API 연동 클래스가 공통으로 구현해야 하는 인터페이스"""

    def __init__(self, client_id: str = "", client_secret: str = "", access_token: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token

    @abstractmethod
    def authenticate(self):
        """API 인증을 수행하고 access_token(또는 서명에 필요한 값)을 준비.
        반환: True/False (성공 여부)"""
        raise NotImplementedError

    @abstractmethod
    def fetch_orders(self, date_from: str, date_to: str) -> list:
        """기간 내 주문 목록을 가져와 importer.py의 표준 주문 스키마
        (order_no/order_date/product_name/option_name/qty/sale_price/
        total_amount/fee_amount/shipping_fee/settlement_amount/buyer_name/
        status/memo)에 맞는 dict 리스트로 반환"""
        raise NotImplementedError

    @abstractmethod
    def fetch_settlement(self, date_from: str, date_to: str) -> list:
        """기간 내 정산 내역을 가져와 importer.py의 정산 스키마
        (order_no/buyer_name/product_name/settle_amount/settle_date)에
        맞는 dict 리스트로 반환"""
        raise NotImplementedError

    @abstractmethod
    def fetch_inventory(self) -> list:
        """마켓에 등록된 상품별 현재 재고 목록 조회.
        반환 예: [{"product_code":.., "name":.., "stock_qty":..}, ...]"""
        raise NotImplementedError

    @abstractmethod
    def push_inventory(self, product_code: str, stock_qty: int) -> bool:
        """마켓 상품의 재고수량을 업데이트(반영). 반환: 성공 여부"""
        raise NotImplementedError

    @abstractmethod
    def update_shipment(self, order_no: str, tracking_no: str, carrier: str) -> bool:
        """주문에 송장번호/택배사 정보를 등록해서 발송 처리. 반환: 성공 여부"""
        raise NotImplementedError


class SmartStoreAPIClient(MarketplaceAPIClient):
    """네이버 커머스API센터 (https://apicenter.commerce.naver.com)
    인증: OAuth2 client_credentials (Client ID/Secret 필요)"""

    def authenticate(self):
        # TODO: POST https://api.commerce.naver.com/external/v1/oauth2/token
        #       client_id, client_secret, grant_type=client_credentials 로 access_token 발급
        raise NotImplementedError("스마트스토어 API 연동은 아직 구현되지 않았습니다 (API 키 필요)")

    def fetch_orders(self, date_from, date_to):
        # TODO: GET /external/v1/pay-order/seller/product-orders (기간/상태별 조회)
        raise NotImplementedError

    def fetch_settlement(self, date_from, date_to):
        # TODO: 정산 관련 엔드포인트 확인 필요 (판매자 정산 내역 조회 API)
        raise NotImplementedError

    def fetch_inventory(self):
        # TODO: GET /external/v2/products/origin-products (상품 목록/재고 조회)
        raise NotImplementedError

    def push_inventory(self, product_code, stock_qty):
        # TODO: PUT /external/v2/products/origin-products/{originProductNo} (재고 수정)
        raise NotImplementedError

    def update_shipment(self, order_no, tracking_no, carrier):
        # TODO: POST /external/v1/pay-order/seller/product-orders/{no}/dispatch
        raise NotImplementedError


class ElevenStAPIClient(MarketplaceAPIClient):
    """11번가 Open API (https://openapi.11st.co.kr)
    인증: 발급받은 API Key를 요청 헤더/쿼리에 포함"""

    def authenticate(self):
        raise NotImplementedError("11번가 API 연동은 아직 구현되지 않았습니다 (API 키 필요)")

    def fetch_orders(self, date_from, date_to):
        # TODO: 주문/배송 조회 API (오픈마켓 셀러오피스 문서 참고)
        raise NotImplementedError

    def fetch_settlement(self, date_from, date_to):
        raise NotImplementedError

    def fetch_inventory(self):
        raise NotImplementedError

    def push_inventory(self, product_code, stock_qty):
        raise NotImplementedError

    def update_shipment(self, order_no, tracking_no, carrier):
        raise NotImplementedError


class CoupangAPIClient(MarketplaceAPIClient):
    """쿠팡 WING Open API (https://developers.coupangcorp.com)
    인증: Access Key/Secret Key로 매 요청마다 HMAC 서명 필요 (가장 까다로움)"""

    def authenticate(self):
        raise NotImplementedError("쿠팡 API 연동은 아직 구현되지 않았습니다 (Access/Secret Key 필요)")

    def fetch_orders(self, date_from, date_to):
        # TODO: GET /v2/providers/openapi/apis/api/v4/vendors/{vendorId}/ordersheets
        raise NotImplementedError

    def fetch_settlement(self, date_from, date_to):
        raise NotImplementedError

    def fetch_inventory(self):
        raise NotImplementedError

    def push_inventory(self, product_code, stock_qty):
        raise NotImplementedError

    def update_shipment(self, order_no, tracking_no, carrier):
        raise NotImplementedError


class ESMAPIClient(MarketplaceAPIClient):
    """ESM PLUS(지마켓/옥션) Open API - 판매자 문의를 통한 별도 신청 필요"""

    def authenticate(self):
        raise NotImplementedError("ESM API 연동은 아직 구현되지 않았습니다 (인증키 필요)")

    def fetch_orders(self, date_from, date_to):
        raise NotImplementedError

    def fetch_settlement(self, date_from, date_to):
        raise NotImplementedError

    def fetch_inventory(self):
        raise NotImplementedError

    def push_inventory(self, product_code, stock_qty):
        raise NotImplementedError

    def update_shipment(self, order_no, tracking_no, carrier):
        raise NotImplementedError


CLIENT_MAP = {
    "스마트스토어": SmartStoreAPIClient,
    "11번가": ElevenStAPIClient,
    "쿠팡": CoupangAPIClient,
    "ESM(G마켓/옥션)": ESMAPIClient,
}


def get_api_client(channel_name: str, **credentials):
    """채널명으로 알맞은 API 클라이언트 인스턴스를 생성해서 반환.
    credentials: client_id, client_secret, access_token 등 (마켓마다 다름)"""
    cls = CLIENT_MAP.get(channel_name)
    if cls is None:
        raise ValueError(f"'{channel_name}'에 대한 API 클라이언트가 없습니다.")
    return cls(**credentials)
