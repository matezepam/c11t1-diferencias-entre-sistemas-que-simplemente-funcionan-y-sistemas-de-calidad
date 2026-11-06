# La interfaz solicita datos y muestra resultados, mientras las funciones de
# negocio comprueban permisos y reglas y DATOS contiene las consultas de PostgreSQL.

from datetime import date, datetime
from getpass import getpass
import subprocess
import sys
import uuid
from CALIDAD.SERVICIOS import CLINICA, COMERCIO, CUENTAS
from CALIDAD.INFRAESTRUCTURA.DATOS import RAIZ
from CALIDAD.COMUN.ERRORES import ErrorAplicacion
from CALIDAD.INFRAESTRUCTURA.PAGOS import PasarelaPrueba
from CALIDAD.INFRAESTRUCTURA.REGISTRO import registrar_evento, cerrar_avisos


# Ejecuta una acción del menú y presenta errores sin revelar SQL ni contraseñas,
# conservando los mensajes de negocio y señalando por separado conversiones inválidas.
def ejecutar(accion):
    try:
        return accion()
    except ErrorAplicacion as error:
        print(error)
    except (ValueError, OverflowError):
        print('Revise los números y fechas ingresados')
    except ImportError:
        print('Instale las dependencias con python -m pip install -r REQUISITOS.txt')
    except Exception as error:
        registrar_evento('interfaz', 'error_'+type(error).__name__, '-')
        print('No se completó la operación, compruebe PostgreSQL y reintente')
    return None


# Presenta listas de filas con un mismo formato sin hacer consultas adicionales.
def mostrar(filas):
    if not filas:
        print('No hay registros')
    else:
        for fila in filas:
            print(fila)


# Pide los datos personales y devuelve el identificador del paciente registrado.
def pedir_paciente(usuario):
    documento = input('Documento: ')
    nombre = input('Nombre: ')
    nacimiento = date.fromisoformat(input('Nacimiento AAAA-MM-DD: '))
    telefono = input('Teléfono: ')
    antecedentes = input('Antecedentes o ninguno: ')
    return CLINICA.registrar_paciente(usuario, documento, nombre, nacimiento, telefono, antecedentes)


# Pide un intervalo con fecha y zona horaria para no confundir un texto de hora
# aislada con el momento completo en que debe comenzar y terminar la cita.
def pedir_cita(usuario):
    paciente = int(input('Id paciente: '))
    doctor = int(input('Id doctor: '))
    print('Formato de ejemplo 2030-11-06T10:00-05:00')
    inicio = datetime.fromisoformat(input('Inicio: '))
    fin = datetime.fromisoformat(input('Fin: '))
    return CLINICA.programar_cita(usuario, paciente, doctor, inicio, fin)


# Reúne los datos de atención en la interfaz y deja la comprobación del doctor,
# el horario y la transacción en el servicio de la clínica.
def pedir_atencion(usuario):
    cita = int(input('Id cita: '))
    observacion = input('Observación: ')
    importe = input('Importe: ')
    return CLINICA.registrar_atencion(usuario, cita, observacion, importe)


# Recoge los datos del producto antes de llamar a la función del comercio,
# evitando mezclar todas las entradas con la selección de opciones del menú.
def pedir_producto(usuario):
    nombre = input('Nombre: ')
    categoria = input('Categoría: ')
    precio = input('Precio: ')
    stock = int(input('Stock: '))
    return COMERCIO.registrar_producto(usuario, nombre, categoria, precio, stock)


# Solicita la cantidad total que debe quedar en el carrito y mantiene esta
# conversión dentro de ejecutar para que una entrada inválida no cierre el menú.
def pedir_cantidad_carrito(usuario):
    producto = int(input('Id producto: '))
    cantidad = int(input('Cantidad total, cero para quitar: '))
    return COMERCIO.cambiar_carrito(usuario, producto, cantidad)


# Solicita las dos referencias que vinculan una cuenta médica y su especialidad.
def pedir_doctor(usuario):
    cuenta = int(input('Id cuenta: '))
    especialidad = int(input('Id especialidad: '))
    return CLINICA.registrar_doctor(usuario, cuenta, especialidad)


# Pide una cuenta nueva y devuelve su id, usando cliente por defecto y exigiendo
# administración cuando se solicita un rol del personal.
def pedir_cuenta(administrador=None):
    nombre, correo = input('Nombre: '), input('Correo: ')
    clave = getpass('Contraseña de aplicación: ')
    rol = input('Rol administracion, recepcion o doctor: ') if administrador else 'cliente'
    return CUENTAS.registrar_usuario(nombre, correo, clave, rol, administrador)


