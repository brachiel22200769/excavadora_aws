# 🚜 Excavadora IoT - Backend API REST & WebSockets (v3.0)

Backend del sistema de teleoperación IoT para vehículos controlados por **ESP8266** y registros de desplazamiento **74HC595**. Desarrollado en **Python (FastAPI)** con persistencia en **Amazon RDS (MySQL)**, autenticación **JWT + bcrypt**, control de acceso basado en roles (**RBAC**) y canales **WebSocket aislados por vehículo**.

---

## 📚 Documentación Interactiva (Swagger UI)

Todos los endpoints REST (incluidos los **21 Stored Procedures** originales y los módulos de Autenticación y Administración) están documentados y listos para pruebas en:

👉 `https://mutual-spearhead-factoid.ngrok-free.dev/docs`

---

## 🔐 Arquitectura de Seguridad y Roles (RBAC)

El sistema implementa tres niveles de acceso con validación estricta de propiedad (**anti-BOLA**) en cada endpoint y canal WebSocket:

* **ADMIN:** Gestiona el inventario de unidades, catálogo de modelos comerciales, asignación de propietarios, estados comerciales (`DISPONIBLE`, `VENDIDO`, `EXHIBICION`, `MANTENIMIENTO`) y consulta la bitácora de auditoría. Opera únicamente por API REST.
* **USUARIO:** Puede registrarse públicamente y operar en tiempo real únicamente los vehículos asignados a su cuenta, consultar su historial y crear, editar o eliminar sus propias secuencias (**Demos**).
* **INVITADO:** Obtiene una reserva temporal exclusiva de **5 minutos** sobre la unidad en estado `EXHIBICION`. Al cerrar sesión, desconectarse del WebSocket o expirar el temporizador, el backend envía automáticamente un paro de seguridad (`status: 13`) y revoca la sesión.

---

## ⚙️ Automatizaciones de Base de Datos

* **Clonación de 13 comandos base (`clonar_comandos_base`):** Cada unidad nueva o puesta en exhibición recibe automáticamente el mapa estándar de comandos (`1` al `13`) y su estado inicial en `DETENIDO (13)`.
* **Demo de Fábrica automática (`asegurar_demo_default`):** Al arrancar el servidor (`startup`), al registrar una unidad nueva o al iniciar el modo invitado, el backend verifica que cada vehículo cuente al menos con la secuencia predeterminada **`Demo de Fábrica`** lista para ejecutarse.
* **Bitácora de Auditoría:** Registra inicios/cierres de sesión, reservas de invitado, cambios de inventario, modelos, propietarios y gestión de demos.

---

## 🔌 Documentación de WebSockets (WSS)

Los canales en tiempo real están aislados por `id_vehiculo` y protegidos contra conexiones no autorizadas (cierre con código `4003` si falla la validación):

### 1. Canal para Clientes Web (Navegador)
```text
wss://mutual-spearhead-factoid.ngrok-free.dev/ws/vehiculos/{id_vehiculo}?token=<JWT>
```
Al conectar, el servidor responde inmediatamente con el estado actual guardado en RDS y la disponibilidad del hardware físico:
```json
{
  "type": "ESTADO_INICIAL",
  "vehiculo": 1,
  "status": 13,
  "esp_conectado": true
}
```

### 2. Canal Dedicado para Hardware (ESP8266)
```text
wss://mutual-spearhead-factoid.ngrok-free.dev/ws/device/{id_vehiculo}?key=<DEVICE_WS_KEY>
```
Al conectar, el servidor envía `{"status": 13}` para garantizar que la excavadora inicie detenida.

### 3. Estructura de Eventos JSON

**Movimiento Manual** (emitido tras `POST /api/vehiculos/{id}/movimiento`; persiste en `estado_vehiculo` e `historial_movimientos`):
```json
{
  "vehiculo": 1,
  "status": 2,
  "id_comando": 2,
  "comando_nombre": "AVANZANDO",
  "origen": "WEB_UI",
  "type": "MOVIMIENTO_MANUAL"
}
```

**Ejecución de DEMO en tiempo real** (emitido tras `POST /api/vehiculos/{id}/demo/{id_demo}/iniciar`; actualiza el estado en vivo sin saturar el historial):
```json
{ "type": "DEMO_INICIO", "vehiculo": 1, "id_demo": 1 }
{ "type": "DEMO_PASO", "vehiculo": 1, "status": 10, "comando_nombre": "GARRA ARRIBA", "duracion": 1200 }
{ "type": "DEMO_PAUSA", "vehiculo": 1, "status": 13, "comando_nombre": "DETENIDO", "pausa": 300 }
{ "type": "DEMO_FIN", "vehiculo": 1, "status": 13, "comando_nombre": "DETENIDO" }
```

**Revocación de Sesión** (al reasignar dueño, cambiar estado comercial o expirar el modo invitado):
```json
{
  "type": "SESION_REVOCADA",
  "motivo": "Sesión invitado finalizada (EXPIRADA)"
}
```

---

## 🗂️ Estructura del Repositorio

```text
websocket_iot/
├── app/
│   ├── main.py                      # Endpoints REST, RBAC, motor de demos y WebSockets
│   ├── models/
│   │   └── schemas.py               # Validaciones Pydantic (Auth, Admin, Vehículos, Demos)
│   ├── services/
│   │   ├── auth_service.py          # JWT, bcrypt, dependencias RBAC y validación anti-BOLA
│   │   └── db_service.py            # Conexión RDS, 21 SPs, comandos base, demo default y auditoría
│   └── websocket/
│       └── websocket_manager.py     # Salas WebSocket aisladas por id_vehiculo (web y ESP8266)
├── migrations/
│   ├── 001_up_admin_rbac.sql        # Migración de tablas RBAC, modelos, auditoría e invitados
│   └── 001_down_rollback.sql        # Reversión segura de la migración
├── seed_inicial.py                  # Carga inicial de usuarios base (admin/usuario) y datos semilla
├── requirements.txt                 # Dependencias Python
└── .env                             # Variables de entorno (RDS, JWT_SECRET, DEVICE_WS_KEY)
```

---

## 🚀 Despliegue y Ejecución (AWS EC2 + RDS + Ngrok)

1. **Instalar dependencias en el entorno virtual:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Configurar `.env`** con las credenciales de Amazon RDS (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`), `JWT_SECRET` y `DEVICE_WS_KEY`.
3. **Aplicar migración y datos semilla (solo primera vez):**
   Ejecutar `migrations/001_up_admin_rbac.sql` en RDS y correr:
   ```powershell
   python seed_inicial.py
   ```
4. **Levantar el servidor FastAPI en EC2 (Windows Server 2025):**
   ```powershell
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
5. **Exponer HTTPS y WSS mediante Ngrok:**
   ```powershell
   ngrok http 8000
   ```

---

Desarrollado por **Erick Brachiel Silva Barriga** — Ingeniería en Sistemas Computacionales, Instituto Tecnológico de Pachuca (2026).
