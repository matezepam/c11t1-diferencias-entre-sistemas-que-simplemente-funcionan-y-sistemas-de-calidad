# EJERCICIO 1 SOLUCION BASICA
# Esta versión agrupa registros y operaciones para mostrar una alternativa que
# acepta datos sin verificar, usando únicamente personas ficticias en la demostración.

pacientes = []
citas = []
historiales = []
facturas = []


# Registra identificación y antecedentes juntos y devuelve la posición, dejando
# visibles las limitaciones de aceptar documentos repetidos y fechas como texto.
def registrar_paciente(nombre, documento, antecedentes):
    pacientes.append([nombre, documento, antecedentes])
    return len(pacientes) - 1


# Agenda, escribe una observación y factura dentro de una sola función para
# contrastar responsabilidades mezcladas y ausencia de una transacción ante fallos.
def gestionar_cita(paciente, doctor, horario, observacion, importe):
    citas.append([paciente, doctor, horario])
    historiales.append([paciente, observacion])
    facturas.append([paciente, importe])
    return len(citas) - 1


# Muestra dos reservas del mismo doctor y horario para evidenciar que el flujo
# termina aunque el resultado incumpla una regla importante de la agenda.
def demostracion():
    paciente = registrar_paciente('Paciente de ejemplo', 'DEMO001', 'Sin antecedentes declarados')
    gestionar_cita(paciente, 'Doctor de ejemplo', '10:00', 'Control de ejemplo', 25)
    gestionar_cita(paciente, 'Doctor de ejemplo', '10:00', 'Segunda reserva de ejemplo', 25)
    print('CLINICA BASICA')
    print('Pacientes', pacientes)
    print('Citas', citas)
    print('Historiales', historiales)
    print('Facturas', facturas)
    print('Se aceptaron dos citas en el mismo horario porque esta versión no lo comprueba')


if __name__ == '__main__':
    demostracion()
