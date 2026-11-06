# Las reglas se prueban sin servidor y las operaciones de base se comprueban
# por separado en un esquema temporal para no borrar los datos del ejemplo.

from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import os
import io
import json
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
import sys
import threading
import unittest
import uuid

from CALIDAD.INFRAESTRUCTURA import DATOS
from CALIDAD.SERVICIOS import CUENTAS, CLINICA, COMERCIO
from CALIDAD.COMUN.ERRORES import DatosInvalidos, Conflicto, AccesoDenegado, PagoNoDisponible
from CALIDAD.COMUN.SEGURIDAD import dinero, entero, texto, derivar_clave, comprobar_clave
from PASARELA.SERVIDOR import preparar_archivo, procesar_pago, SolicitudPago, crear_servidor
from CALIDAD.INFRAESTRUCTURA.PAGOS import PasarelaPrueba
from CALIDAD.INFRAESTRUCTURA.REGISTRO import avisar_pedido, cerrar_avisos, registrar_evento
import PREPARAR

INTEGRACION = '--integracion' in sys.argv
if INTEGRACION:
    sys.argv.remove('--integracion')
ADMIN = {'id': 1, 'nombre': 'Administración', 'rol': 'administracion'}
DOCTOR = {'id': 2, 'nombre': 'Doctor', 'rol': 'doctor'}
CLIENTE = {'id': 3, 'nombre': 'Cliente', 'rol': 'cliente'}


