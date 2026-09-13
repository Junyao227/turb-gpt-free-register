# Paylink Service

This is the maintained OPLL2-based local paylink service. It keeps the OPLL2
operator console and adds a compatibility API for the registration project.

## First Release Providers

- `pix`
- `upi`
- `kakao_pay` (implemented by OPLL2's native `korea` provider)
- `twint` (implemented by OPLL2's native `swiss` provider, CH / CHF)
- `ideal`
- `gcash` (native `gcash`, PH / PHP)
- `gopay` (native approval flow, ID / IDR; operator tracking uses Tasks)
- `grabpay` (native approval flow, PH / PHP; operator tracking uses Tasks)
- `paypal` (standard Checkout link; selectable US / USD, Thailand / THB, or Brazil / BRL profile)

Provider switches and their non-secret country/locale settings are in
`config/providers.ini`. Keep proxy credentials and other secrets in `.env`;
start from `.env.example`.

## PayPal Regional Profiles

PayPal remains a Checkout-link provider: it returns the Checkout URL only and
does not create a payment method or submit a payment. Select its active country
from the Paylink Settings page, or edit `[providers.paypal]` in
`config/providers.ini`:

```ini
[providers.paypal]
enabled = true
country = TH
locale = th
```

The supported profiles are `US` / `en` / `USD`, `TH` / `th` / `THB`, and
`BR` / `pt-BR` / `BRL`. The selected profile determines the Checkout billing
country, locale, currency, and dedicated proxy source. It is explicit: proxy
text never determines the country.

Use `OPENAI_PAY_PAYPAL_PROXY` and `OPENAI_PAY_PAYPAL_PROXY_POOL` for the
default US profile. Thailand uses `OPENAI_PAY_PAYPAL_TH_PROXY` and
`OPENAI_PAY_PAYPAL_TH_PROXY_POOL`; Brazil uses
`OPENAI_PAY_PAYPAL_BR_PROXY` and `OPENAI_PAY_PAYPAL_BR_PROXY_POOL`. Keep all
proxy values in `.env`, not in `providers.ini`.

Provider proxy configuration is stage-based:

- `checkout`: creates the OpenAI Checkout session.
- `promotion`: the trial / promo leg. Internally this calls
  `/backend-api/payments/checkout/update`, but it is a separate promotion pool,
  not a second Checkout creation pool.
- `provider`: initializes Stripe and creates/confirms the provider payment
  method.
- `approve`: calls OpenAI Checkout approve; if not configured it falls back to
  `provider`.

The legacy provider keys above remain the `provider` stage. Stage-specific
overrides use `OPENAI_PAY_<SCOPE>_<STAGE>_PROXY(_POOL)`, for example
`OPENAI_PAY_INDIA_PROMOTION_PROXY_POOL` for UPI's VN promo leg or
`OPENAI_PAY_PAYPAL_TH_PROMOTION_PROXY_POOL` for the Thailand PayPal promo leg.

## Run Locally

```powershell
cd services\paylink
D:\Python38\python.exe -m pip install -r requirements.txt
D:\Python38\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8787 --no-access-log
```

The console is available at `http://127.0.0.1:8787/` and the health check is
`http://127.0.0.1:8787/api/health`.

To use Docker instead:

```powershell
docker compose up --build -d
```

## Registration-Project Configuration

Set the following in the root project's extract-link configuration:

```ini
EXTRACT_LINK_API_BASE=http://127.0.0.1:8787
```

It exposes `POST /api/extract` and `GET /api/jobs/{job_id}/events`.
