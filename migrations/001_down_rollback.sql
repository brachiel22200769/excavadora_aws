USE vehiculo_iot;

ALTER TABLE demos
    DROP FOREIGN KEY fk_demo_creador,
    DROP COLUMN id_usuario_creador,
    DROP COLUMN tipo_demo;

ALTER TABLE vehiculos
    DROP FOREIGN KEY fk_vehiculo_propietario,
    DROP FOREIGN KEY fk_vehiculo_modelo,
    DROP INDEX idx_vehiculo_estado,
    DROP INDEX idx_vehiculo_propietario,
    DROP INDEX uq_vehiculo_serie,
    DROP COLUMN id_propietario,
    DROP COLUMN estado_comercial,
    DROP COLUMN numero_serie,
    DROP COLUMN id_modelo;

DROP TABLE IF EXISTS bitacora_auditoria;
DROP TABLE IF EXISTS sesiones_invitado;
DROP TABLE IF EXISTS modelos_comerciales;
DROP TABLE IF EXISTS usuarios;