class Reglas(unittest.TestCase):
    # Comprueba centavos y cantidades sin depender del almacenamiento de la base.
    def test_importes_y_cantidades(self):
        self.assertEqual(dinero('12.30'), Decimal('12.30'))
        for valor in ('-1','0','NaN','Infinity','0.001','letras','10000000000'):
            with self.subTest(valor=valor), self.assertRaises(DatosInvalidos): dinero(valor)
        self.assertEqual(entero(0, True), 0)
        for valor in (-1,0,True,1.5,'2'):
            with self.assertRaises(DatosInvalidos): entero(valor)
        with self.assertRaises(DatosInvalidos): texto('  ', 'Nombre')

    # Rechaza teléfonos sin suficientes dígitos antes de guardar y comprueba
    # que los espacios y guiones no impidan registrar un número válido.
    def test_telefono(self):
        for telefono in ('-------','(((((((','abc1234567','12345','+593 9999999999999999'):
            with self.subTest(telefono=telefono), self.assertRaises(DatosInvalidos):
                CLINICA.registrar_paciente(ADMIN,'DEMO001','Nombre',date(2000,1,1),telefono,'Ninguno')
        with patch.object(DATOS,'transaccion'), patch.object(DATOS,'guardar_paciente',return_value=7):
            self.assertEqual(CLINICA.registrar_paciente(ADMIN,'DEMO001','Nombre',date(2000,1,1),'+593 99-999-9999','Ninguno'),7)

    # Una fecha futura o una cuenta sin permiso no deben registrar pacientes.
    def test_fecha_y_permisos(self):
        with self.assertRaises(DatosInvalidos):
            CLINICA.registrar_paciente(ADMIN,'DEMO001','Nombre',date.today()+timedelta(days=1),'0999999999','Ninguno')
        with self.assertRaises(AccesoDenegado): CLINICA.listar_pacientes(CLIENTE)
        with self.assertRaises(AccesoDenegado): COMERCIO.registrar_producto(CLIENTE,'Nombre','Categoría','10',1)
        with self.assertRaises(AccesoDenegado): CUENTAS.registrar_usuario('Nombre','persona@example.test','ClaveEjemplo42','doctor')

    # El horario necesita zona horaria y un intervalo futuro de duración válida.
    def test_horarios(self):
        with self.assertRaises(DatosInvalidos):
            CLINICA.programar_cita(ADMIN,1,1,datetime(2030,1,1),datetime(2030,1,1,1))
        inicio = datetime.now(timezone.utc)+timedelta(days=1)
        with self.assertRaises(DatosInvalidos): CLINICA.programar_cita(ADMIN,1,1,inicio,inicio)

    # Los resúmenes no revelan la clave y una contraseña incorrecta no autentica.
    def test_contrasenas(self):
        sal,resumen = derivar_clave('ClaveEjemplo42')
        otra_sal,otro = derivar_clave('ClaveEjemplo42')
        self.assertNotEqual((sal,resumen),(otra_sal,otro))
        registro = {'sal':sal,'clave':resumen}
        self.assertTrue(comprobar_clave('ClaveEjemplo42',registro))
        self.assertFalse(comprobar_clave('OtraClave42',registro))
        with self.assertRaises(DatosInvalidos): derivar_clave('corta')

    # La cuenta local contiene sólo datos de identificación y nunca su resumen.
    def test_inicio_sesion(self):
        sal,resumen = derivar_clave('ClaveEjemplo42')
        registro = dict(ADMIN,correo='persona@example.test',sal=sal,clave=resumen)
        with patch.object(DATOS,'transaccion'), patch.object(DATOS,'buscar_usuario',return_value=registro):
            self.assertEqual(CUENTAS.iniciar_sesion('persona@example.test','ClaveEjemplo42'),ADMIN)
            with self.assertRaises(AccesoDenegado): CUENTAS.iniciar_sesion('persona@example.test','OtraClave42')

    # Verifica impuestos y envíos sin abrir una conexión ni crear pedidos.
    def test_total(self):
        self.assertEqual(COMERCIO.calcular_total('10','normal'),Decimal('14.00'))
        self.assertEqual(COMERCIO.calcular_total('10','rapido'),Decimal('16.50'))
        with self.assertRaises(DatosInvalidos): COMERCIO.calcular_total('10','inexistente')

    # La segunda búsqueda usa caché y sus resultados no permiten modificarla.
    def test_cache(self):
        COMERCIO.invalidar_catalogo()
        producto={'id':1,'nombre':'Cuaderno','categoria':'Papelería','precio':Decimal('3.50'),'stock':2}
        with patch.object(DATOS,'transaccion'), patch.object(DATOS,'catalogo',return_value=[producto]) as consulta:
            primero=COMERCIO.buscar_catalogo('CUA','papelería')
            primero[0]['stock']=500
            self.assertEqual(COMERCIO.buscar_catalogo()[0]['stock'],2)
            self.assertEqual(consulta.call_count,1)
            COMERCIO.invalidar_catalogo()
            COMERCIO.buscar_catalogo()
            self.assertEqual(consulta.call_count,2)
        COMERCIO.invalidar_catalogo()

    # Una pasarela caída no produce una respuesta inventada de cobro o reembolso.
    def test_pasarela_no_disponible(self):
        pasarela=PasarelaPrueba(disponible=False)
        with self.assertRaises(PagoNoDisponible): pasarela.cobrar('compra','10')
        with self.assertRaises(PagoNoDisponible): pasarela.reembolsar('compra','10')

    # El aviso se ejecuta en el trabajador y devuelve una tarea comprobable.
    def test_aviso(self):
        with patch('CALIDAD.INFRAESTRUCTURA.REGISTRO.registrar_evento') as registrar:
            tarea=avisar_pedido(3,7)
            tarea.result(timeout=3)
            registrar.assert_called_once_with(3,'aviso_pedido_simulado',7)

    # Un archivo de auditoría sin permiso no debe interrumpir una operación
    # que ya terminó, por eso se conserva el evento mediante la consola.
    def test_registro_sin_archivo(self):
        import logging
        logger = logging.getLogger('c11t1')
        anteriores, nivel = logger.handlers[:], logger.level
        logger.handlers = []
        try:
            with patch('CALIDAD.INFRAESTRUCTURA.REGISTRO.logging.FileHandler', side_effect=PermissionError), \
                    patch('sys.stderr') as consola:
                registrar_evento(3, 'pago_confirmado', 7)
                salida = ''.join(llamada.args[0] for llamada in consola.write.call_args_list)
                self.assertIn('pago_confirmado', salida)
        finally:
            for handler in logger.handlers:
                handler.close()
            logger.handlers, logger.level = anteriores, nivel


