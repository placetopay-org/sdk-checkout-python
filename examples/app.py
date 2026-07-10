"""All-in-one FastAPI playground for the PlaceToPay Python SDK.

Single-page UI with forms for every endpoint the SDK exposes:

    1. Connect  — enter merchant credentials (held in memory only)
    2. Create session
    3. Query session
    4. Cancel session
    5. Collect (direct charge)
    6. Reverse
    7. Invalidate token

All operations POST to JSON endpoints; the HTML page renders results inline
via ``fetch``. Credentials never touch disk, never log; they live only in
this process's memory and are cleared on disconnect / server restart.
"""

from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from pydantic import ValidationError as PydanticValidationError

from placetopay.checkout import (
    Checkout,
    Country,
    Environment,
    PlaceToPayError,
    Settings,
)

# ─── Module-level state: creds live only in this process's memory ─────
_client: Checkout | None = None
_config_display: dict[str, str] | None = None
# Optional preseed from env vars (dev convenience only — never required).
_PRESEED_LOGIN: str = os.environ.get("PLACETOPAY_LOGIN", "")


def _connect(
    login: str,
    secret_key: str,
    environment: str,
    country: str | None,
    custom_base_url: str | None,
) -> None:
    global _client, _config_display
    env = Environment[environment.upper()]
    ctry = Country[country.upper()] if country else None
    settings_args: dict[str, Any] = {
        "login": login.strip(),
        "secret_key": secret_key.strip(),
        "country": ctry,
    }
    if custom_base_url:
        settings_args["environment"] = None
        settings_args["base_url"] = custom_base_url.strip()
    else:
        settings_args["environment"] = env

    _client = Checkout(Settings(**settings_args))
    masked = login[:6] + "…" + login[-4:] if len(login) > 12 else "…"
    _config_display = {
        "login_masked": masked,
        "environment": env.name,
        "country": ctry.name if ctry else "—",
        "base_url": _client.settings.resolved_base_url,
    }


def _require_client() -> Checkout:
    if _client is None:
        raise HTTPException(status_code=400, detail="Not connected. Use section 1 first.")
    return _client


def _sdk_detail(exc: PlaceToPayError) -> str:
    """Build a human-readable detail string from SDK errors, including reason/code."""
    parts = [str(exc)]
    if exc.reason:
        parts.append(f"reason={exc.reason}")
    if exc.status and exc.status.status:
        parts.append(f"status={exc.status.status.value}")
    return " | ".join(parts)


app = FastAPI(title="PlaceToPay Checkout — Python playground")


# ─── Status / connect / disconnect ─────────────────────────────────────
@app.get("/api/status")
def api_status() -> dict[str, Any]:
    if _client is None:
        return {"connected": False}
    return {"connected": True, **(_config_display or {})}


@app.post("/api/connect")
async def api_connect(request: Request) -> dict[str, Any]:
    body = await request.json()
    if not str(body.get("login", "")).strip():
        raise HTTPException(status_code=400, detail="login is required")
    if not str(body.get("secret_key", "")).strip():
        raise HTTPException(status_code=400, detail="secret_key is required")
    try:
        _connect(
            login=body["login"],
            secret_key=body["secret_key"],
            environment=body.get("environment") or "SANDBOX",
            country=body.get("country") or None,
          custom_base_url=str(body.get("custom_base_url") or "").strip() or None,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"connected": True, **(_config_display or {})}


@app.post("/api/disconnect")
def api_disconnect() -> dict[str, bool]:
    global _client, _config_display
    _client = None
    _config_display = None
    return {"connected": False}


