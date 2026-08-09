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
- `paypal` (standard Checkout link, US / USD)

Provider switches and their non-secret country/locale settings are in
`config/providers.ini`. Keep proxy credentials and other secrets in `.env`;
start from `.env.example`.

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
