from __future__ import annotations

import html
import io
import re
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlsplit

import requests
import segno

KAKAO_BRIDGE_PATTERN = re.compile(
    r"https://online-payment\.kakaopay\.com/bridge/pc/reseller/subscription/payment-issue/[A-Za-z0-9]+"
)
HIDDEN_INPUT_PATTERN = re.compile(
    r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"',
    re.IGNORECASE,
)


def extract_hidden_inputs(document: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for name, value in HIDDEN_INPUT_PATTERN.findall(document or ""):
        values[name] = html.unescape(value)
    return values


def extract_kakao_bridge_url(document: str) -> str:
    match = KAKAO_BRIDGE_PATTERN.search(document or "")
    return str(match.group(0) if match else "").strip()


def parse_payweb_url(app_url: str) -> str:
    parsed = urlsplit(str(app_url or "").strip())
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return unquote(str(query.get("payweb_url") or "").strip())


def render_qr_svg(qr_value: str) -> str:
    buffer = io.BytesIO()
    segno.make(qr_value, error="m").save(buffer, kind="svg", scale=6, border=2)
    return buffer.getvalue().decode("utf-8")


def build_korea_qr_bundle(
    *,
    provider_url: str,
    user_agent: str,
    proxy: str = "",
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": str(user_agent or "").strip(),
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}

    provider_html = session.get(provider_url, timeout=timeout_seconds).text
    payment_bootstrap = extract_hidden_inputs(provider_html)
    payment_form = {
        key: value
        for key, value in payment_bootstrap.items()
        if key
        in {
            "PayMethod",
            "Moid",
            "Amt",
            "GoodsName",
            "ReturnURL",
            "MID",
            "TransType",
            "CurrencyCode",
            "CharSet",
            "SupplyAmt",
            "GoodsVat",
            "ServiceAmt",
            "TaxFreeAmt",
            "DirectShowOpt",
            "NPDisableScroll",
            "NicepayReserved",
            "ServiceCode",
            "BillAuthYN",
            "EdiDate",
            "SignData",
            "sessionId",
            "VerifySType",
            "EncGoodsName",
            "EncBuyerName",
            "NpDirectYn",
            "NpDirectLayer",
            "NpForwardNew",
            "JsVer",
            "NpSvcType",
            "DeployedVer",
            "DeployedDate",
            "DeployedFileName",
            "EncVbankAccountName",
        }
    }
    payment_html = session.post(
        "https://web.nicepay.co.kr/v3/v3Payment.jsp",
        data=payment_form,
        timeout=timeout_seconds,
    ).text
    payment_data = extract_hidden_inputs(payment_html)
    payment_direct_form = {
        "token": payment_data.get("token", ""),
        "NpLang": payment_data.get("NpLang", "ko"),
        "SkinType": payment_data.get("SkinType", ""),
        "LogoImage": payment_data.get("LogoImage", ""),
        "DeployedDate": payment_data.get("DeployedDate", ""),
        "ConnType": payment_data.get("ConnType", ""),
        "PayMethod": payment_data.get("PayMethod", "CARD"),
        "NpDirectLayer": payment_data.get("NpDirectLayer", "Y"),
        "AuthSignData": payment_data.get("AuthSignData", ""),
        "BillAuthType": payment_data.get("BillAuthType", "CARDBILL"),
        "ServiceCode": payment_data.get("ServiceCode", "UNTACT"),
        "RenewalYN": payment_data.get("RenewalYN", "Y"),
    }
    session.post(
        "https://web.nicepay.co.kr/v3/webstd/billing/paymentDirect.jsp",
        data=payment_direct_form,
        timeout=timeout_seconds,
    )
    auth_history = session.post(
        "https://web.nicepay.co.kr/v3/api/auth_history.jsp",
        data={
            "token": payment_data.get("token", ""),
            "apiType": "GET",
            "callFromIdx": "Y",
            "svcType": "01",
        },
        timeout=timeout_seconds,
    ).json()
    basis = session.post(
        "https://web.nicepay.co.kr/v3/api/basisinfo/paymain_basis.jsp",
        data={
            "MID": auth_history.get("MID", ""),
            "PayMethod": auth_history.get("PayMethod", "CARD"),
            "Amt": auth_history.get("Amt", ""),
            "TransType": auth_history.get("TransType", "0"),
            "EscrowOnly": "",
            "ConnType": "",
            "GoodsCl": "",
            "token": auth_history.get("token", ""),
            "SvcType": auth_history.get("SvcType", "01"),
            "IntfVer": "V3",
            "CurrencyCode": auth_history.get("CurrencyCode", "KRW"),
            "BillAuthYN": auth_history.get("BillAuthYN", "Y"),
        },
        timeout=timeout_seconds,
    ).json()
    verify_html = session.get(
        "https://web.nicepay.co.kr/v3/webstd/auth/easypay/kakao/verify_kakao.jsp",
        params={
            "token": auth_history.get("token", ""),
            "PartSvcCd": str((basis.get("EasyPayList") or [{}])[0].get("part_svc_cd") or "E016"),
            "NpDirectLayer": "Y",
            "MID": auth_history.get("MID", ""),
            "TotalAmt": auth_history.get("Amt", ""),
            "TaxFreeAmt": auth_history.get("TaxFreeAmt", ""),
            "GoodsVat": auth_history.get("GoodsVat", ""),
            "ServiceAmt": auth_history.get("ServiceAmt", ""),
            "GoodsName": quote(str(auth_history.get("GoodsName", "")), safe=""),
            "SvcType": auth_history.get("SvcType", "01"),
            "CupDepositAmt": "",
        },
        timeout=timeout_seconds,
    ).text
    bridge_url = extract_kakao_bridge_url(verify_html)
    if not bridge_url:
        raise RuntimeError("kakao bridge url missing")
    bridge_hash = bridge_url.rstrip("/").split("/")[-1]
    bridge = session.get(
        f"https://pay-api-gw.kakaopay.com/online-payment-internal/v2/reseller/subscription/payment-issue/{bridge_hash}/pc/bridge",
        timeout=timeout_seconds,
    ).json()
    qr_status = session.get(
        f"https://pay-api-gw.kakaopay.com/online-payment-internal/v2/reseller/subscription/payment-issue/{bridge_hash}/qr/status",
        timeout=timeout_seconds,
    ).json()
    qr_value = parse_payweb_url(str(bridge.get("ios_app_url") or "")) or bridge_url
    return {
        "bridge_url": bridge_url,
        "bridge_hash": bridge_hash,
        "qr_url": qr_value,
        "qr_svg": render_qr_svg(qr_value),
        "expired_at": int(bridge.get("expired_timestamp") or 0),
        "expired": bool(qr_status.get("expired") or bridge.get("expired")),
        "status": str(qr_status.get("status") or bridge.get("status") or ""),
        "ios_app_url": str(bridge.get("ios_app_url") or ""),
        "aos_app_url": str(bridge.get("aos_app_url") or ""),
        "kakao_tid": str(bridge.get("tid") or ""),
    }