# ─── SDK operations (each returns JSON) ────────────────────────────────
@app.post("/api/create")
async def api_create(request: Request) -> dict[str, Any]:
    body = await request.json()
    c = _require_client()
    reference = body.get("reference") or f"demo-{secrets.token_hex(4)}"
    payload: dict[str, Any] = {
        "ipAddress": "127.0.0.1",
        "userAgent": "checkout-python-playground/1.0",
        "returnUrl": body.get("return_url") or "https://example.com/return",
        "payment": {
            "reference": reference,
            "description": body.get("description") or "Demo session",
            "amount": {
                "currency": body.get("currency") or "COP",
                "total": float(body.get("amount") or 50000),
            },
        },
    }
    try:
        resp = c.create_session(payload)
        return resp.model_dump(by_alias=True, exclude_none=True)
    except PlaceToPayError as exc:
        raise HTTPException(status_code=502, detail=_sdk_detail(exc)) from exc


@app.post("/api/create-subscription")
async def api_create_subscription(request: Request) -> dict[str, Any]:
    body = await request.json()
    c = _require_client()
    reference = body.get("reference") or f"sub-{secrets.token_hex(4)}"
    payload: dict[str, Any] = {
        "ipAddress": "127.0.0.1",
        "userAgent": "checkout-python-playground/1.0",
        "returnUrl": body.get("return_url") or "https://example.com/return",
        "subscription": {
            "reference": reference,
            "description": body.get("description") or "Demo subscription session",
        },
    }
    try:
        resp = c.create_session(payload)
        return resp.model_dump(by_alias=True, exclude_none=True)
    except PlaceToPayError as exc:
        raise HTTPException(status_code=502, detail=_sdk_detail(exc)) from exc


@app.post("/api/query")
async def api_query(request: Request) -> dict[str, Any]:
    body = await request.json()
    c = _require_client()
    try:
        request_id = str(body["request_id"]).strip()
        if not request_id:
            raise ValueError("request_id is required")
        return c.query_session(request_id).model_dump(by_alias=True, exclude_none=True)
    except PydanticValidationError as exc:
        raise HTTPException(status_code=502, detail=f"Response parse error: {exc}") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PlaceToPayError as exc:
        raise HTTPException(status_code=502, detail=_sdk_detail(exc)) from exc


@app.post("/api/cancel")
async def api_cancel(request: Request) -> dict[str, Any]:
    body = await request.json()
    c = _require_client()
    try:
        request_id = str(body["request_id"]).strip()
        if not request_id:
            raise ValueError("request_id is required")
        return c.cancel_session(request_id).model_dump(by_alias=True, exclude_none=True)
    except PydanticValidationError as exc:
        raise HTTPException(status_code=502, detail=f"Response parse error: {exc}") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PlaceToPayError as exc:
        raise HTTPException(status_code=502, detail=_sdk_detail(exc)) from exc


@app.post("/api/collect")
async def api_collect(request: Request) -> dict[str, Any]:
    body = await request.json()
    c = _require_client()
    try:
        info = c.collect({
            "payer": {
                "document": body.get("document") or "1040035000",
                "documentType": body.get("document_type") or "CC",
                "name": body.get("name") or "Test",
                "surname": body.get("surname") or "Buyer",
                "email": body.get("email") or "test@example.com",
            },
            "payment": {
                "reference": f"collect-{secrets.token_hex(4)}",
                "description": body.get("description") or "Collect via token",
                "amount": {
                    "currency": body.get("currency") or "COP",
                    "total": float(body.get("amount") or 10000),
                },
            },
            "instrument": {"token": {"token": body["token"]}},
        })
        return info.model_dump(by_alias=True, exclude_none=True)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing field: {exc}") from exc
    except PlaceToPayError as exc:
        raise HTTPException(status_code=502, detail=_sdk_detail(exc)) from exc


@app.post("/api/reverse")
async def api_reverse(request: Request) -> dict[str, Any]:
    body = await request.json()
    c = _require_client()
    try:
        return c.reverse(str(body["internal_reference"])).model_dump(by_alias=True, exclude_none=True)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing field: {exc}") from exc
    except PlaceToPayError as exc:
        raise HTTPException(status_code=502, detail=_sdk_detail(exc)) from exc


