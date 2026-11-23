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