class Configuracion(unittest.TestCase):
    # Comprueba nombres personales válidos sin permitir cambiar las cuentas
    # administrativas del servidor ni introducir separadores en la configuración.
    def test_nombres_de_usuario(self):
        self.assertEqual(PREPARAR.validar_usuario('persona_12'),'persona_12')
        for nombre in ('postgres','c11propietario','pg_interno','ana|clave','DOS','1usuario',''):
            with self.assertRaises(DatosInvalidos): PREPARAR.validar_usuario(nombre)

    # Una contraseña se confirma antes de usarla y los errores de escritura
    # se detectan antes de iniciar el servidor o modificar una cuenta.
    def test_confirmacion_de_claves(self):
        with patch.object(PREPARAR,'getpass',side_effect=['ClavePersonal42','ClavePersonal42']):
            self.assertEqual(PREPARAR.pedir_clave('prueba'),'ClavePersonal42')
        with patch.object(PREPARAR,'getpass',side_effect=['ClavePersonal42','OtraClave42']):
            with self.assertRaises(DatosInvalidos): PREPARAR.pedir_clave('prueba')
        for clave in ('corta','x'*129,'ClaveCon\nSalto'):
            with patch.object(PREPARAR,'getpass',return_value=clave):
                with self.assertRaises(DatosInvalidos): PREPARAR.pedir_clave('prueba')

    # Simula dos personas que clonan el trabajo y verifica que cada configuración
    # conserve sus credenciales, incluidos espacios, comillas y signos de la clave.
    def test_configuracion_personal(self):
        with tempfile.TemporaryDirectory() as carpeta:
            raiz=Path(carpeta)
            for usuario in ('persona_uno','persona_dos'):
                with patch.object(PREPARAR,'RAIZ',raiz), patch.object(DATOS,'RAIZ',raiz), patch.dict(os.environ,{},clear=True):
                    clave=' Clave "personal" ñ # = 42 '
                    PREPARAR.guardar_configuracion(usuario,clave,'Persona',usuario+'@example.test')
                    token=os.environ['C11_CLAVE_PASARELA']
                    with patch.dict(os.environ,{},clear=True):
                        DATOS.cargar_configuracion()
                        self.assertEqual(os.environ['PGUSER'],usuario)
                        self.assertEqual(os.environ['PGPASSWORD'],clave)
                        self.assertEqual(os.environ['C11_CLAVE_PASARELA'],token)
                    self.assertEqual((raiz/'.env').stat().st_mode & 0o777,0o600)

    # Conserva la configuración de instalaciones anteriores y respeta una
    # variable indicada desde el entorno sin reemplazarla por la del archivo.
    def test_configuracion_anterior_y_entorno(self):
        with tempfile.TemporaryDirectory() as carpeta:
            raiz=Path(carpeta)
            (raiz/'.env').write_text('PGUSER=usuario_anterior\nPGPASSWORD=AnteriorClave42\n')
            with patch.object(DATOS,'RAIZ',raiz), patch.dict(os.environ,{'PGUSER':'usuario_externo'},clear=True):
                DATOS.cargar_configuracion()
                self.assertEqual(os.environ['PGUSER'],'usuario_externo')
                self.assertEqual(os.environ['PGPASSWORD'],'AnteriorClave42')

    # La conexión recibe los datos elegidos y no utiliza un nombre personal
    # predeterminado cuando falta la preparación de esta copia del proyecto.
    def test_conexion_con_credenciales_elegidas(self):
        with patch.object(DATOS,'cargar_configuracion'), patch.dict(os.environ,{'PGUSER':'persona_nueva','PGPASSWORD':'ClaveElegida42'},clear=True):
            with patch('psycopg.connect') as conectar:
                DATOS.conectar()
                self.assertEqual(conectar.call_args.kwargs['user'],'persona_nueva')
                self.assertEqual(conectar.call_args.kwargs['password'],'ClaveElegida42')
        with patch.object(DATOS,'cargar_configuracion'), patch.dict(os.environ,{},clear=True):
            with self.assertRaises(DatosInvalidos): DATOS.conectar()

    # Una base existente de otra cuenta se conserva sin alterar roles ni claves.
    def test_no_cambiar_propietario_ajeno(self):
        with patch('psycopg.connect') as conectar:
            conexion=conectar.return_value.__enter__.return_value
            conexion.execute.return_value.fetchone.return_value=('otro_usuario',)
            with self.assertRaises(DatosInvalidos):
                PREPARAR.preparar_base('/tmp','persona_nueva','ClaveElegida42')
            self.assertEqual(conexion.execute.call_count,1)

    # Una instalación nueva crea el rol y la base con el usuario solicitado,
    # manteniendo el nombre separado de la contraseña en las instrucciones SQL.
    def test_creacion_con_usuario_elegido(self):
        with patch('psycopg.connect') as conectar:
            conexion=conectar.return_value.__enter__.return_value
            conexion.execute.return_value.fetchone.return_value=None
            PREPARAR.preparar_base('/tmp','persona_nueva','ClaveElegida42')
            consultas=[llamada.args[0].as_string() for llamada in conexion.execute.call_args_list
                       if not isinstance(llamada.args[0],str)]
            self.assertIn('CREATE ROLE "persona_nueva"',consultas[0])
            self.assertIn('CREATE DATABASE c11t1 OWNER "persona_nueva"',consultas[1])

    # La cuenta administrativa conserva su contraseña propia y las cuentas
    # ficticias reciben otra, sin almacenar ninguna de ellas como texto original.
    def test_cuentas_con_claves_separadas(self):
        with patch.object(PREPARAR,'conectar') as conectar:
            conexion=conectar.return_value.__enter__.return_value
            conexion.execute.return_value.fetchone.return_value=None
            PREPARAR.preparar_ejemplos('Persona','persona@example.test','ClaveAdmin42','ClaveEjemplos42')
            cuentas=[llamada.args[1] for llamada in conexion.execute.call_args_list
                     if llamada.args[0].startswith('INSERT INTO usuarios')]
            self.assertEqual(len(cuentas),4)
            for nombre,correo,sal,resumen,rol in cuentas:
                esperada='ClaveAdmin42' if rol=='administracion' else 'ClaveEjemplos42'
                self.assertTrue(comprobar_clave(esperada,{'sal':sal,'clave':resumen}))
                self.assertNotEqual(resumen,esperada)