@app.post("/api/invalidate")
async def api_invalidate(request: Request) -> dict[str, Any]:
    body = await request.json()
    c = _require_client()
    try:
        s = c.invalidate_token({"instrument": {"token": {"token": body["token"]}}})
        return s.model_dump(by_alias=True, exclude_none=True)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing field: {exc}") from exc
    except PlaceToPayError as exc:
        raise HTTPException(status_code=502, detail=_sdk_detail(exc)) from exc


# ─── Single-page UI ────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        _INDEX_HTML.replace("__PRESEED_LOGIN__", _PRESEED_LOGIN),
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


_INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>PlaceToPay — Python playground</title>
<link rel="icon" type="image/png" href="https://placetopay-static-prod-bucket.s3.us-east-2.amazonaws.com/placetopay-com/favicons/apple-icon-57x57.png">
<style>
  :root{
    /* PlaceToPay palette — orange primary, warm neutrals */
    --p2p-orange: #F36C21;
    --p2p-orange-dark: #C94518;
    --p2p-orange-soft: #FEF2EC;
    --p2p-orange-ring: #FCD9C2;
    --ink: #1F2937;
    --ink-soft: #4B5563;
    --muted: #6B7280;
    --border: #E5E7EB;
    --bg: #FAF7F3;
    --card: #FFFFFF;
    --ok-bg: #DCFCE7; --ok-ink: #166534;
    --err-bg: #FEE2E2; --err-ink: #991B1B;
    --err: #DC2626;
  }
  *{box-sizing:border-box;}
  html,body{margin:0;}
  body{font:14px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg);min-height:100vh;}

  /* ─── Layout ────────────────────────────────────────── */
  .layout{display:grid;grid-template-columns:260px 1fr;min-height:100vh;}
  aside{background:var(--card);border-right:1px solid var(--border);padding:1.5rem 1.1rem;position:sticky;top:0;height:100vh;overflow-y:auto;}
  main{padding:2rem 2.5rem;max-width:900px;}

  /* ─── Sidebar ─────────────────────────────────────── */
  .brand{display:flex;align-items:center;gap:.6rem;margin-bottom:1.25rem;}
  .brand-mark{width:38px;height:38px;border-radius:999px;box-shadow:0 2px 6px rgba(243,108,33,.35);display:block;object-fit:cover;}
  .brand-text{line-height:1.1;}
  .brand-text .t1{font-weight:700;font-size:14px;color:var(--ink);}
  .brand-text .t2{font-size:11px;color:var(--muted);}

  .status-card{border:1px solid var(--border);border-radius:8px;padding:.7rem .85rem;background:var(--bg);margin-bottom:1.25rem;}
  .status-card.live{background:var(--p2p-orange-soft);border-color:var(--p2p-orange-ring);}
  .status-row{display:flex;align-items:center;gap:.5rem;font-size:12.5px;}
  .dot{width:8px;height:8px;border-radius:999px;background:#9CA3AF;}
  .dot.on{background:#16A34A;box-shadow:0 0 0 3px #DCFCE7;}
  .dot.off{background:#DC2626;box-shadow:0 0 0 3px #FEE2E2;}
  .status-detail{margin-top:.5rem;font-size:11.5px;color:var(--ink-soft);display:grid;gap:.15rem;}
  .status-detail code{background:white;border:1px solid var(--border);padding:1px 5px;border-radius:3px;font-size:11px;}
  .status-card button{margin-top:.5rem;width:100%;}

  .menu-heading{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:1rem 0 .35rem;padding:0 .5rem;}
  nav ul{list-style:none;margin:0;padding:0;}
  nav li a{display:flex;align-items:center;gap:.55rem;padding:.5rem .65rem;border-radius:6px;color:var(--ink-soft);text-decoration:none;font-size:13px;cursor:pointer;transition:all .12s;}
  nav li a:hover{background:var(--p2p-orange-soft);color:var(--p2p-orange-dark);}
  nav li a.active{background:var(--p2p-orange);color:white;font-weight:600;}
  nav li a.active .num{background:rgba(255,255,255,.22);color:white;}
  nav li a.disabled{opacity:.45;cursor:not-allowed;}
  nav li a.disabled:hover{background:transparent;color:var(--ink-soft);}
  .num{display:inline-flex;width:22px;height:22px;border-radius:999px;background:var(--border);color:var(--ink-soft);font-size:11px;font-weight:700;align-items:center;justify-content:center;flex-shrink:0;}

  /* ─── Main panels ─────────────────────────────────── */
  h1{margin:0 0 .25rem;font-size:1.6rem;letter-spacing:-0.01em;}
  .sub{color:var(--muted);font-size:12.5px;margin-bottom:1.5rem;}
  section{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1.5rem 1.75rem;margin:0;box-shadow:0 1px 2px rgba(0,0,0,0.03);display:none;}
  section.active{display:block;}
  section.connected{background:linear-gradient(180deg,var(--p2p-orange-soft) 0%,var(--card) 60%);border-color:var(--p2p-orange-ring);}
  section h2{margin:0 0 1rem;font-size:1.15rem;color:var(--ink);display:flex;align-items:center;gap:.6rem;}
  section h2 .badge{background:var(--p2p-orange);color:white;font-size:11px;padding:2px 8px;border-radius:999px;font-weight:700;}

  form{display:grid;gap:.75rem;grid-template-columns:1fr 1fr;align-items:end;}
  form .full{grid-column:1/-1;}
  label{display:grid;gap:.25rem;font-size:12px;color:var(--ink-soft);font-weight:500;}
  input,select,textarea{padding:.55rem .7rem;font:inherit;border:1px solid var(--border);border-radius:6px;background:white;color:var(--ink);transition:border-color .12s,box-shadow .12s;}
  input:focus,select:focus,textarea:focus{outline:0;border-color:var(--p2p-orange);box-shadow:0 0 0 3px var(--p2p-orange-ring);}
  textarea{min-height:6rem;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;resize:vertical;}
  button{cursor:pointer;background:var(--p2p-orange);color:white;border:0;font-weight:600;padding:.6rem 1.2rem;border-radius:6px;font:inherit;font-weight:600;transition:background .12s;}
  button:hover{background:var(--p2p-orange-dark);}
  button.ghost{background:transparent;color:var(--p2p-orange-dark);border:1px solid var(--p2p-orange);}
  button.ghost:hover{background:var(--p2p-orange-soft);}
  button.danger{background:var(--err);}
  button.danger:hover{background:#B91C1C;}

  pre{background:#0F172A;color:#E2E8F0;padding:1rem 1.1rem;border-radius:8px;overflow-x:auto;font-size:11.5px;line-height:1.5;white-space:pre-wrap;word-break:break-all;max-height:420px;margin-top:1rem;}
  .hint{font-size:11.5px;color:var(--muted);margin-top:.35rem;}
  .link-cta{display:inline-block;margin-top:.75rem;padding:.55rem .85rem;background:var(--p2p-orange-soft);border:1px solid var(--p2p-orange-ring);border-radius:6px;color:var(--p2p-orange-dark);text-decoration:none;font-weight:600;font-size:13px;}
  .link-cta:hover{background:var(--p2p-orange-ring);}
  .not-connected-banner{padding:.9rem 1.1rem;background:#FEF3C7;color:#78350F;border:1px solid #FCD34D;border-radius:8px;font-size:13px;margin-bottom:1rem;}
</style></head><body>

<div class="layout">

<aside>
  <div class="brand">
    <img class="brand-mark" src="https://placetopay-static-prod-bucket.s3.us-east-2.amazonaws.com/placetopay-com/favicons/apple-icon-57x57.png" alt="PlaceToPay" width="38" height="38">
    <div class="brand-text">
      <div class="t1">PlaceToPay</div>
      <div class="t2">Python SDK playground</div>
    </div>
  </div>

  <div id="status-card" class="status-card">
    <div class="status-row"><span id="status-dot" class="dot off"></span><strong id="status-text">Disconnected</strong></div>
    <div id="status-detail" class="status-detail" style="display:none"></div>
    <button id="btn-disconnect" class="ghost" style="display:none" onclick="disconnect()">Disconnect</button>
  </div>

  <div class="menu-heading">Operations</div>
  <nav><ul id="menu">
    <li><a data-target="sec-connect"    onclick="show(event,'sec-connect')"    class="active"><span class="num">1</span>Connection</a></li>
    <li><a data-target="sec-create"     onclick="show(event,'sec-create')"     class="disabled"><span class="num">2</span>Create session</a></li>
    <li><a data-target="sec-create-subscription" onclick="show(event,'sec-create-subscription')" class="disabled"><span class="num">3</span>Create subscription session</a></li>
    <li><a data-target="sec-query"      onclick="show(event,'sec-query')"      class="disabled"><span class="num">4</span>Query session</a></li>
    <li><a data-target="sec-cancel"     onclick="show(event,'sec-cancel')"     class="disabled"><span class="num">5</span>Cancel session</a></li>
    <li><a data-target="sec-collect"    onclick="show(event,'sec-collect')"    class="disabled"><span class="num">6</span>Collect</a></li>
    <li><a data-target="sec-reverse"    onclick="show(event,'sec-reverse')"    class="disabled"><span class="num">7</span>Reverse</a></li>
    <li><a data-target="sec-invalidate" onclick="show(event,'sec-invalidate')" class="disabled"><span class="num">8</span>Invalidate token</a></li>
  </ul></nav>
</aside>

<main>
  <h1>Checkout SDK Playground</h1>
  <p class="sub">Every PlaceToPay Checkout SDK operation in one place. Credentials live only in this process's memory — a server restart wipes them.</p>

  <div id="connect-banner" class="not-connected-banner">Start by entering your PlaceToPay credentials in section <strong>1 · Connection</strong>. The other operations light up once you're connected.</div>

  <section id="sec-connect" class="active">
    <h2>Connection <span class="badge">1</span></h2>
    <form id="form-connect" onsubmit="return connect(event)">
      <label>Login<input name="login" value="__PRESEED_LOGIN__" required autocomplete="off"></label>
      <label>Secret key<input name="secret_key" type="password" required autocomplete="off"></label>
      <label>Environment<select name="environment"><option>SANDBOX</option><option>PRODUCTION</option></select></label>
      <label>Country (optional)<select name="country"><option value="">—</option><option>COLOMBIA</option><option>ECUADOR</option></select></label>
      <div class="full hint">Country applies regional defaults (currency/locale) and can affect production routing.</div>
      <label class="full"><input id="custom-url-enabled" type="checkbox"> Use custom WebCheckout URL</label>
      <label id="custom-url-row" class="full" style="display:none">Custom URL<input id="custom-base-url" name="custom_base_url" type="url" placeholder="https://checkout-test.placetopay.com" autocomplete="off"></label>
      <div class="full"><button>Connect</button><div class="hint">Secret goes to this local server only — never logged, never persisted.</div><div id="connect-target" class="hint"></div></div>
    </form>
    <pre id="out-connect" style="display:none"></pre>
  </section>

  <section id="sec-create">
    <h2>Create session <span class="badge">2</span></h2>
    <form onsubmit="call(event, '/api/create', 'out-create'); return false;">
      <label>Amount<input name="amount" type="number" step="0.01" value="50000" required></label>
      <label>Currency<input name="currency" value="COP" required></label>
      <label class="full">Description<input name="description" value="Demo session"></label>
      <label class="full">Return URL<input name="return_url" value="https://example.com/return"></label>
      <div class="full"><button>Create &amp; get processUrl</button></div>
    </form>
    <pre id="out-create" style="display:none"></pre>
  </section>

  <section id="sec-create-subscription">
    <h2>Create subscription session <span class="badge">3</span></h2>
    <form onsubmit="call(event, '/api/create-subscription', 'out-create-subscription'); return false;">
      <label class="full">Reference <span class="hint">(optional)</span><input name="reference" placeholder="sub-abc123"></label>
      <label class="full">Description<input name="description" value="Demo subscription session"></label>
      <label class="full">Return URL<input name="return_url" value="https://example.com/return"></label>
      <div class="full"><button>Create subscription session &amp; get processUrl</button></div>
    </form>
    <pre id="out-create-subscription" style="display:none"></pre>
  </section>

  <section id="sec-query">
    <h2>Query session <span class="badge">4</span></h2>
    <form onsubmit="call(event, '/api/query', 'out-query'); return false;">
      <label>Request ID<input name="request_id" type="text" inputmode="numeric" required></label>
      <div><button>Query</button></div>
    </form>
    <pre id="out-query" style="display:none"></pre>
  </section>

  <section id="sec-cancel">
    <h2>Cancel session <span class="badge">5</span></h2>
    <form onsubmit="call(event, '/api/cancel', 'out-cancel'); return false;">
      <label>Request ID<input name="request_id" type="text" inputmode="numeric" required></label>
      <div><button class="danger">Cancel</button></div>
    </form>
    <pre id="out-cancel" style="display:none"></pre>
  </section>

  <section id="sec-collect">
    <h2>Collect (direct charge) <span class="badge">6</span></h2>
    <form onsubmit="call(event, '/api/collect', 'out-collect'); return false;">
      <label class="full">Token<input name="token" required placeholder="subscription token"></label>
      <label>Amount<input name="amount" type="number" step="0.01" value="10000"></label>
      <label>Currency<input name="currency" value="COP"></label>
      <label>Payer document<input name="document" value="1040035000"></label>
      <label>Document type<input name="document_type" value="CC"></label>
      <label>Name<input name="name" value="Test"></label>
      <label>Surname<input name="surname" value="Buyer"></label>
      <label>Email<input name="email" type="email" value="test@example.com"></label>
      <div class="full"><button>Collect</button></div>
    </form>
    <pre id="out-collect" style="display:none"></pre>
  </section>

  <section id="sec-reverse">
    <h2>Reverse <span class="badge">7</span></h2>
    <form onsubmit="call(event, '/api/reverse', 'out-reverse'); return false;">
      <label>Internal reference<input name="internal_reference" required></label>
      <div><button class="danger">Reverse</button></div>
    </form>
    <pre id="out-reverse" style="display:none"></pre>
  </section>

  <section id="sec-invalidate">
    <h2>Invalidate token <span class="badge">8</span></h2>
    <form onsubmit="call(event, '/api/invalidate', 'out-invalidate'); return false;">
      <label class="full">Token<input name="token" required></label>
      <div><button class="danger">Invalidate</button></div>
    </form>
    <pre id="out-invalidate" style="display:none"></pre>
  </section>
</main>

</div>

<script>
function endpointForSelection(environment, country){
  const env = (environment || 'SANDBOX').toUpperCase();
  const ctry = (country || '').toUpperCase();
  if (ctry === 'ECUADOR'){
    return env === 'PRODUCTION'
      ? 'https://checkout.placetopay.ec'
      : 'https://checkout-test.placetopay.ec';
  }
  return env === 'PRODUCTION'
    ? 'https://checkout.placetopay.com'
    : 'https://checkout-test.placetopay.com';
}

function syncCustomBaseUrlState(){
  const enabled = document.getElementById('custom-url-enabled');
  const row = document.getElementById('custom-url-row');
  const input = document.getElementById('custom-base-url');
  if(!enabled || !row || !input) return;
  row.style.display = enabled.checked ? 'grid' : 'none';
  input.disabled = !enabled.checked;
  input.required = enabled.checked;
}

function refreshTargetHint(){
  const form = document.getElementById('form-connect');
  const hint = document.getElementById('connect-target');
  if(!form || !hint) return;
  const fd = new FormData(form);
  const env = (fd.get('environment') || 'SANDBOX').toString().toUpperCase();
  const country = (fd.get('country') || '').toString().toUpperCase();
  const customEnabled = document.getElementById('custom-url-enabled')?.checked;
  const customUrl = (document.getElementById('custom-base-url')?.value || '').trim();
  const target = customEnabled && customUrl ? customUrl : endpointForSelection(env, country);
  const connected = document.getElementById('status-text')?.textContent === 'Connected';
  hint.innerHTML = 'WebCheckout target: <code>' + target + '</code>' + (connected ? ' <span class="hint">(applies on reconnect)</span>' : '');
}

function show(ev, id){
  if(ev) ev.preventDefault();
  const link = document.querySelector('a[data-target="'+id+'"]');
  if(link && link.classList.contains('disabled')) return false;
  for(const s of document.querySelectorAll('section')) s.classList.remove('active');
  document.getElementById(id).classList.add('active');
  for(const a of document.querySelectorAll('nav a')) a.classList.remove('active');
  if(link) link.classList.add('active');
  return false;
}

async function refreshStatus(){
  const r = await fetch('/api/status'); const j = await r.json();
  const dot   = document.getElementById('status-dot');
  const text  = document.getElementById('status-text');
  const detail= document.getElementById('status-detail');
  const btn   = document.getElementById('btn-disconnect');
  const card  = document.getElementById('status-card');
  const banner= document.getElementById('connect-banner');
  const secConnect = document.getElementById('sec-connect');
  const menu = document.getElementById('menu');

  if (j.connected){
    dot.className='dot on'; text.textContent='Connected';
    card.classList.add('live');
    detail.style.display='grid';
    detail.innerHTML = '<div>Login: <code>'+j.login_masked+'</code></div>'
      + '<div>Env: <code>'+j.environment+'</code> &nbsp; Country: <code>'+j.country+'</code></div>'
      + '<div>WebCheckout: <code>'+(j.base_url || endpointForSelection((j.environment || 'SANDBOX').toUpperCase(), (j.country || '').toUpperCase()))+'</code></div>';
    // Keep form selections editable while connected; changes are applied on reconnect.
    refreshTargetHint();
    btn.style.display='block';
    banner.style.display='none';
    secConnect.classList.add('connected');
    for(const a of menu.querySelectorAll('a')) a.classList.remove('disabled');
  } else {
    dot.className='dot off'; text.textContent='Disconnected';
    card.classList.remove('live');
    detail.style.display='none'; detail.innerHTML='';
    btn.style.display='none';
    banner.style.display='block';
    secConnect.classList.remove('connected');
    for(const a of menu.querySelectorAll('a'))
      if(a.getAttribute('data-target')!=='sec-connect') a.classList.add('disabled');
    // Force back to Connection section if user was on a disabled one.
    if(!document.getElementById('sec-connect').classList.contains('active')) show(null,'sec-connect');
  }
}
document.querySelector('#form-connect select[name="environment"]')?.addEventListener('change', refreshTargetHint);
document.querySelector('#form-connect select[name="country"]')?.addEventListener('change', refreshTargetHint);
document.getElementById('custom-url-enabled')?.addEventListener('change', () => { syncCustomBaseUrlState(); refreshTargetHint(); });
document.getElementById('custom-base-url')?.addEventListener('input', refreshTargetHint);
syncCustomBaseUrlState();
refreshTargetHint();
refreshStatus();

function prettyJsonRaw(raw){
  const text = (raw || '').trim();
  if (!text || (text[0] !== '{' && text[0] !== '[')) return raw;

  let out = '';
  let indent = 0;
  let inString = false;
  let escaped = false;
  const unit = '  ';

  for (let i = 0; i < text.length; i++){
    const ch = text[i];

    if (inString){
      out += ch;
      if (escaped){
        escaped = false;
      } else if (ch === '\\'){
        escaped = true;
      } else if (ch === '"'){
        inString = false;
      }
      continue;
    }

    if (ch === '"'){
      inString = true;
      out += ch;
      continue;
    }

    if (ch === '{' || ch === '['){
      out += ch + '\n';
      indent += 1;
      out += unit.repeat(indent);
      continue;
    }

    if (ch === '}' || ch === ']'){
      out += '\n';
      indent = Math.max(0, indent - 1);
      out += unit.repeat(indent) + ch;
      continue;
    }

    if (ch === ','){
      out += ch + '\n' + unit.repeat(indent);
      continue;
    }

    if (ch === ':'){
      out += ': ';
      continue;
    }

    if (ch !== '\n' && ch !== '\r' && ch !== '\t'){
      out += ch;
    }
  }

  return out;
}

function normalizeJsonText(raw){
  let text = (raw || '').trim();
  if (!text) return text;

  // Case 1: already a JSON object/array text.
  if (text[0] === '{' || text[0] === '[') return text;

  // Case 2: JSON encoded as a quoted string, e.g. "{\"a\":1}".
  if ((text[0] === '"' && text[text.length - 1] === '"') || text.includes('\\"')){
    try {
      const decoded = JSON.parse(text);
      if (typeof decoded === 'string') {
        const nested = decoded.trim();
        if (nested[0] === '{' || nested[0] === '[') return nested;
      }
    } catch {
      // Keep original text when decoding fails.
    }
  }

  return text;
}

function fmt(out, r, payload){
  out.style.display='block';

  if (typeof payload !== 'string'){
    out.textContent = 'HTTP ' + r.status + '\n\n' + JSON.stringify(payload, null, 2);
    return;
  }

  const normalized = normalizeJsonText(payload);
  const pretty = (normalized[0] === '{' || normalized[0] === '[')
    ? prettyJsonRaw(normalized)
    : normalized;
  out.textContent = 'HTTP ' + r.status + '\n\n' + pretty;
}

function jsonField(raw, field){
  const re = new RegExp('"' + field + '"\\s*:\\s*"([^"]+)"');
  const m = raw.match(re);
  return m ? m[1] : null;
}

async function connect(ev){
  ev.preventDefault();
  const f = ev.target; const body = Object.fromEntries(new FormData(f).entries());
  const customEnabled = document.getElementById('custom-url-enabled')?.checked;
  if (!customEnabled) delete body.custom_base_url;
  const out = document.getElementById('out-connect');
  const r = await fetch('/api/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j = await r.json(); fmt(out, r, j);
  if (r.ok){
    const secretInput = f.querySelector('input[name="secret_key"]');
    if (secretInput) secretInput.value = '';
    await refreshStatus();
  }
  return false;
}

async function disconnect(){
  await fetch('/api/disconnect',{method:'POST'}); await refreshStatus();
}

async function call(ev, path, outId){
  ev.preventDefault();
  const form = ev.target;
  const out = document.getElementById(outId);
  const body = Object.fromEntries(new FormData(form).entries());
  const r = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const raw = await r.text();
  fmt(out, r, raw || '{"error":"empty response"}');
  if (path === '/api/create' || path === '/api/create-subscription'){
    const processUrl = jsonField(raw, 'processUrl');
    if (!processUrl) return false;
    const sibling = out.nextElementSibling;
    if (sibling && sibling.classList && sibling.classList.contains('link-cta')) sibling.remove();
    const a = document.createElement('a'); a.href=processUrl; a.target='_blank';
    a.className='link-cta';
    a.textContent='→ Open processUrl in a new tab (complete the payment)';
    out.after(a);
  }
  return false;
}
</script>

</body></html>
"""
