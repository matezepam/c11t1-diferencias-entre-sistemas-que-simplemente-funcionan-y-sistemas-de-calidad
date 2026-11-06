# Prepara una instancia PostgreSQL exclusiva de este trabajo dentro de la carpeta
# personal para no modificar servicios ni bases de otros proyectos y crea los datos
# de ejemplo sin borrar pacientes, productos o pedidos que ya se hayan registrado.

from getpass import getpass, getuser
from pathlib import Path
import os
import shutil
import subprocess
import secrets
import json
import re

from CALIDAD.INFRAESTRUCTURA.DATOS import RAIZ, cargar_configuracion, conectar
from CALIDAD.COMUN.SEGURIDAD import derivar_clave, texto
from CALIDAD.COMUN.ERRORES import ErrorAplicacion, DatosInvalidos


# Comprueba los ejecutables antes de iniciar el servidor y devuelve el directorio
# de datos y sockets locales, dejando los archivos de PostgreSQL fuera de Git.
def iniciar_postgres():
    for programa in ('initdb', 'pg_ctl'):
        if not shutil.which(programa):
            raise RuntimeError(f'Falta {programa}, instale PostgreSQL antes de continuar')
    carpeta = Path.home() / '.local/share/c11t1/postgres'
    carpeta.parent.mkdir(parents=True, exist_ok=True)
    sockets = carpeta.parent / 'sockets'
    sockets.mkdir(exist_ok=True, mode=0o700)
    if not (carpeta / 'PG_VERSION').exists():
        subprocess.run(['initdb', '-D', str(carpeta), '-U', 'c11propietario',
                        '--auth-local=peer', '--auth-host=scram-sha-256',
                        '--encoding=UTF8', '--no-locale'], check=True)
    estado = subprocess.run(['pg_ctl', '-D', str(carpeta), 'status'], capture_output=True)
    if estado.returncode != 0:
        # El mapeo permite a la cuenta local preparar la base sin darle al usuario
        # de la aplicación privilegios de superusuario ni acceso desde otra máquina.
        (carpeta / 'pg_ident.conf').write_text(f'c11local {getuser()} c11propietario\n')
        (carpeta / 'pg_hba.conf').write_text(
            'local all c11propietario peer map=c11local\n'
            'local all all scram-sha-256\n'
            'host all all 127.0.0.1/32 scram-sha-256\n'
            'host all all ::1/128 scram-sha-256\n')
        subprocess.run(['pg_ctl', '-D', str(carpeta), '-l', str(carpeta.parent / 'postgres.log'),
                        '-o', f'-p 55432 -k {sockets} -h 127.0.0.1', 'start'], check=True)
    return sockets


# Comprueba el nombre antes de usarlo en PostgreSQL o DBeaver y evita que la
# cuenta del programa sustituya las cuentas administrativas del servidor.
def validar_usuario(usuario):
    if not isinstance(usuario, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', usuario):
        raise DatosInvalidos('Use un usuario de hasta 63 letras minúsculas, números o guiones bajos, comenzando con una letra')
    if usuario in ('postgres', 'c11propietario') or usuario.startswith('pg_'):
        raise DatosInvalidos('Elija otro nombre para la cuenta de la aplicación')
    return usuario


# Solicita la contraseña sin mostrarla y la confirma antes de cambiar la base,
# evitando crear accesos con una clave escrita por error o una clave fija del repositorio.
def pedir_clave(nombre):
    clave = getpass(f'Contraseña para {nombre}, mínimo ocho caracteres: ')
    if not 8 <= len(clave) <= 128 or any(c in clave for c in ('\x00', '\n', '\r')):
        raise DatosInvalidos('La contraseña debe tener entre 8 y 128 caracteres y no contener saltos de línea')
    if clave != getpass('Repita la contraseña: '):
        raise DatosInvalidos('Las contraseñas no coinciden')
    return clave


# Crea la cuenta elegida y la base sin dar permisos de administración del clúster,
# utilizando identificadores SQL separados de los valores de la contraseña.
def preparar_base(sockets, usuario, clave):
    import psycopg
    from psycopg import sql

    validar_usuario(usuario)
    with psycopg.connect(host=str(sockets), port=55432, user='c11propietario',
                         dbname='postgres', autocommit=True) as conexion:
        base = conexion.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='c11t1'").fetchone()
        if base and base[0] != usuario:
            raise DatosInvalidos('Esta base ya pertenece a otra cuenta, use el usuario con que la preparó en este equipo')
        rol = conexion.execute('SELECT rolsuper,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=%s', (usuario,)).fetchone()
        if rol and any(rol):
            raise DatosInvalidos('Elija una cuenta sin privilegios administrativos para la aplicación')
        if not rol:
            consulta = sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}')
        else:
            consulta = sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}')
        conexion.execute(consulta.format(sql.Identifier(usuario), sql.Literal(clave)))
        if not base:
            conexion.execute(sql.SQL('CREATE DATABASE c11t1 OWNER {}').format(sql.Identifier(usuario)))


# Guarda la conexión y la identificación administrativa sólo en el equipo del
# usuario, conservando la clave de la pasarela al repetir la preparación.
def guardar_configuracion(usuario, clave, nombre_admin, correo_admin):
    configuracion = {'PGHOST': '127.0.0.1', 'PGPORT': '55432', 'PGDATABASE': 'c11t1',
                     'PGUSER': usuario, 'PGPASSWORD': clave,
                     'C11_ADMIN_NOMBRE': nombre_admin, 'C11_ADMIN_CORREO': correo_admin,
                     'C11_CLAVE_PASARELA': os.environ.get('C11_CLAVE_PASARELA') or secrets.token_hex(24)}
    ruta = RAIZ / '.env'
    ruta.touch(mode=0o600, exist_ok=True)
    ruta.chmod(0o600)
    # Las comillas permiten conservar espacios y signos de una contraseña sin
    # confundirlos con nuevas variables de configuración al leer el archivo.
    ruta.write_text(''.join(f'{k}={json.dumps(v, ensure_ascii=False)}\n' for k,v in configuracion.items()), encoding='utf-8')
    os.environ.update(configuracion)


