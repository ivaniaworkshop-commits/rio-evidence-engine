#!/usr/bin/env python3
"""Servidor local desechable para probar las tres pantallas integradas."""
import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'app'))
import uvicorn
from rio_pey_codi.identity import Signup
from rio_pey_codi.platform import Settings, create_platform


def main():
    parser = argparse.ArgumentParser(description='RÍO unificada: demostración local sin pagos reales')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--test-marker', default='', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('El puerto debe estar entre 1 y 65535.')
    if args.test_marker and not re.fullmatch(r'[0-9a-f]{32}', args.test_marker):
        parser.error('Marcador de prueba inválido.')
    with tempfile.TemporaryDirectory(prefix='rio-unificada-demo-') as folder:
        db = Path(folder) / 'demo.sqlite3'
        base = f'http://127.0.0.1:{args.port}'
        application = create_platform(Settings(
            env='local', mode='DEMO', database_url='sqlite+pysqlite:///' + str(db),
            auto_create=True, email_mode='memory', public_url=base, origin=base,
        ))
        if args.test_marker:
            marker = args.test_marker

            @application.get('/__rio_test_' + marker, include_in_schema=False)
            def test_marker():
                return {'marker': marker}

        application.state.accounts.signup(Signup(
            email='evaluacion@example.org', password='RioDemo-2026-Local',
            business_name='Comercio de evaluación',
        ))
        application.state.accounts.verify(application.state.mailer.outbox[-1]['token'])
        print(f'Interfaz unificada: {base}/static/unificada/index.html', flush=True)
        print(f'Aplicación integrada: {base}/', flush=True)
        print('Cuenta ficticia local: evaluacion@example.org / RioDemo-2026-Local', flush=True)
        print('Sin pagos ni correos reales; la base temporal se elimina al cerrar.', flush=True)
        uvicorn.run(application, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
