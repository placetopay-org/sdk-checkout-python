# PlaceToPay Checkout - Ejemplo Python

App FastAPI que recorre los endpoints del SDK Python de punta a punta contra sandbox de PlaceToPay.

Se usa como harness de validación del SDK y no como integración productiva.

## Ejecutar

```bash
# desde la raiz del repo
pip install -e .
cd examples
pip install -r requirements.txt

cp .env.example .env
uvicorn app:app --reload
```

Luego abre **http://localhost:8000**.

## Qué demuestra

| Flujo | UI | Metodo |
| --- | --- | --- |
| Crear session | formulario en `/` | `create_session` |
| Consultar session | `/session/{id}` | `query_session` |
| Cancelar session | `POST /session/{id}/cancel` | `cancel_session` |
| Collect | `/docs` o curl | `collect` |
| Reverse | `/docs` o curl | `reverse` |
| Invalidate token | `/docs` o curl | `invalidate_token` |

Swagger UI: http://localhost:8000/docs

## Notas

- `collect`, `reverse` e `invalidate_token` requieren token real de sandbox.
- El app de examples no se pública en el paquete PyPI.

## Transacciones cubiertas

Este ejemplo cubre los 2 bloques funcionales de Checkout:

- Sesion: `create_session`, `query_session`, `cancel_session`.
- Token/post-pago: `collect`, `reverse`, `invalidate_token`.

## Funcionalidades destacadas del ejemplo

- Firma SHA-256 y nonce criptografico manejados por el SDK.
- Verificacion de estados de sesion y transaccion via `query_session`.
- Prueba local de los 6 endpoints soportados por el contrato OpenAPI.
