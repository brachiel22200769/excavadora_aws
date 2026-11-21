USE vehiculo_iot;

-- 1. TABLA DE USUARIOS
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    correo VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    rol ENUM('ADMIN', 'USUARIO') NOT NULL DEFAULT 'USUARIO',
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_usuario_username UNIQUE (username),
    CONSTRAINT uq_usuario_correo UNIQUE (correo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 2. TABLA DE MODELOS COMERCIALES
CREATE TABLE IF NOT EXISTS modelos_comerciales (
    id_modelo INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    descripcion VARCHAR(255) NULL,
    especificaciones VARCHAR(255) NULL,
    microcontrolador_base VARCHAR(50) NOT NULL DEFAULT 'ESP8266',
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_modelo_nombre UNIQUE (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 3. TABLA DE SESIONES TEMPORALES DE INVITADO (5 min)
CREATE TABLE IF NOT EXISTS sesiones_invitado (
    id_sesion BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_vehiculo INT NOT NULL,
    token_jti VARCHAR(64) NOT NULL,
    ip_origen VARCHAR(45) NULL,
    inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_en TIMESTAMP NOT NULL,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    motivo_cierre VARCHAR(40) NULL,
    CONSTRAINT uq_sesion_jti UNIQUE (token_jti),
    INDEX idx_sesion_vehiculo_activa (id_vehiculo, activa, expira_en),
    CONSTRAINT fk_sesion_vehiculo
        FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 4. TABLA DE BITÁCORA DE AUDITORÍA
CREATE TABLE IF NOT EXISTS bitacora_auditoria (
    id_auditoria BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NULL,
    username_actor VARCHAR(50) NOT NULL DEFAULT 'SISTEMA',
    correo_actor VARCHAR(120) NULL,
    accion VARCHAR(60) NOT NULL,
    entidad VARCHAR(40) NOT NULL,
    id_entidad INT NULL,
    detalles VARCHAR(500) NULL,
    fecha_hora TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_auditoria_fecha (fecha_hora DESC),
    INDEX idx_auditoria_accion (accion),
    CONSTRAINT fk_auditoria_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 5. AMPLIACIÓN DE vehiculos (sin borrar ni alterar IDs)
ALTER TABLE vehiculos
    ADD COLUMN id_modelo INT NULL AFTER modelo,
    ADD COLUMN numero_serie VARCHAR(60) NULL AFTER id_modelo,
    ADD COLUMN estado_comercial ENUM('DISPONIBLE', 'VENDIDO', 'EXHIBICION', 'MANTENIMIENTO')
        NOT NULL DEFAULT 'DISPONIBLE' AFTER activo,
    ADD COLUMN id_propietario INT NULL AFTER estado_comercial,
    ADD CONSTRAINT uq_vehiculo_serie UNIQUE (numero_serie),
    ADD INDEX idx_vehiculo_propietario (id_propietario),
    ADD INDEX idx_vehiculo_estado (estado_comercial),
    ADD CONSTRAINT fk_vehiculo_modelo
        FOREIGN KEY (id_modelo) REFERENCES modelos_comerciales(id_modelo)
        ON DELETE SET NULL ON UPDATE CASCADE,
    ADD CONSTRAINT fk_vehiculo_propietario
        FOREIGN KEY (id_propietario) REFERENCES usuarios(id_usuario)
        ON DELETE SET NULL ON UPDATE CASCADE;

-- 6. AMPLIACIÓN DE demos (Empresa vs Privada)
ALTER TABLE demos
    ADD COLUMN tipo_demo ENUM('EMPRESA', 'PRIVADA') NOT NULL DEFAULT 'EMPRESA' AFTER descripcion,
    ADD COLUMN id_usuario_creador INT NULL AFTER tipo_demo,
    ADD CONSTRAINT fk_demo_creador
        FOREIGN KEY (id_usuario_creador) REFERENCES usuarios(id_usuario)
        ON DELETE SET NULL ON UPDATE CASCADE;

-- 7. MODELO BASE Y DATOS PARA TUS VEHÍCULOS ACTUALES
INSERT IGNORE INTO modelos_comerciales (nombre, descripcion, especificaciones, microcontrolador_base)
VALUES (
    'Excavadora IoT Pro Series',
    'Modelo comercial estándar con tracción de orugas y brazo articulado',
    'ESP8266, 74HC595, 13 Canales, Optoacopladores',
    'ESP8266'
);

UPDATE vehiculos
SET
    id_modelo = COALESCE(
        id_modelo,
        (SELECT id_modelo FROM modelos_comerciales WHERE nombre = 'Excavadora IoT Pro Series' LIMIT 1)
    ),
    numero_serie = COALESCE(numero_serie, CONCAT('EXC-IOT-2026-', LPAD(id_vehiculo, 3, '0')))
WHERE id_vehiculo > 0;


USE vehiculo_iot;
SHOW TABLES;

SELECT id_vehiculo, nombre, numero_serie, estado_comercial FROM vehiculos;