class PagosLocales(unittest.TestCase):
    # Cada caso trabaja con un archivo temporal para comprobar pagos persistentes
    # sin modificar el archivo que utiliza la demostración del usuario.
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.ruta = Path(self.temporal.name) / 'pagos.sqlite3'
        preparar_archivo(self.ruta)
        self.datos = {'clave': 'compra-local', 'importe': '10.00'}

    # Repetir un cobro o un reembolso conserva un único registro y su estado.
    def test_cobro_y_reembolso_repetidos(self):
        for _ in range(2):
            self.assertEqual(procesar_pago(self.ruta,'cobrar',self.datos)['estado'],'cobrado')
        for _ in range(2):
            self.assertEqual(procesar_pago(self.ruta,'reembolsar',self.datos)['estado'],'reembolsado')
        self.assertEqual(procesar_pago(self.ruta,'cobrar',self.datos)['estado'],'reembolsado')
        with closing(sqlite3.connect(self.ruta)) as conexion, conexion:
            self.assertEqual(conexion.execute('SELECT count(*) FROM pagos').fetchone()[0],1)

    # La anulación evita cobrar después de una cancelación y el rechazo conserva
    # la respuesta original aunque se vuelva a solicitar la misma compra.
    def test_anulacion_y_rechazo(self):
        self.assertEqual(procesar_pago(self.ruta,'reembolsar',self.datos)['estado'],'anulado')
        self.assertEqual(procesar_pago(self.ruta,'cobrar',self.datos)['estado'],'anulado')
        datos = dict(self.datos,clave='rechazo',rechazar=True)
        self.assertEqual(procesar_pago(self.ruta,'cobrar',datos)['estado'],'rechazado')
        datos['rechazar'] = False
        self.assertEqual(procesar_pago(self.ruta,'cobrar',datos)['estado'],'rechazado')

    # Una clave no puede reutilizarse con otro importe y los datos inválidos no
    # deben dejar un cobro incompleto dentro del archivo de la pasarela.
    def test_importes_y_datos_invalidos(self):
        procesar_pago(self.ruta,'cobrar',self.datos)
        with self.assertRaises(Conflicto):
            procesar_pago(self.ruta,'cobrar',dict(self.datos,importe='11'))
        for importe in ('NaN','0','-1','0.001'):
            with self.assertRaises(DatosInvalidos):
                procesar_pago(self.ruta,'cobrar',dict(self.datos,importe=importe))
        with self.assertRaises(DatosInvalidos): procesar_pago(self.ruta,'otra',self.datos)
        with self.assertRaises(DatosInvalidos): procesar_pago(self.ruta,'cobrar',[])

    # Las solicitudes simultáneas con una misma clave confirman un solo registro.
    def test_cobros_simultaneos(self):
        with ThreadPoolExecutor(max_workers=4) as ejecutor:
            resultados = list(ejecutor.map(lambda _: procesar_pago(self.ruta,'cobrar',self.datos),range(8)))
        self.assertTrue(all(r['estado']=='cobrado' for r in resultados))
        with closing(sqlite3.connect(self.ruta)) as conexion, conexion:
            self.assertEqual(conexion.execute('SELECT count(*) FROM pagos').fetchone()[0],1)

    # Comprueba el tratamiento de una solicitud sin abrir un puerto de red,
    # usando el mismo manejador que recibe los mensajes del servidor real.
    def solicitud(self, cuerpo, autorizacion='Bearer clave-local', ruta='/cobrar'):
        manejador = SolicitudPago.__new__(SolicitudPago)
        manejador.server = SimpleNamespace(clave_pasarela='clave-local',ruta_pagos=self.ruta)
        manejador.headers = {'Authorization':autorizacion,'Content-Length':str(len(cuerpo))}
        manejador.rfile, manejador.path = io.BytesIO(cuerpo), ruta
        with patch.object(manejador,'responder') as responder:
            manejador.do_POST()
            return responder.call_args.args

    # Una clave incorrecta, un JSON roto o un mensaje demasiado grande se rechazan.
    def test_solicitudes_http(self):
        cuerpo = json.dumps(self.datos).encode()
        self.assertEqual(self.solicitud(cuerpo)[0],200)
        self.assertEqual(self.solicitud(cuerpo,'Bearer otra')[0],401)
        self.assertEqual(self.solicitud(b'{')[0],400)
        self.assertEqual(self.solicitud(b' '*2049)[0],400)
        self.assertEqual(self.solicitud(cuerpo,ruta='/otra')[0],400)
        self.assertEqual(self.solicitud(json.dumps(dict(self.datos,importe='11')).encode())[0],409)

    # Conecta el cliente con el manejador mediante un transporte controlado para
    # verificar cabeceras, JSON y resultados sin depender de permisos de red.
    def test_cliente_y_servicio(self):
        def transportar(solicitud, timeout):
            self.assertEqual(timeout,5)
            codigo, resultado = self.solicitud(solicitud.data,
                solicitud.get_header('Authorization'),solicitud.full_url.rsplit(':55433',1)[-1])
            if codigo != 200:
                raise HTTPError(solicitud.full_url,codigo,'Error',{},None)
            return io.BytesIO(json.dumps(resultado).encode())
        pasarela = PasarelaPrueba(clave='clave-local')
        with patch('CALIDAD.INFRAESTRUCTURA.PAGOS.urlopen',side_effect=transportar):
            self.assertEqual(pasarela.cobrar('compra-local','10'),'cobrado')
            self.assertEqual(pasarela.reembolsar('compra-local','10'),'reembolsado')
            with self.assertRaises(Conflicto): pasarela.cobrar('compra-local','11')

    # Un corte o una respuesta inválida se conservan como resultado desconocido,
    # evitando inventar un rechazo y liberar stock que todavía puede estar vendido.
    def test_respuestas_invalidas_y_cortes(self):
        pasarela = PasarelaPrueba(clave='clave-local')
        for cuerpo in (b'{',b'[]',b'{"estado":"desconocido"}'):
            with patch('CALIDAD.INFRAESTRUCTURA.PAGOS.urlopen',return_value=io.BytesIO(cuerpo)):
                with self.assertRaises(PagoNoDisponible): pasarela.cobrar('compra','10')
        with patch('CALIDAD.INFRAESTRUCTURA.PAGOS.urlopen',side_effect=URLError('Corte')):
            with self.assertRaises(PagoNoDisponible): pasarela.cobrar('compra','10')

    # La respuesta puede perderse después de guardar el cobro y al reintentar
    # se recupera ese registro, comprobando que el corte no produzca otro pago.
    def test_respuesta_perdida_despues_del_cobro(self):
        pasarela = PasarelaPrueba(clave='clave-local')
        def perder_respuesta(solicitud, timeout):
            procesar_pago(self.ruta,'cobrar',json.loads(solicitud.data))
            raise URLError('Respuesta perdida después de confirmar')
        with patch('CALIDAD.INFRAESTRUCTURA.PAGOS.urlopen',side_effect=perder_respuesta):
            with self.assertRaises(PagoNoDisponible): pasarela.cobrar('compra-local','10')
        respuesta = procesar_pago(self.ruta,'cobrar',self.datos)
        with patch('CALIDAD.INFRAESTRUCTURA.PAGOS.urlopen',return_value=io.BytesIO(json.dumps(respuesta).encode())):
            self.assertEqual(pasarela.cobrar('compra-local','10'),'cobrado')
        with closing(sqlite3.connect(self.ruta)) as conexion, conexion:
            self.assertEqual(conexion.execute('SELECT count(*) FROM pagos').fetchone()[0],1)


