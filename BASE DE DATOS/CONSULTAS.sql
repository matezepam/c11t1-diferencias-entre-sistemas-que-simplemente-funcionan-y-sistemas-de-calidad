-- Consultas de lectura sin contraseñas ni observaciones médicas.
SET search_path TO c11_clase;
SELECT id,nombre,correo,rol FROM usuarios ORDER BY id;
SELECT id,nombre FROM especialidades ORDER BY id;
SELECT id,documento,nombre FROM pacientes ORDER BY id;
SELECT id,paciente_id,doctor_id,inicio,fin,atendida FROM citas ORDER BY inicio;
SELECT id,cita_id,importe,fecha FROM atenciones ORDER BY id;
SELECT id,nombre,categoria,precio,stock FROM productos ORDER BY id;
SELECT id,usuario_id,total,estado FROM pedidos ORDER BY id;