# Crea la cuenta administrativa personal y las cuentas ficticias del ejercicio,
# guardando sus resúmenes y utilizando otra contraseña para los usuarios de prueba.
def preparar_ejemplos(nombre_admin, correo_admin, clave_admin, clave_ejemplos):
    cuentas = [(nombre_admin, correo_admin, 'administracion', clave_admin)]
    cuentas += [(nombre, nombre+'@example.test', rol, clave_ejemplos)
                for nombre, rol in (('doctor','doctor'), ('recepcion','recepcion'), ('cliente','cliente'))]
    with conectar() as conexion:
        conexion.execute((RAIZ / 'BASE DE DATOS' / 'ESQUEMA.sql').read_text())
        for nombre, correo, rol, clave in cuentas:
            previa = conexion.execute('SELECT rol FROM usuarios WHERE correo=%s', (correo,)).fetchone()
            if previa and previa['rol'] != rol:
                raise DatosInvalidos('Ese correo ya pertenece a una cuenta con otro rol')
            sal, resumen = derivar_clave(clave)
            conexion.execute('''INSERT INTO usuarios(nombre,correo,sal,clave,rol) VALUES (%s,%s,%s,%s,%s)
                              ON CONFLICT(correo) DO UPDATE SET nombre=excluded.nombre,sal=excluded.sal,clave=excluded.clave''',
                              (nombre, correo, sal, resumen, rol))
        conexion.execute("INSERT INTO especialidades(nombre) VALUES ('Medicina general') ON CONFLICT DO NOTHING")
        conexion.execute('''INSERT INTO doctores(usuario_id,especialidad_id) SELECT u.id,e.id
                          FROM usuarios u,especialidades e WHERE u.correo='doctor@example.test'
                          AND e.nombre='Medicina general' ON CONFLICT(usuario_id) DO NOTHING''')
        if not conexion.execute('SELECT id FROM productos LIMIT 1').fetchone():
            conexion.execute("INSERT INTO productos(nombre,categoria,precio,stock) VALUES ('Cuaderno','Papelería',3.50,10),('Lápiz','Papelería',0.75,20)")


# Abre DBeaver sin incluir la contraseña en sus argumentos y deja que el programa
# solicite la clave o su controlador, usando una conexión guardada del proyecto.
def preparar_dbeaver():
    usuario = validar_usuario(os.environ['PGUSER'])
    print(f'DBeaver: host 127.0.0.1, puerto 55432, base c11t1, usuario {usuario}, esquema c11_clase')
    if shutil.which('dbeaver'):
        subprocess.Popen(['dbeaver', '-con',
            f'driver=postgresql|host=127.0.0.1|port=55432|database=c11t1|user={usuario}|name=C11T1 POSTGRESQL|create=true|save=true',
            '-f', str(RAIZ/'BASE DE DATOS'/'CONSULTAS.sql')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# Prepara el trabajo con las credenciales de quien lo ejecuta y pide los datos
# antes de modificar la base, manteniendo las contraseñas fuera del código.
def main():
    try:
        import psycopg
    except ImportError:
        raise SystemExit('Instale primero python -m pip install -r REQUISITOS.txt')
    cargar_configuracion()
    predeterminado = os.environ.get('PGUSER') or getuser()
    usuario = validar_usuario(input(f'Usuario PostgreSQL [{predeterminado}]: ').strip() or predeterminado)
    clave = pedir_clave('PostgreSQL')
    nombre_admin = texto(input('Nombre de la cuenta administrativa: '), 'Nombre', 120)
    correo_admin = texto(input('Correo de la cuenta administrativa: '), 'Correo', 200).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', correo_admin):
        raise DatosInvalidos('Ingrese un correo válido para administración')
    if correo_admin in ('doctor@example.test', 'recepcion@example.test', 'cliente@example.test'):
        raise DatosInvalidos('Use un correo diferente al de las cuentas de ejemplo')
    clave_admin = pedir_clave('la cuenta administrativa')
    clave_ejemplos = pedir_clave('las cuentas ficticias de doctor, recepción y cliente')
    if clave_admin == clave_ejemplos:
        raise DatosInvalidos('Use una contraseña administrativa distinta de la de las cuentas ficticias')
    sockets = iniciar_postgres()
    preparar_base(sockets, usuario, clave)
    guardar_configuracion(usuario, clave, nombre_admin, correo_admin)
    preparar_ejemplos(nombre_admin, correo_admin, clave_admin, clave_ejemplos)
    preparar_dbeaver()
    print('Preparación terminada, ejecute python -m PASARELA.SERVIDOR')
    print('En otra terminal active el mismo entorno y ejecute python INICIAR.py')
    print(f'Administración: {correo_admin}')
    print('Ejemplos: doctor@example.test, recepcion@example.test y cliente@example.test')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('Preparación cancelada')
    except ErrorAplicacion as error:
        print(error)
        raise SystemExit(1)
    except Exception as error:
        print(f'No se completó la preparación, revise PostgreSQL y sus dependencias ({type(error).__name__})')
        raise SystemExit(1)
