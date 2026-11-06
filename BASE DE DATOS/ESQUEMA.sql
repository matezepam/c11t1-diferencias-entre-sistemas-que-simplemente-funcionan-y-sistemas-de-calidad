-- El esquema agrupa las tablas de las dos soluciones de calidad.
CREATE SCHEMA IF NOT EXISTS c11_clase;
SET search_path TO c11_clase;

CREATE TABLE IF NOT EXISTS usuarios (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 nombre text NOT NULL,
 correo text NOT NULL UNIQUE,
 sal text NOT NULL,
 clave text NOT NULL,
 rol text NOT NULL CHECK(rol IN ('administracion','recepcion','doctor','cliente'))
);
CREATE TABLE IF NOT EXISTS especialidades (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 nombre text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS doctores (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 usuario_id bigint NOT NULL UNIQUE REFERENCES usuarios,
 especialidad_id bigint NOT NULL REFERENCES especialidades
);
CREATE TABLE IF NOT EXISTS pacientes (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 documento text NOT NULL UNIQUE,
 nombre text NOT NULL,
 nacimiento date NOT NULL,
 telefono text NOT NULL,
 antecedentes text NOT NULL
);
CREATE TABLE IF NOT EXISTS citas (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 paciente_id bigint NOT NULL REFERENCES pacientes,
 doctor_id bigint NOT NULL REFERENCES doctores,
 inicio timestamptz NOT NULL,
 fin timestamptz NOT NULL CHECK(fin>inicio),
 atendida boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS agenda_doctor ON citas(doctor_id,inicio,fin);
CREATE INDEX IF NOT EXISTS agenda_paciente ON citas(paciente_id,inicio,fin);
CREATE TABLE IF NOT EXISTS atenciones (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 cita_id bigint NOT NULL UNIQUE REFERENCES citas,
 observacion text NOT NULL,
 importe numeric(12,2) NOT NULL CHECK(importe>0),
 fecha timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS productos (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 nombre text NOT NULL,
 categoria text NOT NULL,
 precio numeric(12,2) NOT NULL CHECK(precio>0),
 stock integer NOT NULL CHECK(stock>=0)
);
CREATE TABLE IF NOT EXISTS carrito (
 usuario_id bigint NOT NULL REFERENCES usuarios,
 producto_id bigint NOT NULL REFERENCES productos,
 cantidad integer NOT NULL CHECK(cantidad>0),
 PRIMARY KEY(usuario_id,producto_id)
);
CREATE TABLE IF NOT EXISTS pedidos (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 usuario_id bigint NOT NULL REFERENCES usuarios,
 clave text NOT NULL UNIQUE,
 total numeric(12,2) NOT NULL CHECK(total>0),
 estado text NOT NULL CHECK(estado IN ('pendiente','pagado','cancelado','reembolso_pendiente','enviado','entregado'))
);
CREATE TABLE IF NOT EXISTS detalles (
 pedido_id bigint NOT NULL REFERENCES pedidos,
 producto_id bigint NOT NULL REFERENCES productos,
 cantidad integer NOT NULL CHECK(cantidad>0),
 precio numeric(12,2) NOT NULL CHECK(precio>0),
 PRIMARY KEY(pedido_id,producto_id)
);