# Conecta cada opción clínica con una función específica y mantiene la cuenta
# recibida del inicio de sesión, sin pedir permisos o identificadores de otro usuario.
def menu_clinica(usuario):
    while True:
        print('\nCLINICA DE CALIDAD')
        print('1. Registrar paciente\n2. Pacientes\n3. Doctores\n4. Programar cita\n5. Agenda')
        print('6. Atención y factura\n7. Historial\n8. Facturas\n9. Nueva especialidad')
        print('10. Nueva cuenta de personal\n11. Asociar doctor y especialidad\n0. Volver')
        opcion = input('Opción: ').strip()
        if opcion == '0':
            return
        elif opcion == '1':
            print('Paciente:', ejecutar(lambda: pedir_paciente(usuario)))
        elif opcion == '2':
            mostrar(ejecutar(lambda: CLINICA.listar_pacientes(usuario)))
        elif opcion == '3':
            mostrar(ejecutar(lambda: CLINICA.listar_doctores(usuario)))
        elif opcion == '4':
            print('Cita:', ejecutar(lambda: pedir_cita(usuario)))
        elif opcion == '5':
            mostrar(ejecutar(lambda: CLINICA.listar_citas(usuario)))
        elif opcion == '6':
            print('Factura:', ejecutar(lambda: pedir_atencion(usuario)))
        elif opcion == '7':
            resultado = ejecutar(lambda: CLINICA.consultar_historial(usuario, int(input('Id paciente: '))))
            if resultado:
                paciente, atenciones = resultado
                print(paciente)
                mostrar(atenciones)
        elif opcion == '8':
            mostrar(ejecutar(lambda: CLINICA.listar_facturas(usuario)))
        elif opcion == '9':
            print('Especialidad:', ejecutar(lambda: CLINICA.agregar_especialidad(usuario, input('Nombre: '))))
        elif opcion == '10':
            print('Cuenta:', ejecutar(lambda: pedir_cuenta(usuario)))
        elif opcion == '11':
            print('Doctor:', ejecutar(lambda: pedir_doctor(usuario)))
        else:
            print('Seleccione una opción del menú')


# Reserva primero y muestra el id antes del pago para que un fallo posterior
# pueda recuperarse desde el menú sin crear una segunda compra.
def pedir_compra(usuario, pasarela):
    clave = str(uuid.uuid4())
    pedido = COMERCIO.reservar_pedido(usuario, clave, input('Envío normal o rapido: '))
    print('Pedido creado:', pedido)
    rechazar = input('Simular pago rechazado, s/n: ').strip().lower() == 's'
    print('Resultado:', COMERCIO.confirmar_pago(usuario, pedido, pasarela, rechazar))
    return pedido


# Utiliza el cliente de la pasarela de prueba y conecta las opciones del
# comercio, dejando los cobros en el proceso independiente de PASARELA/SERVIDOR.py.
def menu_comercio(usuario):
    pasarela = PasarelaPrueba()
    while True:
        print('\nCOMERCIO DE CALIDAD')
        print('1. Catálogo\n2. Perfil\n3. Cambiar nombre\n4. Carrito\n5. Cambiar cantidad\n6. Comprar')
        print('7. Consultar pedido\n8. Reintentar pago\n9. Cancelar pedido\n10. Registrar producto')
        print('11. Actualizar stock\n12. Avanzar pedido\n13. Mis pedidos\n0. Volver')
        opcion = input('Opción: ').strip()
        if opcion == '0':
            return
        elif opcion == '1':
            mostrar(ejecutar(lambda: COMERCIO.buscar_catalogo(input('Nombre: '), input('Categoría o Enter: '))))
        elif opcion == '2':
            print(ejecutar(lambda: CUENTAS.consultar_perfil(usuario)))
        elif opcion == '3':
            print(ejecutar(lambda: CUENTAS.consultar_perfil(usuario, input('Nuevo nombre: '))))
        elif opcion == '4':
            mostrar(ejecutar(lambda: COMERCIO.consultar_carrito(usuario)))
        elif opcion == '5':
            mostrar(ejecutar(lambda: pedir_cantidad_carrito(usuario)))
        elif opcion == '6':
            ejecutar(lambda: pedir_compra(usuario, pasarela))
        elif opcion == '7':
            print(ejecutar(lambda: COMERCIO.consultar_pedido(usuario, int(input('Id pedido: ')))))
        elif opcion == '8':
            print(ejecutar(lambda: COMERCIO.confirmar_pago(usuario, int(input('Id pedido: ')), pasarela)))
        elif opcion == '9':
            print(ejecutar(lambda: COMERCIO.cancelar_pedido(usuario, int(input('Id pedido: ')), pasarela)))
        elif opcion == '10':
            print('Producto:', ejecutar(lambda: pedir_producto(usuario)))
        elif opcion == '11':
            ejecutar(lambda: COMERCIO.actualizar_stock(usuario, int(input('Id producto: ')), int(input('Stock disponible: '))))
        elif opcion == '12':
            ejecutar(lambda: COMERCIO.avanzar_pedido(usuario, int(input('Id pedido: ')), input('Estado enviado o entregado: ')))
        elif opcion == '13':
            mostrar(ejecutar(lambda: COMERCIO.listar_pedidos(usuario)))
        else:
            print('Seleccione una opción del menú')


# Abre las versiones básicas por separado y pide una cuenta sólo para las de
# calidad, cerrando los avisos pendientes al terminar el programa normalmente.
def main():
    try:
        while True:
            print('\nC11T1 SISTEMAS BASICOS Y DE CALIDAD')
            print('1. Clínica básica\n2. Clínica de calidad\n3. Comercio básico\n4. Comercio de calidad\n5. Crear cuenta de cliente\n0. Salir')
            opcion = input('Opción: ').strip()
            if opcion == '0':
                return
            elif opcion in ('1','3'):
                archivo = 'EJERCICIO 1 CLINICA BASICA.py' if opcion=='1' else 'EJERCICIO 2 COMERCIO BASICO.py'
                subprocess.run([sys.executable, str(RAIZ/'BASICOS'/archivo)], check=True)
            elif opcion in ('2','4'):
                usuario = ejecutar(lambda: CUENTAS.iniciar_sesion(input('Correo: '), getpass('Contraseña: ')))
                if usuario:
                    if opcion=='2':
                        menu_clinica(usuario)
                    else:
                        menu_comercio(usuario)
            elif opcion == '5':
                print('Cuenta:', ejecutar(pedir_cuenta))
            else:
                print('Seleccione una opción del menú')
    finally:
        cerrar_avisos()


if __name__ == '__main__':
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print('\nPrograma finalizado')
