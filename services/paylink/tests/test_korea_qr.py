from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from korea_qr import extract_kakao_bridge_url, parse_payweb_url


def test_extract_kakao_bridge_url():
    html = """
    <script>
    location.href = 'https://online-payment.kakaopay.com/bridge/pc/reseller/subscription/payment-issue/abc123hash';
    </script>
    """
    assert (
        extract_kakao_bridge_url(html)
        == "https://online-payment.kakaopay.com/bridge/pc/reseller/subscription/payment-issue/abc123hash"
    )


def test_parse_payweb_url():
    app_url = (
        "kakaotalk://kakaopay/pg?"
        "payweb_talk_min_version=11.3.0&"
        "payweb_url=https%3A%2F%2Fonline-payment.kakaopay.com%2Fpay%2Fpc%2Freseller%2Fsubscription%2Fpayment-issue%2Fabc123&"
        "url=https://online-pay.kakaopay.com/pay/r1/abc123"
    )
    assert (
        parse_payweb_url(app_url)
        == "https://online-payment.kakaopay.com/pay/pc/reseller/subscription/payment-issue/abc123"
    )
