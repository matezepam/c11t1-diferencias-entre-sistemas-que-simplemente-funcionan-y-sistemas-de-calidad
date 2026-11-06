# EJERCICIO 1 CLINICA DE CALIDAD
# Las funciones aplican las reglas del ejercicio y reciben la cuenta autenticada,
# mientras DATOS se ocupa de las consultas y la interfaz de pedir y mostrar información.

from datetime import date, datetime, timedelta, timezone
import re
from CALIDAD.INFRAESTRUCTURA import DATOS
from CALIDAD.COMUN.SEGURIDAD import texto, dinero, entero, exigir_rol
from CALIDAD.COMUN.ERRORES import DatosInvalidos, Conflicto, AccesoDenegado
from CALIDAD.INFRAESTRUCTURA.REGISTRO import registrar_evento


# Registra un paciente y devuelve su id después de validar identificación,
# fecha y contacto, contando los dígitos del teléfono para no aceptar sólo signos.
def registrar_paciente(usuario, documento, nombre, nacimiento, telefono, antecedentes):
    exigir_rol(usuario, ('administracion', 'recepcion'))
    documento = texto(documento, 'Documento', 30)
    nombre = texto(nombre, 'Nombre', 120)
    antecedentes = texto(antecedentes, 'Antecedentes', 4000)
    telefono = texto(telefono, 'Teléfono', 25)
    if not re.fullmatch(r'[A-Za-z0-9-]{4,30}', documento) or not any(c.isalnum() for c in documento):
        raise DatosInvalidos('El documento debe tener entre 4 y 30 letras, números o guiones')
    digitos = sum(caracter.isdigit() for caracter in telefono)
    if not re.fullmatch(r'\+?[0-9 ()-]+', telefono) or not 7 <= digitos <= 15:
        raise DatosInvalidos('El teléfono debe contener entre 7 y 15 dígitos')
    if type(nacimiento) is not date or not date(1900, 1, 1) <= nacimiento <= date.today():
        raise DatosInvalidos('Ingrese una fecha de nacimiento válida y no futura')
    with DATOS.transaccion() as conexion:
        identificador = DATOS.guardar_paciente(conexion, (documento, nombre, nacimiento, telefono, antecedentes))
    registrar_evento(usuario['id'], 'registro_paciente', identificador)
    return identificador


# Devuelve los datos necesarios para elegir paciente sin mostrar sus antecedentes.
def listar_pacientes(usuario):
    exigir_rol(usuario, ('administracion', 'recepcion'))
    with DATOS.transaccion() as conexion:
        return DATOS.pacientes(conexion)


# Devuelve los doctores y sus especialidades a las cuentas del personal.
def listar_doctores(usuario):
    exigir_rol(usuario, ('administracion', 'recepcion', 'doctor'))
    with DATOS.transaccion() as conexion:
        return DATOS.doctores(conexion)


# Reserva una cita y devuelve su id, comprobando los intervalos después de bloquear
# doctor y paciente para que dos reservas simultáneas no acepten el mismo horario.
def programar_cita(usuario, paciente_id, doctor_id, inicio, fin):
    exigir_rol(usuario, ('administracion', 'recepcion'))
    entero(paciente_id)
    entero(doctor_id)
    if not isinstance(inicio, datetime) or not isinstance(fin, datetime) or inicio.tzinfo is None or fin.tzinfo is None:
        raise DatosInvalidos('Ingrese fecha y hora con zona horaria')
    if inicio <= datetime.now(timezone.utc) or not timedelta(minutes=5) <= fin-inicio <= timedelta(hours=8):
        raise DatosInvalidos('La cita debe ser futura y durar entre cinco minutos y ocho horas')
    with DATOS.transaccion() as conexion:
        if not DATOS.bloquear_agenda(conexion, paciente_id, doctor_id):
            raise DatosInvalidos('El paciente y el doctor deben existir')
        if DATOS.buscar_cruce(conexion, paciente_id, doctor_id, inicio, fin):
            raise Conflicto('El paciente o doctor ya tienen una cita en ese intervalo')
        cita_id = DATOS.guardar_cita(conexion, paciente_id, doctor_id, inicio, fin)
    registrar_evento(usuario['id'], 'programacion_cita', cita_id)
    return cita_id


# Guarda observación e importe facturado y devuelve el número de atención,
# agrupando esas escrituras y el estado de la cita para revertir todo si algo falla.
def registrar_atencion(usuario, cita_id, observacion, importe):
    exigir_rol(usuario, ('doctor',))
    entero(cita_id)
    observacion, importe = texto(observacion, 'Observación', 8000), dinero(importe)
    with DATOS.transaccion() as conexion:
        cita = DATOS.cita_para_atender(conexion, cita_id)
        if not cita or cita['usuario_id'] != usuario['id']:
            raise AccesoDenegado('Sólo el doctor asignado puede registrar esta atención')
        if cita['atendida'] or cita['inicio'] > datetime.now(timezone.utc):
            raise Conflicto('La cita ya se atendió o todavía no comienza')
        factura_id = DATOS.guardar_atencion(conexion, cita_id, observacion, importe)
    registrar_evento(usuario['id'], 'atencion_y_factura', cita_id)
    return factura_id


# Devuelve antecedentes y atenciones sólo al doctor que tiene una cita con el
# paciente, comprobando ese vínculo antes de leer la información médica.
def consultar_historial(usuario, paciente_id):
    exigir_rol(usuario, ('doctor',))
    entero(paciente_id)
    with DATOS.transaccion() as conexion:
        if not DATOS.doctor_asignado(conexion, paciente_id, usuario['id']):
            raise AccesoDenegado('No está asignado a este paciente')
        resultado = DATOS.historial(conexion, paciente_id)
    registrar_evento(usuario['id'], 'consulta_historial', paciente_id)
    return resultado


# Agrega una especialidad y devuelve su id sin mantener nombres fijos en condiciones.
def agregar_especialidad(usuario, nombre):
    exigir_rol(usuario, ('administracion',))
    with DATOS.transaccion() as conexion:
        return DATOS.guardar_especialidad(conexion, texto(nombre, 'Especialidad', 100))


# Asocia una cuenta de doctor a una especialidad existente y devuelve su id,
# permitiendo extender la agenda mediante registros y no mediante cambios del código.
def registrar_doctor(usuario, usuario_id, especialidad_id):
    exigir_rol(usuario, ('administracion',))
    entero(usuario_id)
    entero(especialidad_id)
    with DATOS.transaccion() as conexion:
        cuenta = DATOS.perfil(conexion, usuario_id)
        if not cuenta or cuenta['rol'] != 'doctor':
            raise DatosInvalidos('Seleccione una cuenta con rol doctor')
        return DATOS.guardar_doctor(conexion, usuario_id, especialidad_id)


# Devuelve la agenda del personal y limita a cada doctor a sus propias citas.
def listar_citas(usuario):
    exigir_rol(usuario, ('administracion', 'recepcion', 'doctor'))
    with DATOS.transaccion() as conexion:
        return DATOS.agenda(conexion, usuario)


# Devuelve números e importes de facturas sin permitir que recepción lea observaciones.
def listar_facturas(usuario):
    exigir_rol(usuario, ('administracion', 'recepcion'))
    with DATOS.transaccion() as conexion:
        return DATOS.facturas(conexion)