@unittest.skipUnless(INTEGRACION,'Use --integracion con PostgreSQL preparado')
class Integracion(unittest.TestCase):
    # Selecciona un esquema exclusivo de estas pruebas sin borrar las tablas del ejemplo.
    @classmethod
    def setUpClass(cls):
        cls.anterior=os.environ.get('C11_ESQUEMA')
        cls.esquema='pruebas_c11_'+uuid.uuid4().hex
        os.environ['C11_ESQUEMA']=cls.esquema
        cls.sal,cls.clave=derivar_clave('ClaveEjemplo42')
        cls.temporal=tempfile.TemporaryDirectory()
        cls.ruta_pagos=Path(cls.temporal.name)/'pagos.sqlite3'
        cls.servidor=crear_servidor(cls.ruta_pagos,'clave-de-pruebas',0)
        cls.hilo=threading.Thread(target=cls.servidor.serve_forever,daemon=True)
        cls.hilo.start()

    # Renueva las tablas temporales y prepara cuentas para cada caso independiente.
    def setUp(self):
        from psycopg import sql
        with closing(sqlite3.connect(self.ruta_pagos)) as pagos, pagos:
            pagos.execute('DELETE FROM pagos')
        self.pasarela=PasarelaPrueba(url=f'http://127.0.0.1:{self.servidor.server_port}',clave='clave-de-pruebas')
        with DATOS.conectar() as conexion:
            conexion.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(self.esquema)))
            esquema=(DATOS.RAIZ/'BASE DE DATOS'/'ESQUEMA.sql').read_text().replace('c11_clase',self.esquema)
            conexion.execute(esquema)
            for nombre,rol in (('admin','administracion'),('doctor','doctor'),('recepcion','recepcion'),('uno','cliente'),('dos','cliente')):
                DATOS.guardar_usuario(conexion,nombre,nombre+'@example.test',self.sal,self.clave,rol)
            conexion.execute("INSERT INTO especialidades(nombre) VALUES ('General')")
            DATOS.guardar_doctor(conexion,2,1)
            DATOS.guardar_producto(conexion,'Cuaderno','Papelería',Decimal('10'),1)
        self.admin={'id':1,'nombre':'admin','rol':'administracion'}
        self.doctor={'id':2,'nombre':'doctor','rol':'doctor'}
        self.cliente={'id':4,'nombre':'uno','rol':'cliente'}
        self.otro={'id':5,'nombre':'dos','rol':'cliente'}
        self.paciente=CLINICA.registrar_paciente(self.admin,'DEMO001','Paciente',date(2000,1,1),'0999999999','Ninguno')
        COMERCIO.invalidar_catalogo()

    # Elimina sólo el esquema temporal y restaura la configuración al finalizar.
    @classmethod
    def tearDownClass(cls):
        from psycopg import sql
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.hilo.join()
        cls.temporal.cleanup()
        with DATOS.conectar() as conexion:
            conexion.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(cls.esquema)))
        if cls.anterior is None: os.environ.pop('C11_ESQUEMA',None)
        else: os.environ['C11_ESQUEMA']=cls.anterior

    # El intervalo ocupado se rechaza y una cita consecutiva se acepta.
    def test_agenda(self):
        inicio=datetime.now(timezone.utc)+timedelta(days=1)
        CLINICA.programar_cita(self.admin,self.paciente,1,inicio,inicio+timedelta(minutes=30))
        with self.assertRaises(Conflicto):
            CLINICA.programar_cita(self.admin,self.paciente,1,inicio,inicio+timedelta(minutes=30))
        CLINICA.programar_cita(self.admin,self.paciente,1,inicio+timedelta(minutes=30),inicio+timedelta(hours=1))

    # Un fallo posterior a escribir la atención revierte también la factura y el estado.
    def test_atencion_atomica(self):
        with DATOS.conectar() as conexion:
            cita=DATOS.guardar_cita(conexion,self.paciente,1,datetime.now(timezone.utc)-timedelta(hours=1),datetime.now(timezone.utc))
        original=DATOS.guardar_atencion
        def fallar(conexion,*valores):
            original(conexion,*valores)
            raise RuntimeError('Fallo controlado')
        with patch.object(DATOS,'guardar_atencion',side_effect=fallar):
            with self.assertRaises(RuntimeError): CLINICA.registrar_atencion(self.doctor,cita,'Control','20')
        with DATOS.conectar() as conexion:
            self.assertEqual(DATOS.uno(conexion,'SELECT count(*) AS n FROM atenciones')['n'],0)
            self.assertFalse(DATOS.uno(conexion,'SELECT atendida FROM citas WHERE id=%s',(cita,))['atendida'])
        self.assertIsInstance(CLINICA.registrar_atencion(self.doctor,cita,'Control','20'),int)

    # Sólo una reserva simultánea puede quedarse con la última unidad.
    def test_compras_simultaneas(self):
        for cliente in (self.cliente,self.otro): COMERCIO.cambiar_carrito(cliente,1,1)
        barrera=threading.Barrier(2)
        def reservar(usuario):
            barrera.wait()
            try: return COMERCIO.reservar_pedido(usuario,str(uuid.uuid4()))
            except Conflicto: return None
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados=list(ejecutor.map(reservar,(self.cliente,self.otro)))
        self.assertEqual(sum(r is not None for r in resultados),1)
        with DATOS.conectar() as conexion: self.assertEqual(DATOS.producto(conexion,1)['stock'],0)

    # Repetir una compra devuelve el mismo pedido y no habilita otra cuenta para verlo.
    def test_compra_repetida(self):
        COMERCIO.cambiar_carrito(self.cliente,1,1)
        pedido=COMERCIO.reservar_pedido(self.cliente,'compra-uno')
        self.assertEqual(COMERCIO.reservar_pedido(self.cliente,'compra-uno'),pedido)
        with self.assertRaises(AccesoDenegado): COMERCIO.consultar_pedido(self.otro,pedido)

    # Una caída conserva el pedido pendiente para confirmar con la misma clave después.
    def test_pago_pendiente(self):
        COMERCIO.cambiar_carrito(self.cliente,1,1)
        pedido=COMERCIO.reservar_pedido(self.cliente,'compra-uno')
        with self.assertRaises(PagoNoDisponible): COMERCIO.confirmar_pago(self.cliente,pedido,PasarelaPrueba(False))
        self.assertEqual(COMERCIO.consultar_pedido(self.cliente,pedido)['estado'],'pendiente')
        self.assertEqual(COMERCIO.confirmar_pago(self.cliente,pedido,self.pasarela),'pagado')

    # Cobrar y cancelar repetidamente no duplica cobros ni devoluciones de stock.
    def test_pago_y_reembolso(self):
        COMERCIO.cambiar_carrito(self.cliente,1,1)
        pedido=COMERCIO.reservar_pedido(self.cliente,'compra-uno')
        pasarela=self.pasarela
        for _ in range(2): self.assertEqual(COMERCIO.confirmar_pago(self.cliente,pedido,pasarela),'pagado')
        for _ in range(2): self.assertEqual(COMERCIO.cancelar_pedido(self.cliente,pedido,pasarela),'cancelado')
        with DATOS.conectar() as conexion:
            self.assertEqual(DATOS.producto(conexion,1)['stock'],1)
        with closing(sqlite3.connect(self.ruta_pagos)) as pagos, pagos:
            self.assertEqual(pagos.execute('SELECT estado FROM pagos').fetchone()[0],'reembolsado')

    # Un pago rechazado libera la reserva sin marcar la compra como pagada.
    def test_rechazo(self):
        COMERCIO.cambiar_carrito(self.cliente,1,1)
        pedido=COMERCIO.reservar_pedido(self.cliente,'compra-uno')
        self.assertEqual(COMERCIO.confirmar_pago(self.cliente,pedido,self.pasarela,True),'cancelado')
        with DATOS.conectar() as conexion: self.assertEqual(DATOS.producto(conexion,1)['stock'],1)

    # El cobro externo puede confirmarse antes de fallar la escritura del pedido,
    # por eso el reintento recupera el pago y completa sólo la parte pendiente.
    def test_cobro_confirmado_y_pedido_pendiente(self):
        COMERCIO.cambiar_carrito(self.cliente,1,1)
        pedido=COMERCIO.reservar_pedido(self.cliente,'recuperar-cobro')
        with patch.object(DATOS,'cambiar_estado',side_effect=RuntimeError('Fallo controlado')):
            with self.assertRaises(RuntimeError):
                COMERCIO.confirmar_pago(self.cliente,pedido,self.pasarela)
        self.assertEqual(COMERCIO.consultar_pedido(self.cliente,pedido)['estado'],'pendiente')
        self.assertEqual(COMERCIO.confirmar_pago(self.cliente,pedido,self.pasarela),'pagado')
        with closing(sqlite3.connect(self.ruta_pagos)) as pagos, pagos:
            self.assertEqual(pagos.execute('SELECT count(*) FROM pagos').fetchone()[0],1)

    # Una caída al reembolsar deja la cancelación pendiente y conserva el stock
    # reservado hasta confirmar que la pasarela devolvió o anuló el cobro.
    def test_cancelacion_pendiente(self):
        COMERCIO.cambiar_carrito(self.cliente,1,1)
        pedido=COMERCIO.reservar_pedido(self.cliente,'cancelar-pendiente')
        COMERCIO.confirmar_pago(self.cliente,pedido,self.pasarela)
        with self.assertRaises(PagoNoDisponible):
            COMERCIO.cancelar_pedido(self.cliente,pedido,PasarelaPrueba(False))
        self.assertEqual(COMERCIO.consultar_pedido(self.cliente,pedido)['estado'],'reembolso_pendiente')
        with DATOS.conectar() as conexion: self.assertEqual(DATOS.producto(conexion,1)['stock'],0)
        self.assertEqual(COMERCIO.cancelar_pedido(self.cliente,pedido,self.pasarela),'cancelado')
        with DATOS.conectar() as conexion: self.assertEqual(DATOS.producto(conexion,1)['stock'],1)

    # Si falla la tienda después de un reembolso, volver a cancelar no reembolsa
    # otra vez y completa la devolución de stock en una sola transacción local.
    def test_reembolso_confirmado_y_stock_pendiente(self):
        COMERCIO.cambiar_carrito(self.cliente,1,1)
        pedido=COMERCIO.reservar_pedido(self.cliente,'recuperar-stock')
        COMERCIO.confirmar_pago(self.cliente,pedido,self.pasarela)
        original=DATOS.devolver_stock
        def fallar(conexion,pedido_id):
            original(conexion,pedido_id)
            raise RuntimeError('Fallo controlado')
        with patch.object(DATOS,'devolver_stock',side_effect=fallar):
            with self.assertRaises(RuntimeError):
                COMERCIO.cancelar_pedido(self.cliente,pedido,self.pasarela)
        with DATOS.conectar() as conexion: self.assertEqual(DATOS.producto(conexion,1)['stock'],0)
        self.assertEqual(COMERCIO.cancelar_pedido(self.cliente,pedido,self.pasarela),'cancelado')
        self.assertEqual(COMERCIO.cancelar_pedido(self.cliente,pedido,self.pasarela),'cancelado')
        with DATOS.conectar() as conexion: self.assertEqual(DATOS.producto(conexion,1)['stock'],1)

    # La recuperación de pedidos muestra sólo los de la cuenta autenticada.
    def test_listar_pedidos_propios(self):
        COMERCIO.cambiar_carrito(self.cliente,1,1)
        pedido=COMERCIO.reservar_pedido(self.cliente,'pedido-propio')
        self.assertEqual(COMERCIO.listar_pedidos(self.cliente)[0]['id'],pedido)
        self.assertEqual(COMERCIO.listar_pedidos(self.otro),[])
        with self.assertRaises(AccesoDenegado): COMERCIO.listar_pedidos(self.doctor)

    # La modificación desde el servicio descarta la caché del catálogo.
    def test_cache_actualizada(self):
        self.assertEqual(COMERCIO.buscar_catalogo()[0]['stock'],1)
        COMERCIO.actualizar_stock(self.admin,1,4)
        self.assertEqual(COMERCIO.buscar_catalogo()[0]['stock'],4)


if __name__=='__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        cerrar_avisos()
