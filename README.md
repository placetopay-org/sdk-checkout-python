# PlaceToPay Checkout - SDK Python

[![CI](https://github.com/placetopay/checkout-python/actions/workflows/ci.yml/badge.svg)](https://github.com/placetopay/checkout-python/actions/workflows/ci.yml)
[![PyPI versión](https://img.shields.io/pypi/v/placetopay-checkout.svg)](https://pypi.org/project/placetopay-checkout/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

SDK oficial de Python para **PlaceToPay Web Checkout**.

Esta libreria te permite integrar pagos rapidamente: crear la sesion,
redirigir al comprador y confirmar el resultado del pago desde tu servicio.

Terminología estándar del proyecto: ver `../docs/GLOSARIO.md`.

> Si vienes del SDK anterior de la comunidad, revisa `MIGRATION.md` para una migracion guiada.

---

## Instalación

```bash
pip install placetopay-checkout
```

Requiere **Python 3.13+**.

## Versiones soportadas

| Versión SDK | Python | Estado | Parches de seguridad hasta |
|-------------|--------|--------|----------------------------|
| `1.x` | 3.13, 3.14 | **Actual** | Hasta el siguiente major |
| `0.x` | - | Pre-release | End-of-life |

**Política**

- Soportamos la versión actual y la versión anterior de Python.
- Cambios breaking solo en major.
- Ruta de migración documentada en `MIGRATION.md`.

## Quickstart (5 minutos)

En pocos pasos puedes crear una sesion y obtener el `process_url` para enviar
al comprador al checkout.

```python
from placetopay.checkout import Checkout, Settings, Environment, Country

client = Checkout(Settings(
    login="YOUR_LOGIN",
    secret_key="YOUR_SECRET_KEY",
    environment=Environment.SANDBOX,
    country=Country.COLOMBIA,
))

response = client.create_session({
    "ipAddress":  "127.0.0.1",
    "userAgent":  "MyApp/1.0",
    "returnUrl":  "https://example.com/return",
    "payment": {
        "reference":   "ORDER-0001",
        "description": "Demo purchase",
        "amount":      {"currency": "COP", "total": 50_000},
    },
})

print(response.process_url)
print(response.request_id)
```

Después del pago:

```python
info = client.query_session(response.request_id)
if info.status.status == "APPROVED":
    # completar orden
    ...
```

## Que puedes hacer con este SDK

| Endpoint | Método | Notas |
| --- | --- | --- |
| `POST /api/session` | `create_session` | Soporta `autopay`, `type`, `metadata`, `dispersion` |
| `POST /api/session/{id}` | `query_session` | |
| `POST /api/session/{id}/cancel` | `cancel_session` | Nuevo vs SDK de referencia |
| `POST /api/collect` | `collect` | Cobro con instrumento tokenizado |
| `POST /api/reverse` | `reverse` | Por `internalReference` |
| `POST /api/instrument/invalidate` | `invalidate_token` | Revoca token |
| Verificación webhook SHA-256 | `verify_notification` | Recomendado |
| Verificación webhook SHA-1 | `verify_notification_legacy` | Solo compatibilidad legacy |

## Flujo de integracion recomendado

Flujo de sesion (checkout web):

1. `create_session` para iniciar el checkout y obtener `request_id` + `process_url`.
2. `query_session` para confirmar estado despues del retorno del pagador.
3. `cancel_session` para invalidar una sesion pendiente cuando aplica.

Flujo de tokenizacion y post-pago:

1. `collect` para cobrar con instrumento tokenizado.
2. `reverse` para reversar por `internalReference`.
3. `invalidate_token` para revocar el token.

## Funcionalidades incluidas en v1

- Soporte de `auth.additional` via `Settings.auth_additional`.
- Soporte de `CollectRequest.provider` para override opcional de procesador.
- Helpers de estado en `Status` y `Transaction` (`is_approved`, `is_rejected`, `is_error`, `is_successful`).
- Helpers de sesion en `SessionInformation` (`last_transaction`, `last_approved_transaction`, `last_authorization`).
- Compatibilidad con valores heterogeneos en `processorFields[].value`.

## Casos de uso comunes

- Checkout estandar en web con redireccion (`create_session` + `query_session`).
- Cobro con token guardado (`collect`) para compras recurrentes.
- Reversion de pagos (`reverse`) y revocacion de token (`invalidate_token`).

### Limitaciones por pais

- Ecuador: la funcionalidad `autopay` no esta habilitada en WebCheckout para este pais. Si se envia en `create_session`, puede ser rechazada por el gateway.
- Ecuador: la recurrencia en pago unico no esta disponible actualmente.

### Compatibilidad de respuestas del gateway

- En respuestas de `query_session` / `collect`, `payment[].processorFields[].value` puede llegar como `str`, `int`, `float`, `bool` o objeto JSON.
- El SDK acepta ese valor heterogeneo para evitar `ValidationError` cuando el gateway envia metadatos no-string.

## Configuración

Campos de `Settings`:

| Campo | Tipo | Default | Uso |
| --- | --- | --- | --- |
| `login` | `str` | requerido | Login de comercio |
| `secret_key` | `str` o `SecretStr` | requerido | Secret de comercio |
| `environment` | `Environment` | `SANDBOX` | Sandbox/Producción |
| `country` | `Country` | `None` | Defaults de locale/currency/base URL |
| `base_url` | `str` | - | Override explícito (solo HTTPS) |
| `timeout_connect` | `float` | `10` | Timeout conexión |
| `timeout_read` | `float` | `30` | Timeout lectura |
| `retry_max_attempts` | `int` | `3` | Retries máximos |
| `retry_initial_delay_ms` | `int` | `200` | Backoff inicial |
| `retry_max_delay_ms` | `int` | `5000` | Tope de backoff |
| `user_agent_suffix` | `str` | `None` | Sufijo de user-agent |
| `additional_headers` | `dict[str, str]` | `{}` | Headers extra |
| `logger` | `logging.Logger` | `None` | DEBUG con payload redactado |

## Manejo de errores

Todas las excepciones heredan de `PlaceToPayError`:

- `AuthenticationError`
- `ValidationError`
- `NotFoundError`
- `RateLimitError`
- `NetworkError`
- `ServerError`

## Verificación de webhook

```python
from placetopay.checkout import verify_notification

@app.post("/placetopay/webhook")
def webhook(payload: dict):
    if not verify_notification(payload, secret_key=SECRET):
        return ("invalid signature", 403)
    # Safe to act on payload
```

> Las notificaciones webhook de PlaceToPay están confirmadas sobre SHA-256.

## Pruebas locales con app de ejemplo

La carpeta `examples/` incluye una app FastAPI para probar los flujos end-to-end. Ver [`examples/README.md`](examples/README.md).

```bash
cd examples
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --reload
open http://localhost:8000
```

## Seguridad

- Firma: SHA-256.
- Nonce: 16 bytes criptográficos via `secrets.token_bytes()`.
- TLS: HTTPS obligatorio.
- Logging: redacción automática de PAN, CVV, `tranKey`, `nonce`, token, PIN y password.
- Disclosure: ver [SECURITY.md](SECURITY.md).

## Instalar desde código fuente

```bash
git clone https://github.com/placetopay/checkout-python.git
cd checkout-python
pip install -e '.[dev]'
pytest
```

## Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

MIT, ver [LICENSE](LICENSE).
