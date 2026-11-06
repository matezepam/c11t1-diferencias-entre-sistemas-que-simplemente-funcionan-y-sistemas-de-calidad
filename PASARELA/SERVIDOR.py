# La pasarela de prueba se ejecuta aparte de la tienda y conserva sólo claves
# de compra, importes y estados, sin tarjetas ni movimientos de dinero real.

from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hmac
import json
import os
import sqlite3

from CALIDAD.INFRAESTRUCTURA.DATOS import cargar_configuracion
from CALIDAD.COMUN.SEGURIDAD import texto, dinero
from CALIDAD.COMUN.ERRORES import DatosInvalidos, Conflicto

# Comparte la ubicación de datos del trabajo para que otra copia del repositorio
# conserve los pagos correspondientes a la misma base PostgreSQL de este equipo.
RUTA_PAGOS = Path.home() / '.local/share/c11t1/PAGOS.sqlite3'


# Crea el archivo del servicio sin usar la conexión de la tienda para poder
# comprobar qué ocurre cuando sólo una de las dos partes confirma su operación.
def preparar_archivo(ruta):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(ruta)) as conexion, conexion:
        conexion.execute('''CREATE TABLE IF NOT EXISTS pagos (
            clave TEXT PRIMARY KEY, centavos INTEGER NOT NULL, estado TEXT NOT NULL)''')
    ruta.chmod(0o600)


# Devuelve el estado de una operación y guarda el importe en centavos para
# comparar reintentos sin aproximaciones y sin crear un segundo cobro.
def procesar_pago(ruta, accion, datos):
    if accion not in ('cobrar', 'reembolsar') or not isinstance(datos, dict):
        raise DatosInvalidos('Operación de pago inválida')
    clave = texto(datos.get('clave'), 'Clave de compra', 80)
    centavos = int(dinero(datos.get('importe')) * 100)
    rechazar = datos.get('rechazar', False)
    if type(rechazar) is not bool:
        raise DatosInvalidos('La opción de rechazo debe ser verdadera o falsa')
    with closing(sqlite3.connect(ruta, timeout=5)) as conexion, conexion:
        # Reserva la escritura antes de leer para que dos solicitudes con la
        # misma clave no puedan decidir resultados distintos al mismo tiempo.
        conexion.execute('BEGIN IMMEDIATE')
        pago = conexion.execute('SELECT centavos, estado FROM pagos WHERE clave=?', (clave,)).fetchone()
        if pago and pago[0] != centavos:
            raise Conflicto('La clave de compra ya tiene otro importe')
        if not pago:
            estado = ('rechazado' if rechazar else 'cobrado') if accion == 'cobrar' else 'anulado'
            conexion.execute('INSERT INTO pagos VALUES (?, ?, ?)', (clave, centavos, estado))
        else:
            estado = pago[1]
            if accion == 'reembolsar' and estado == 'cobrado':
                estado = 'reembolsado'
                conexion.execute('UPDATE pagos SET estado=? WHERE clave=?', (estado, clave))
        # El contexto confirma al salir o revierte ante una excepción aunque
        # este servicio tenga un almacenamiento independiente de PostgreSQL.
    return {'estado': estado}


class SolicitudPago(BaseHTTPRequestHandler):
    # Devuelve JSON y un código HTTP para distinguir un dato incorrecto de un
    # conflicto o una caída sin revelar consultas ni credenciales del servicio.
    def responder(self, codigo, contenido):
        cuerpo = json.dumps(contenido).encode('utf-8')
        self.send_response(codigo)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    # Acepta sólo mensajes autenticados y pequeños para limitar la comunicación
    # a los datos que necesitan el cobro y el reembolso del ejemplo.
    def do_POST(self):
        esperado = 'Bearer ' + self.server.clave_pasarela
        recibido = self.headers.get('Authorization', '')
        if not hmac.compare_digest(recibido.encode(), esperado.encode()):
            self.responder(401, {'error': 'Acceso a la pasarela denegado'})
            return
        try:
            longitud = int(self.headers.get('Content-Length', '0'))
            if not 0 < longitud <= 2048:
                raise DatosInvalidos('Tamaño de solicitud inválido')
            datos = json.loads(self.rfile.read(longitud))
            resultado = procesar_pago(self.server.ruta_pagos, self.path.lstrip('/'), datos)
            self.responder(200, resultado)
        except Conflicto as error:
            self.responder(409, {'error': str(error)})
        except (DatosInvalidos, ValueError, UnicodeError):
            self.responder(400, {'error': 'Revise los datos de la solicitud'})
        except (sqlite3.Error, OSError):
            self.responder(503, {'error': 'El servicio de pagos no está disponible'})

    # Evita imprimir cabeceras o cuerpos de solicitudes en la terminal.
    def log_message(self, formato, *argumentos):
        return


# Devuelve el servidor y permite usar un puerto temporal en las pruebas,
# mientras la ejecución normal escucha sólo en este equipo por el 55433.
def crear_servidor(ruta, clave, puerto=55433):
    if not isinstance(clave, str) or not clave.strip():
        raise DatosInvalidos('Ejecute PREPARAR.py para configurar la pasarela')
    preparar_archivo(ruta)
    servidor = ThreadingHTTPServer(('127.0.0.1', puerto), SolicitudPago)
    servidor.clave_pasarela, servidor.ruta_pagos = clave, ruta
    return servidor


if __name__ == '__main__':
    cargar_configuracion()
    try:
        with crear_servidor(RUTA_PAGOS, os.environ.get('C11_CLAVE_PASARELA')) as servidor:
            print('PASARELA DE PRUEBA | http://127.0.0.1:55433')
            print('Deje esta terminal abierta y ejecute INICIAR.py en otra')
            servidor.serve_forever()
    except KeyboardInterrupt:
        print('\nPasarela detenida')
    except (DatosInvalidos, OSError) as error:
        print(f'No se pudo iniciar la pasarela: {error}')
        raise SystemExit(1)
