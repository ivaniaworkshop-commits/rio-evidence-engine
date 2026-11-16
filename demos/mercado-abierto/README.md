# Mercado Abierto · integración con pey y CoDi

Código fuente del gateway y la interfaz web de Mercado Abierto. La aplicación permite administrar negocios y ofertas, gestionar direcciones de entrega, consolidar pedidos, y conectar comercios con los servicios de cobro de pey.

Este repositorio contiene código y migraciones, no datos de producción ni credenciales. Publicar el código no publica la base de datos, las variables privadas, la configuración de Vercel ni la autorización del proveedor.

## Componentes

- `app/`: servicio FastAPI, modelos, migraciones Alembic, archivos estáticos y pruebas.
- `frontdesk/`: páginas ligeras de entrada al gateway. El archivo `vercel.json` apunta al dominio de la aplicación actual; cámbialo antes de reutilizarlo en otro entorno.
- `iniciar_unificada.py`: inicia una instancia local desechable con datos sintéticos y sin pagos reales.

## Desarrollo local

Requiere Python 3.11 o posterior. Desde la raíz:

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e "./app[test]"
python iniciar_unificada.py
```

Abre `http://127.0.0.1:8000/`. El servidor crea una base SQLite temporal, usa un correo ficticio y no emite pagos. Detener el proceso elimina esa base.

Para las pruebas unitarias:

```bash
cd app
python -m pytest -q
node --test tests/market_checkout_ui.test.cjs
```

Las pruebas de proveedor usan respuestas sintéticas; no acceden a cuentas bancarias o llaves de pey. El contrato OpenAPI público usado por las pruebas está en [`app/tests/fixtures/pey-openapi-2026-10-20.json`](app/tests/fixtures/pey-openapi-2026-10-20.json).

## Cobros, pedidos y límites

Las operaciones CoDi reales requieren credenciales válidas y configuradas por cada comercio, migraciones aplicadas y verificación del contrato vigente de pey. No guardes llaves, secretos de webhook, CLABEs ni contraseñas en este repositorio.

El QR de seguimiento del carrito identifica un pedido consolidado. El QR CoDi que cobra el total se crea en Caja después de que el vendedor acepta el pedido. Un carrito de un solo pago debe contener ofertas de un mismo vendedor, porque CoDi dirige el cobro a una sola cuenta. El estado de pey no demuestra por sí mismo la acreditación bancaria; esta aplicación no declara una confirmación bancaria sin integración independiente.

El botón de WhatsApp es un enlace público de contacto. No es una bandeja conectada ni recibe o envía mensajes de forma automática.

## Configuración

En despliegue se necesita una base PostgreSQL y variables privadas configuradas fuera de Git. Usa las migraciones de `app/migrations/` con una copia de datos antes de cambiar de revisión. Los detalles de la cuenta productiva de Vercel se han omitido. La integración de pey se rige por su [documentación oficial](https://docs.pey.mx/).

## Licencia

El repositorio es público, pero no incluye una licencia de distribución para el código propio. La visibilidad pública no concede por sí sola permiso de reutilización. Los avisos de dependencias de terceros se conservan en los archivos correspondientes.
