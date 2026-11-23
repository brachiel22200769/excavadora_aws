import os
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from mysql.connector import Error as MySQLError

from app.models.schemas import (
    VehiculoRequest, ComandoRequest, DemoRequest, DemoMovimientoRequest, MovimientoRequest,
    LoginRequest, RegisterRequest, ModeloComercialRequest,
    UnidadAdminCreateRequest, UnidadAdminUpdateRequest,
    AsignarPropietarioRequest, CambiarEstadoRequest,
)
from app.services.db_service import DBService
from app.services.auth_service import (
    hash_password, verify_password, crear_token_usuario, crear_token_invitado,
    decodificar_y_validar_token, get_current_actor, require_admin,
    validar_acceso_vehiculo, DEVICE_WS_KEY, GUEST_DURATION_MINUTES,
)
from app.websocket.websocket_manager import WebSocketManager

app = FastAPI(title="API Excavadora IoT (RBAC + Admin + 21 SPs)", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://brachiel22200769.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "*",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

db = DBService()
ws_manager = WebSocketManager()
active_demos: dict[int, dict] = {}
active_guest_timers: dict[str, asyncio.Task] = {}
@app.on_event("startup")
def inicializar_demos_default():
    try:
        db.asegurar_demos_vehiculos_existentes()
    except Exception as e:
        print(f"[WARN] No se pudieron verificar demos default al iniciar: {e}")

# ==========================================
# UTILIDADES INTERNAS
# ==========================================
def resolver_comando_vehiculo(id_vehiculo: int, identificador: int) -> dict | None:
    """Busca por id_comando exacto y, si no coincide, por codigo (1..13) del vehículo."""
    comandos = db.llamar_sp_lectura("sp_obtener_comandos_vehiculo", [id_vehiculo])
    cmd = next((c for c in comandos if c["id_comando"] == identificador and c["activo"]), None)
    if not cmd:
        cmd = next((c for c in comandos if c["codigo"] == identificador and c["activo"]), None)
    return cmd

def obtener_id_comando_stop(id_vehiculo: int) -> int | None:
    cmd = resolver_comando_vehiculo(id_vehiculo, 13)
    return cmd["id_comando"] if cmd else None

def obtener_vehiculo_de_demo(id_demo: int) -> dict:
    rows = db.ejecutar_consulta("SELECT * FROM demos WHERE id_demo = %s LIMIT 1", (id_demo,))
    if not rows:
        raise HTTPException(404, "Demo no encontrada.")
    return rows[0]

async def detener_vehiculo_seguro(id_vehiculo: int):
    if id_vehiculo in active_demos and not active_demos[id_vehiculo]["task"].done():
        active_demos[id_vehiculo]["cancel_event"].set()
    id_stop = obtener_id_comando_stop(id_vehiculo)
    if id_stop:
        db.actualizar_estado_solo(id_vehiculo, id_stop, ws_manager.dispositivo_conectado(id_vehiculo))
    await ws_manager.enviar_a_vehiculo(id_vehiculo, {
        "vehiculo": id_vehiculo,
        "status": 13,
        "comando_nombre": "DETENIDO",
    })

async def cerrar_sesion_invitado(jti: str, id_vehiculo: int, motivo: str):
    db.ejecutar_escritura(
        "UPDATE sesiones_invitado SET activa = FALSE, motivo_cierre = %s "
        "WHERE token_jti = %s AND activa = TRUE",
        (motivo, jti),
    )
    await detener_vehiculo_seguro(id_vehiculo)
    await ws_manager.revocar_web_vehiculo(id_vehiculo, motivo=f"Sesión invitado finalizada ({motivo})", solo_jti=jti)
    db.registrar_auditoria("CIERRE_INVITADO", "sesiones_invitado", id_vehiculo, f"Sesión cerrada ({motivo}) en unidad ID {id_vehiculo}")
    task = active_guest_timers.pop(jti, None)
    if task and task is not asyncio.current_task() and not task.done():
        task.cancel()

async def temporizador_invitado(jti: str, id_vehiculo: int, segundos: float):
    try:
        await asyncio.sleep(max(1.0, segundos))
        await cerrar_sesion_invitado(jti, id_vehiculo, "EXPIRADA")
    except asyncio.CancelledError:
        pass

# ==========================================
# INTERFAZ WEB Y DIAGNÓSTICO DE SALUD
# ==========================================
@app.get("/control", response_class=HTMLResponse, tags=["0. Salud e Interfaz"])
def panel_control():
    html_path = os.path.join(BASE_DIR, "index.html")
    if not os.path.isfile(html_path):
        return HTMLResponse("<h1>Error: No se encontró index.html</h1>", status_code=404)
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/Fondo.jpg", include_in_schema=False)
def obtener_fondo():
    return FileResponse(os.path.join(BASE_DIR, "Fondo.jpg"))

@app.get("/api/health", tags=["0. Salud e Interfaz"])
def health_check():
    """Diagnóstico independiente de API y RDS (público, sin exponer secretos)."""
    rds_ok = db.ping_rds()
    return {
        "api": "OK",
        "rds": "OK" if rds_ok else "SIN VERIFICAR",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# ==========================================
# AUTENTICACIÓN, REGISTRO E INVITADO
# ==========================================
@app.post("/api/auth/register", status_code=201, tags=["Auth"])
def registrar_usuario(req: RegisterRequest):
    """Registro público: SIEMPRE crea rol USUARIO. Nadie puede registrarse como ADMIN."""
    username = req.username.strip().lower()
    correo = req.correo.strip().lower()
    existe = db.ejecutar_consulta(
        "SELECT id_usuario FROM usuarios WHERE username = %s OR correo = %s LIMIT 1",
        (username, correo),
    )
    if existe:
        raise HTTPException(409, "El nombre de usuario o correo ya está registrado.")

    pwd_hash = hash_password(req.password)
    res = db.ejecutar_escritura(
        "INSERT INTO usuarios (username, nombre, correo, password_hash, rol, activo) "
        "VALUES (%s, %s, %s, %s, 'USUARIO', TRUE)",
        (username, req.nombre.strip(), correo, pwd_hash),
    )
    nuevo_id = res["last_id"]
    db.registrar_auditoria(
        "REGISTRO_USUARIO", "usuarios", nuevo_id,
        f"Nuevo comprador registrado: {username} ({correo})",
        {"id_usuario": nuevo_id, "username": username, "correo": correo, "rol": "USUARIO"},
    )
    return {"mensaje": "Usuario registrado correctamente", "id_usuario": nuevo_id, "username": username, "rol": "USUARIO"}

@app.post("/api/auth/login", tags=["Auth"])
def login(req: LoginRequest):
    """Inicio de sesión con username y password."""
    username = req.username.strip().lower()
    rows = db.ejecutar_consulta(
        "SELECT id_usuario, username, nombre, correo, password_hash, rol, activo "
        "FROM usuarios WHERE username = %s LIMIT 1",
        (username,),
    )
    if not rows or not verify_password(req.password, rows[0]["password_hash"]):
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    user = rows[0]
    if not user["activo"]:
        raise HTTPException(403, "Cuenta desactivada por el administrador.")

    token, exp = crear_token_usuario(user)
    db.registrar_auditoria(
        "LOGIN", "usuarios", user["id_usuario"],
        f"Inicio de sesión exitoso para {user['username']} ({user['correo']})",
        user,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expira_en": exp.isoformat(),
        "usuario": {
            "id_usuario": user["id_usuario"],
            "username": user["username"],
            "nombre": user["nombre"],
            "correo": user["correo"],
            "rol": user["rol"],
        },
    }

@app.post("/api/auth/guest", tags=["Auth"])
async def iniciar_modo_invitado(request: Request):
    """Reserva exclusiva de 5 minutos para la unidad en estado EXHIBICION."""
    # Expirar sesiones vencidas antes de revisar disponibilidad
    db.ejecutar_escritura(
        "UPDATE sesiones_invitado SET activa = FALSE, motivo_cierre = 'EXPIRADA' "
        "WHERE activa = TRUE AND expira_en <= UTC_TIMESTAMP()"
    )

    exhibicion = db.ejecutar_consulta(
        "SELECT id_vehiculo, nombre, numero_serie, modelo FROM vehiculos "
        "WHERE estado_comercial = 'EXHIBICION' AND activo = TRUE ORDER BY id_vehiculo ASC LIMIT 1"
    )
    if not exhibicion:
        raise HTTPException(404, "No hay ningún vehículo configurado en modo EXHIBICION actualmente.")
    unidad = exhibicion[0]
    id_v = unidad["id_vehiculo"]

    ocupada = db.ejecutar_consulta(
        "SELECT id_sesion, expira_en FROM sesiones_invitado "
        "WHERE id_vehiculo = %s AND activa = TRUE AND expira_en > UTC_TIMESTAMP() LIMIT 1",
        (id_v,),
    )
    if ocupada:
        raise HTTPException(
            409,
            "La unidad de exhibición está siendo probada por otro invitado. Intenta en unos minutos.",
        )

    db.clonar_comandos_base(id_v)
    db.asegurar_demo_default(id_v)
    token, jti, exp = crear_token_invitado(id_v)
    ip_origen = request.client.host if request.client else None

    db.ejecutar_escritura(
        "INSERT INTO sesiones_invitado (id_vehiculo, token_jti, ip_origen, inicio, expira_en, activa) "
        "VALUES (%s, %s, %s, UTC_TIMESTAMP(), %s, TRUE)",
        (id_v, jti, ip_origen, exp.strftime("%Y-%m-%d %H:%M:%S")),
    )
    db.registrar_auditoria(
        "INICIO_INVITADO", "sesiones_invitado", id_v,
        f"Invitado reservó unidad '{unidad['nombre']}' (ID {id_v}) por {GUEST_DURATION_MINUTES} minutos",
    )

    segundos = GUEST_DURATION_MINUTES * 60
    active_guest_timers[jti] = asyncio.create_task(temporizador_invitado(jti, id_v, segundos))

    return {
        "access_token": token,
        "token_type": "bearer",
        "expira_en": exp.isoformat(),
        "duracion_segundos": segundos,
        "usuario": {
            "id_usuario": None,
            "username": "invitado",
            "nombre": "Modo Invitado",
            "correo": "invitado@exhibicion",
            "rol": "INVITADO",
            "id_vehiculo": id_v,
        },
        "vehiculo": unidad,
    }

@app.get("/api/auth/me", tags=["Auth"])
def obtener_perfil(actor: dict = Depends(get_current_actor)):
    return actor

@app.post("/api/auth/logout", tags=["Auth"])
async def logout(actor: dict = Depends(get_current_actor)):
    if actor.get("rol") == "INVITADO":
        await cerrar_sesion_invitado(actor["jti"], actor["id_vehiculo"], "LOGOUT")
    else:
        db.registrar_auditoria("LOGOUT", "usuarios", actor["id_usuario"], f"Cierre de sesión de {actor['username']}", actor)
    return {"mensaje": "Sesión cerrada correctamente"}

# ==========================================
# CATÁLOGO PÚBLICO Y "MIS VEHÍCULOS"
# ==========================================
@app.get("/api/catalogo/modelos", tags=["Catálogo"])
def catalogo_publico_modelos():
    return db.ejecutar_consulta(
        "SELECT id_modelo, nombre, descripcion, especificaciones, microcontrolador_base "
        "FROM modelos_comerciales WHERE activo = TRUE ORDER BY id_modelo"
    )

@app.get("/api/vehiculos/mios", tags=["1. Vehículos"])
def obtener_mis_vehiculos(actor: dict = Depends(get_current_actor)):
    rol = actor.get("rol")
    if rol == "ADMIN":
        return db.ejecutar_consulta(
            "SELECT v.*, m.nombre AS modelo_comercial, u.username AS propietario_username, u.nombre AS propietario_nombre "
            "FROM vehiculos v "
            "LEFT JOIN modelos_comerciales m ON m.id_modelo = v.id_modelo "
            "LEFT JOIN usuarios u ON u.id_usuario = v.id_propietario "
            "ORDER BY v.id_vehiculo"
        )
    if rol == "USUARIO":
        return db.ejecutar_consulta(
            "SELECT v.*, m.nombre AS modelo_comercial "
            "FROM vehiculos v LEFT JOIN modelos_comerciales m ON m.id_modelo = v.id_modelo "
            "WHERE v.id_propietario = %s AND v.activo = TRUE ORDER BY v.id_vehiculo",
            (actor["id_usuario"],),
        )
    if rol == "INVITADO":
        return db.ejecutar_consulta(
            "SELECT v.*, m.nombre AS modelo_comercial "
            "FROM vehiculos v LEFT JOIN modelos_comerciales m ON m.id_modelo = v.id_modelo "
            "WHERE v.id_vehiculo = %s AND v.estado_comercial = 'EXHIBICION' AND v.activo = TRUE",
            (actor["id_vehiculo"],),
        )
    return []

# ==========================================
# 1. VEHÍCULOS (5 SPs originales + RBAC)
# ==========================================
@app.post("/api/vehiculos", status_code=201, tags=["1. Vehículos"])
def crear_vehiculo(req: VehiculoRequest, admin: dict = Depends(require_admin)):
    res = db.llamar_sp_escritura("sp_crear_vehiculo", [req.nombre, req.modelo, req.descripcion, req.microcontrolador])
    nuevo_id = res.get("id_vehiculo") if isinstance(res, dict) else None
    if nuevo_id:
        db.clonar_comandos_base(nuevo_id)
        db.asegurar_demo_default(nuevo_id)
        db.registrar_auditoria("CREAR_VEHICULO", "vehiculos", nuevo_id, f"Creó vehículo '{req.nombre}'", admin)
    return {"mensaje": "Vehículo creado", "id_vehiculo": nuevo_id}

@app.get("/api/vehiculos", tags=["1. Vehículos"])
def obtener_vehiculos(admin: dict = Depends(require_admin)):
    return db.llamar_sp_lectura("sp_obtener_vehiculos")

@app.get("/api/vehiculos/{id_vehiculo}", tags=["1. Vehículos"])
def obtener_vehiculo(id_vehiculo: int, actor: dict = Depends(get_current_actor)):
    validar_acceso_vehiculo(db, actor, id_vehiculo, modo="lectura")
    res = db.llamar_sp_lectura("sp_obtener_vehiculo", [id_vehiculo])
    if not res:
        raise HTTPException(404, "Vehículo no encontrado")
    return res[0]

@app.put("/api/vehiculos/{id_vehiculo}", tags=["1. Vehículos"])
def actualizar_vehiculo(id_vehiculo: int, req: VehiculoRequest, admin: dict = Depends(require_admin)):
    db.llamar_sp_escritura("sp_actualizar_vehiculo", [id_vehiculo, req.nombre, req.modelo, req.descripcion, req.microcontrolador, req.activo])
    db.registrar_auditoria("ACTUALIZAR_VEHICULO", "vehiculos", id_vehiculo, f"Actualizó unidad ID {id_vehiculo} ({req.nombre})", admin)
    return {"mensaje": "Vehículo actualizado"}

@app.delete("/api/vehiculos/{id_vehiculo}", tags=["1. Vehículos"])
def eliminar_vehiculo(id_vehiculo: int, admin: dict = Depends(require_admin)):
    db.llamar_sp_escritura("sp_eliminar_vehiculo", [id_vehiculo])
    db.registrar_auditoria("ELIMINAR_VEHICULO", "vehiculos", id_vehiculo, f"Eliminó unidad ID {id_vehiculo}", admin)
    return {"mensaje": "Vehículo eliminado"}

# ==========================================
# PANEL ADMINISTRADOR (Inventario, Modelos, Dueños, Auditoría)
# ==========================================
@app.get("/api/admin/dashboard", tags=["Admin"])
def admin_dashboard(admin: dict = Depends(require_admin)):
    totales = db.ejecutar_consulta(
        "SELECT "
        "(SELECT COUNT(*) FROM vehiculos) AS total_unidades, "
        "(SELECT COUNT(*) FROM vehiculos WHERE estado_comercial = 'VENDIDO') AS vendidas, "
        "(SELECT COUNT(*) FROM vehiculos WHERE estado_comercial = 'EXHIBICION') AS exhibicion, "
        "(SELECT COUNT(*) FROM vehiculos WHERE estado_comercial = 'DISPONIBLE') AS disponibles, "
        "(SELECT COUNT(*) FROM modelos_comerciales WHERE activo = TRUE) AS total_modelos, "
        "(SELECT COUNT(*) FROM usuarios WHERE rol = 'USUARIO') AS total_clientes, "
        "(SELECT COUNT(*) FROM sesiones_invitado WHERE activa = TRUE AND expira_en > UTC_TIMESTAMP()) AS invitados_activos"
    )
    return totales[0]

@app.get("/api/admin/usuarios", tags=["Admin"])
def listar_usuarios(admin: dict = Depends(require_admin)):
    return db.ejecutar_consulta(
        "SELECT id_usuario, username, nombre, correo, rol, activo, fecha_creacion "
        "FROM usuarios ORDER BY rol, id_usuario"
    )

@app.get("/api/admin/modelos", tags=["Admin"])
def listar_modelos(admin: dict = Depends(require_admin)):
    return db.ejecutar_consulta("SELECT * FROM modelos_comerciales ORDER BY id_modelo")

@app.post("/api/admin/modelos", status_code=201, tags=["Admin"])
def crear_modelo(req: ModeloComercialRequest, admin: dict = Depends(require_admin)):
    try:
        res = db.ejecutar_escritura(
            "INSERT INTO modelos_comerciales (nombre, descripcion, especificaciones, microcontrolador_base, activo) "
            "VALUES (%s, %s, %s, %s, %s)",
            (req.nombre.strip(), req.descripcion, req.especificaciones, req.microcontrolador_base, req.activo),
        )
    except MySQLError:
        raise HTTPException(409, "Ya existe un modelo comercial con ese nombre.")
    db.registrar_auditoria("CREAR_MODELO", "modelos_comerciales", res["last_id"], f"Creó modelo '{req.nombre}'", admin)
    return {"mensaje": "Modelo comercial creado", "id_modelo": res["last_id"]}

@app.put("/api/admin/modelos/{id_modelo}", tags=["Admin"])
def actualizar_modelo(id_modelo: int, req: ModeloComercialRequest, admin: dict = Depends(require_admin)):
    try:
        res = db.ejecutar_escritura(
            "UPDATE modelos_comerciales SET nombre=%s, descripcion=%s, especificaciones=%s, "
            "microcontrolador_base=%s, activo=%s WHERE id_modelo=%s",
            (req.nombre.strip(), req.descripcion, req.especificaciones, req.microcontrolador_base, req.activo, id_modelo),
        )
    except MySQLError:
        raise HTTPException(409, "Nombre de modelo duplicado.")
    if res["affected"] == 0:
        raise HTTPException(404, "Modelo no encontrado.")
    db.registrar_auditoria("EDITAR_MODELO", "modelos_comerciales", id_modelo, f"Actualizó modelo ID {id_modelo} ('{req.nombre}')", admin)
    return {"mensaje": "Modelo actualizado"}

@app.get("/api/admin/vehiculos", tags=["Admin"])
def listar_inventario_admin(admin: dict = Depends(require_admin)):
    return db.ejecutar_consulta(
        "SELECT v.*, m.nombre AS modelo_comercial, u.username AS propietario_username, "
        "u.nombre AS propietario_nombre, u.correo AS propietario_correo "
        "FROM vehiculos v "
        "LEFT JOIN modelos_comerciales m ON m.id_modelo = v.id_modelo "
        "LEFT JOIN usuarios u ON u.id_usuario = v.id_propietario "
        "ORDER BY v.id_vehiculo"
    )

@app.post("/api/admin/vehiculos", status_code=201, tags=["Admin"])
def registrar_unidad_admin(req: UnidadAdminCreateRequest, admin: dict = Depends(require_admin)):
    modelos = db.ejecutar_consulta("SELECT nombre FROM modelos_comerciales WHERE id_modelo = %s", (req.id_modelo,))
    if not modelos:
        raise HTTPException(404, "Modelo comercial no encontrado.")
    if req.id_propietario is not None:
        u = db.ejecutar_consulta("SELECT id_usuario FROM usuarios WHERE id_usuario = %s", (req.id_propietario,))
        if not u:
            raise HTTPException(404, "Propietario no encontrado.")
    try:
        res = db.ejecutar_escritura(
            "INSERT INTO vehiculos (nombre, modelo, id_modelo, numero_serie, descripcion, microcontrolador, activo, estado_comercial, id_propietario) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                req.nombre.strip(), modelos[0]["nombre"], req.id_modelo, req.numero_serie.strip(),
                req.descripcion, req.microcontrolador, req.activo, req.estado_comercial, req.id_propietario,
            ),
        )
    except MySQLError:
        raise HTTPException(409, "El número de serie ya está registrado.")
    nuevo_id = res["last_id"]
    db.clonar_comandos_base(nuevo_id)
    db.asegurar_demo_default(nuevo_id)
    db.registrar_auditoria(
        "REGISTRAR_UNIDAD", "vehiculos", nuevo_id,
        f"Registró unidad '{req.nombre}' (Serie {req.numero_serie}, estado {req.estado_comercial})", admin,
    )
    return {"mensaje": "Unidad registrada con 13 comandos base", "id_vehiculo": nuevo_id}

@app.put("/api/admin/vehiculos/{id_vehiculo}", tags=["Admin"])
async def editar_unidad_completa(id_vehiculo: int, req: UnidadAdminUpdateRequest, admin: dict = Depends(require_admin)):
    actual = db.ejecutar_consulta("SELECT * FROM vehiculos WHERE id_vehiculo = %s", (id_vehiculo,))
    if not actual:
        raise HTTPException(404, "Vehículo no encontrado.")

    nombre_modelo = req.modelo or actual[0]["modelo"]
    if req.id_modelo is not None:
        m = db.ejecutar_consulta("SELECT nombre FROM modelos_comerciales WHERE id_modelo = %s", (req.id_modelo,))
        if not m:
            raise HTTPException(404, "Modelo comercial no encontrado.")
        nombre_modelo = m[0]["nombre"]

    if req.id_propietario is not None:
        u = db.ejecutar_consulta("SELECT id_usuario FROM usuarios WHERE id_usuario = %s", (req.id_propietario,))
        if not u:
            raise HTTPException(404, "Propietario no encontrado.")

    try:
        db.ejecutar_escritura(
            "UPDATE vehiculos SET nombre=%s, modelo=%s, id_modelo=%s, numero_serie=%s, "
            "descripcion=%s, microcontrolador=%s, activo=%s, estado_comercial=%s, id_propietario=%s "
            "WHERE id_vehiculo=%s",
            (
                req.nombre.strip(), nombre_modelo, req.id_modelo, req.numero_serie.strip(),
                req.descripcion, req.microcontrolador, req.activo, req.estado_comercial,
                req.id_propietario, id_vehiculo,
            ),
        )
    except MySQLError:
        raise HTTPException(409, "Número de serie duplicado.")

    if actual[0]["id_propietario"] != req.id_propietario or actual[0]["estado_comercial"] != req.estado_comercial:
        await ws_manager.revocar_web_vehiculo(id_vehiculo, "Propiedad o estado comercial actualizado")

    db.registrar_auditoria(
        "EDITAR_UNIDAD", "vehiculos", id_vehiculo,
        f"Editó unidad ID {id_vehiculo}: nombre='{req.nombre}', estado={req.estado_comercial}, dueño={req.id_propietario}", admin,
    )
    return {"mensaje": "Unidad actualizada completamente"}

@app.patch("/api/admin/vehiculos/{id_vehiculo}/propietario", tags=["Admin"])
async def asignar_propietario(id_vehiculo: int, req: AsignarPropietarioRequest, admin: dict = Depends(require_admin)):
    actual = db.ejecutar_consulta("SELECT * FROM vehiculos WHERE id_vehiculo = %s", (id_vehiculo,))
    if not actual:
        raise HTTPException(404, "Vehículo no encontrado.")

    nuevo_estado = req.estado_comercial or ("VENDIDO" if req.id_propietario else "DISPONIBLE")
    if req.id_propietario is not None:
        u = db.ejecutar_consulta("SELECT username FROM usuarios WHERE id_usuario = %s", (req.id_propietario,))
        if not u:
            raise HTTPException(404, "Usuario propietario no encontrado.")

    db.ejecutar_escritura(
        "UPDATE vehiculos SET id_propietario = %s, estado_comercial = %s WHERE id_vehiculo = %s",
        (req.id_propietario, nuevo_estado, id_vehiculo),
    )
    await ws_manager.revocar_web_vehiculo(id_vehiculo, "Propietario reasignado por administrador")
    db.registrar_auditoria(
        "ASIGNAR_PROPIETARIO", "vehiculos", id_vehiculo,
        f"Asignó unidad ID {id_vehiculo} a usuario ID {req.id_propietario} (estado: {nuevo_estado})", admin,
    )
    return {"mensaje": "Propietario actualizado", "estado_comercial": nuevo_estado}

@app.patch("/api/admin/vehiculos/{id_vehiculo}/estado", tags=["Admin"])
async def cambiar_estado_comercial(id_vehiculo: int, req: CambiarEstadoRequest, admin: dict = Depends(require_admin)):
    actual = db.ejecutar_consulta("SELECT id_vehiculo FROM vehiculos WHERE id_vehiculo = %s", (id_vehiculo,))
    if not actual:
        raise HTTPException(404, "Vehículo no encontrado.")

    # Si pasa a EXHIBICION, aseguramos sus 13 comandos y limpiamos propietario para que no choque
    if req.estado_comercial == "EXHIBICION":
        db.clonar_comandos_base(id_vehiculo)
        db.asegurar_demo_default(id_vehiculo)

    db.ejecutar_escritura(
        "UPDATE vehiculos SET estado_comercial = %s WHERE id_vehiculo = %s",
        (req.estado_comercial, id_vehiculo),
    )
    await ws_manager.revocar_web_vehiculo(id_vehiculo, f"Estado cambiado a {req.estado_comercial}")
    db.registrar_auditoria(
        "CAMBIAR_ESTADO_UNIDAD", "vehiculos", id_vehiculo,
        f"Cambió estado de unidad ID {id_vehiculo} a {req.estado_comercial}", admin,
    )
    return {"mensaje": f"Estado actualizado a {req.estado_comercial}"}

@app.get("/api/admin/auditoria", tags=["Admin"])
def obtener_auditoria(limit: int = Query(default=100, ge=1, le=500), admin: dict = Depends(require_admin)):
    return db.ejecutar_consulta(
        "SELECT id_auditoria, id_usuario, username_actor, correo_actor, accion, entidad, id_entidad, detalles, fecha_hora "
        "FROM bitacora_auditoria ORDER BY id_auditoria DESC LIMIT %s",
        (limit,),
    )

# ==========================================
# 2. COMANDOS (4 SPs + RBAC)
# ==========================================
@app.post("/api/vehiculos/{id_vehiculo}/comandos", status_code=201, tags=["2. Comandos"])
def crear_comando(id_vehiculo: int, req: ComandoRequest, admin: dict = Depends(require_admin)):
    db.llamar_sp_escritura("sp_crear_comando", [id_vehiculo, req.nombre, req.codigo, req.descripcion])
    db.registrar_auditoria("CREAR_COMANDO", "comandos", id_vehiculo, f"Agregó comando {req.codigo} ({req.nombre}) a unidad {id_vehiculo}", admin)
    return {"mensaje": "Comando creado"}

@app.get("/api/vehiculos/{id_vehiculo}/comandos", tags=["2. Comandos"])
def obtener_comandos(id_vehiculo: int, actor: dict = Depends(get_current_actor)):
    validar_acceso_vehiculo(db, actor, id_vehiculo, modo="lectura")
    return db.llamar_sp_lectura("sp_obtener_comandos_vehiculo", [id_vehiculo])

@app.put("/api/comandos/{id_comando}", tags=["2. Comandos"])
def actualizar_comando(id_comando: int, req: ComandoRequest, admin: dict = Depends(require_admin)):
    db.llamar_sp_escritura("sp_actualizar_comando", [id_comando, req.nombre, req.codigo, req.descripcion, req.activo])
    db.registrar_auditoria("EDITAR_COMANDO", "comandos", id_comando, f"Editó comando ID {id_comando} ({req.nombre}, activo={req.activo})", admin)
    return {"mensaje": "Comando actualizado"}

@app.delete("/api/comandos/{id_comando}", tags=["2. Comandos"])
def eliminar_comando(id_comando: int, admin: dict = Depends(require_admin)):
    db.llamar_sp_escritura("sp_eliminar_comando", [id_comando])
    db.registrar_auditoria("ELIMINAR_COMANDO", "comandos", id_comando, f"Eliminó comando ID {id_comando}", admin)
    return {"mensaje": "Comando eliminado"}

# ==========================================
# 3. ESTADO, HISTORIAL Y CONTROL MANUAL (4 SPs + RBAC/BOLA)
# ==========================================
@app.get("/api/vehiculos/{id_vehiculo}/estado", tags=["3. Estado e Historial"])
def obtener_estado(id_vehiculo: int, actor: dict = Depends(get_current_actor)):
    validar_acceso_vehiculo(db, actor, id_vehiculo, modo="lectura")
    estado = db.llamar_sp_lectura("sp_obtener_estado", [id_vehiculo])
    esp_online = ws_manager.dispositivo_conectado(id_vehiculo)
    if estado:
        estado[0]["esp_conectado"] = esp_online
    return estado

@app.get("/api/vehiculos/{id_vehiculo}/historial", tags=["3. Estado e Historial"])
def obtener_historial(id_vehiculo: int, actor: dict = Depends(get_current_actor)):
    validar_acceso_vehiculo(db, actor, id_vehiculo, modo="lectura")
    historial = db.llamar_sp_lectura("sp_obtener_historial", [id_vehiculo])
    return historial[:10]

@app.post("/api/vehiculos/{id_vehiculo}/movimiento", status_code=201, tags=["3. Estado e Historial"])
async def ejecutar_movimiento(id_vehiculo: int, req: MovimientoRequest, actor: dict = Depends(get_current_actor)):
    vehiculo = validar_acceso_vehiculo(db, actor, id_vehiculo, modo="operar")
    if not vehiculo["activo"]:
        raise HTTPException(404, "Vehículo inactivo.")

    # Prioridad absoluta de control manual / DETENER sobre cualquier demo activa
    if id_vehiculo in active_demos and not active_demos[id_vehiculo]["task"].done():
        active_demos[id_vehiculo]["cancel_event"].set()

    comando_valido = resolver_comando_vehiculo(id_vehiculo, req.id_comando)
    if not comando_valido:
        raise HTTPException(400, "Comando inválido o deshabilitado para este vehículo.")

    origen = "INVITADO" if actor.get("rol") == "INVITADO" else req.origen
    db.registrar_movimiento(id_vehiculo, comando_valido["id_comando"], origen)

    # Enviamos el CODIGO (1..13) al hardware y clientes web de ESE vehículo
    await ws_manager.enviar_a_vehiculo(id_vehiculo, {
        "vehiculo": id_vehiculo,
        "status": comando_valido["codigo"],
        "id_comando": comando_valido["id_comando"],
        "comando_nombre": comando_valido["nombre"],
        "origen": origen,
        "type": "MOVIMIENTO_MANUAL",
    })
    return {
        "mensaje": "Movimiento aceptado",
        "id_comando": comando_valido["id_comando"],
        "codigo": comando_valido["codigo"],
        "comando": comando_valido["nombre"],
    }

# ==========================================
# 4. DEMOS (4 SPs + RBAC)
# ==========================================
@app.post("/api/vehiculos/{id_vehiculo}/demos", status_code=201, tags=["4. Demos"])
def crear_demo(id_vehiculo: int, req: DemoRequest, actor: dict = Depends(get_current_actor)):
    validar_acceso_vehiculo(db, actor, id_vehiculo, modo="gestion_demos")
    res = db.llamar_sp_escritura("sp_crear_demo", [id_vehiculo, req.nombre, req.descripcion])
    id_demo = res.get("id_demo") if isinstance(res, dict) else None
    if id_demo:
        tipo = "EMPRESA" if actor["rol"] == "ADMIN" else "PRIVADA"
        db.ejecutar_escritura(
            "UPDATE demos SET tipo_demo = %s, id_usuario_creador = %s WHERE id_demo = %s",
            (tipo, actor["id_usuario"], id_demo),
        )
        db.registrar_auditoria("CREAR_DEMO", "demos", id_demo, f"Creó demo '{req.nombre}' ({tipo}) en unidad {id_vehiculo}", actor)
    return {"mensaje": "Demo creada", "id_demo": id_demo}

@app.get("/api/vehiculos/{id_vehiculo}/demos", tags=["4. Demos"])
def obtener_demos(id_vehiculo: int, actor: dict = Depends(get_current_actor)):
    validar_acceso_vehiculo(db, actor, id_vehiculo, modo="lectura")
    return db.llamar_sp_lectura("sp_obtener_demos", [id_vehiculo])

@app.put("/api/demos/{id_demo}", tags=["4. Demos"])
def actualizar_demo(id_demo: int, req: DemoRequest, actor: dict = Depends(get_current_actor)):
    demo = obtener_vehiculo_de_demo(id_demo)
    validar_acceso_vehiculo(db, actor, demo["id_vehiculo"], modo="gestion_demos")
    db.llamar_sp_escritura("sp_actualizar_demo", [id_demo, req.nombre, req.descripcion, req.activo])
    db.registrar_auditoria("EDITAR_DEMO", "demos", id_demo, f"Actualizó demo ID {id_demo} ('{req.nombre}')", actor)
    return {"mensaje": "Demo actualizada"}

@app.delete("/api/demos/{id_demo}", tags=["4. Demos"])
def eliminar_demo(id_demo: int, actor: dict = Depends(get_current_actor)):
    demo = obtener_vehiculo_de_demo(id_demo)
    validar_acceso_vehiculo(db, actor, demo["id_vehiculo"], modo="gestion_demos")
    db.llamar_sp_escritura("sp_eliminar_demo", [id_demo])
    db.registrar_auditoria("ELIMINAR_DEMO", "demos", id_demo, f"Eliminó demo ID {id_demo} ('{demo['nombre']}')", actor)
    return {"mensaje": "Demo eliminada"}

# ==========================================
# 5. MOVIMIENTOS DEMO Y EJECUCIÓN (4 SPs + RBAC)
# ==========================================
@app.post("/api/demos/{id_demo}/movimientos", status_code=201, tags=["5. Movimientos Demo"])
def agregar_movimiento_demo(id_demo: int, req: DemoMovimientoRequest, actor: dict = Depends(get_current_actor)):
    demo = obtener_vehiculo_de_demo(id_demo)
    validar_acceso_vehiculo(db, actor, demo["id_vehiculo"], modo="gestion_demos")
    cmd = resolver_comando_vehiculo(demo["id_vehiculo"], req.id_comando)
    if not cmd:
        raise HTTPException(400, "El comando no pertenece o no está activo en este vehículo.")
    try:
        db.llamar_sp_escritura(
            "sp_agregar_movimiento_demo",
            [id_demo, cmd["id_comando"], req.orden, req.duracion_ms, req.pausa_ms],
        )
    except MySQLError:
        raise HTTPException(409, f"Ya existe un paso con el orden {req.orden} en esta demo.")
    return {"mensaje": "Movimiento agregado a la demo"}

@app.get("/api/demos/{id_demo}/movimientos", tags=["5. Movimientos Demo"])
def obtener_movimientos_demo(id_demo: int, actor: dict = Depends(get_current_actor)):
    demo = obtener_vehiculo_de_demo(id_demo)
    validar_acceso_vehiculo(db, actor, demo["id_vehiculo"], modo="lectura")
    return db.llamar_sp_lectura("sp_obtener_movimientos_demo", [id_demo])

@app.put("/api/movimientos_demo/{id_demo_movimiento}", tags=["5. Movimientos Demo"])
def actualizar_movimiento_demo(id_demo_movimiento: int, req: DemoMovimientoRequest, actor: dict = Depends(get_current_actor)):
    rows = db.ejecutar_consulta(
        "SELECT dm.id_demo, d.id_vehiculo FROM demo_movimientos dm "
        "JOIN demos d ON d.id_demo = dm.id_demo WHERE dm.id_demo_movimiento = %s LIMIT 1",
        (id_demo_movimiento,),
    )
    if not rows:
        raise HTTPException(404, "Movimiento de demo no encontrado.")
    validar_acceso_vehiculo(db, actor, rows[0]["id_vehiculo"], modo="gestion_demos")
    cmd = resolver_comando_vehiculo(rows[0]["id_vehiculo"], req.id_comando)
    if not cmd:
        raise HTTPException(400, "Comando incompatible con el vehículo.")
    try:
        db.llamar_sp_escritura(
            "sp_actualizar_movimiento_demo",
            [id_demo_movimiento, cmd["id_comando"], req.orden, req.duracion_ms, req.pausa_ms],
        )
    except MySQLError:
        raise HTTPException(409, f"Conflicto de orden ({req.orden}) duplicado en la demo.")
    return {"mensaje": "Movimiento de demo actualizado"}

@app.delete("/api/movimientos_demo/{id_demo_movimiento}", tags=["5. Movimientos Demo"])
def eliminar_movimiento_demo(id_demo_movimiento: int, actor: dict = Depends(get_current_actor)):
    rows = db.ejecutar_consulta(
        "SELECT d.id_vehiculo FROM demo_movimientos dm "
        "JOIN demos d ON d.id_demo = dm.id_demo WHERE dm.id_demo_movimiento = %s LIMIT 1",
        (id_demo_movimiento,),
    )
    if not rows:
        raise HTTPException(404, "Movimiento de demo no encontrado.")
    validar_acceso_vehiculo(db, actor, rows[0]["id_vehiculo"], modo="gestion_demos")
    db.llamar_sp_escritura("sp_eliminar_movimiento_demo", [id_demo_movimiento])
    return {"mensaje": "Movimiento de demo eliminado"}

@app.post("/api/vehiculos/{id_vehiculo}/demo/{id_demo}/iniciar", status_code=202, tags=["5. Movimientos Demo"])
async def iniciar_demo(id_vehiculo: int, id_demo: int, actor: dict = Depends(get_current_actor)):
    validar_acceso_vehiculo(db, actor, id_vehiculo, modo="operar")
    demo = obtener_vehiculo_de_demo(id_demo)
    if demo["id_vehiculo"] != id_vehiculo:
        raise HTTPException(403, "Esta demo no pertenece al vehículo seleccionado.")
    if id_vehiculo in active_demos and not active_demos[id_vehiculo]["task"].done():
        raise HTTPException(409, "Ya hay una DEMO en ejecución en esta unidad.")
    movimientos = db.llamar_sp_lectura("sp_obtener_movimientos_demo", [id_demo])
    if not movimientos:
        raise HTTPException(404, "DEMO vacía o sin pasos registrados.")

    cancel_event = asyncio.Event()
    task = asyncio.create_task(motor_ejecucion_demo(id_vehiculo, id_demo, movimientos, cancel_event))
    active_demos[id_vehiculo] = {"task": task, "cancel_event": cancel_event}
    return {"mensaje": "DEMO iniciada"}

@app.post("/api/vehiculos/{id_vehiculo}/demo/cancelar", tags=["5. Movimientos Demo"])
async def cancelar_demo(id_vehiculo: int, actor: dict = Depends(get_current_actor)):
    validar_acceso_vehiculo(db, actor, id_vehiculo, modo="operar")
    if id_vehiculo in active_demos and not active_demos[id_vehiculo]["task"].done():
        active_demos[id_vehiculo]["cancel_event"].set()
        return {"mensaje": "Señal de cancelación enviada."}
    await detener_vehiculo_seguro(id_vehiculo)
    raise HTTPException(400, "No hay DEMO activa.")

async def motor_ejecucion_demo(id_vehiculo: int, id_demo: int, movimientos: list, cancel_event: asyncio.Event):
    id_stop = obtener_id_comando_stop(id_vehiculo)
    try:
        await ws_manager.enviar_a_vehiculo(id_vehiculo, {"type": "DEMO_INICIO", "vehiculo": id_vehiculo, "id_demo": id_demo})
        for mov in movimientos:
            if cancel_event.is_set():
                break
            db.actualizar_estado_solo(id_vehiculo, mov["id_comando"], True)
            await ws_manager.enviar_a_vehiculo(id_vehiculo, {
                "type": "DEMO_PASO",
                "vehiculo": id_vehiculo,
                "status": mov["codigo"],
                "comando_nombre": mov["comando"],
                "duracion": mov["duracion_ms"],
            })
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=mov["duracion_ms"] / 1000.0)
                break
            except asyncio.TimeoutError:
                pass

            if mov["pausa_ms"] > 0 and not cancel_event.is_set():
                if id_stop:
                    db.actualizar_estado_solo(id_vehiculo, id_stop, True)
                await ws_manager.enviar_a_vehiculo(id_vehiculo, {
                    "type": "DEMO_PAUSA",
                    "vehiculo": id_vehiculo,
                    "status": 13,
                    "comando_nombre": "DETENIDO",
                    "pausa": mov["pausa_ms"],
                })
                try:
                    await asyncio.wait_for(cancel_event.wait(), timeout=mov["pausa_ms"] / 1000.0)
                    break
                except asyncio.TimeoutError:
                    pass

        if id_stop:
            db.actualizar_estado_solo(id_vehiculo, id_stop, True)
        await ws_manager.enviar_a_vehiculo(id_vehiculo, {
            "type": "DEMO_FIN",
            "vehiculo": id_vehiculo,
            "status": 13,
            "comando_nombre": "DETENIDO",
        })
    finally:
        active_demos.pop(id_vehiculo, None)

# ==========================================
# WEBSOCKETS AISLADOS POR VEHÍCULO
# ==========================================
@app.websocket("/ws/vehiculos/{id_vehiculo}")
async def websocket_cliente_web(websocket: WebSocket, id_vehiculo: int, token: str = Query(...)):
    """Canal WebSocket autenticado y aislado para navegadores."""
    try:
        actor = decodificar_y_validar_token(token)
        validar_acceso_vehiculo(db, actor, id_vehiculo, modo="lectura")
    except HTTPException:
        await websocket.close(code=4003)
        return

    await ws_manager.conectar_web(id_vehiculo, websocket, actor)
    try:
        estado_actual = db.llamar_sp_lectura("sp_obtener_estado", [id_vehiculo])
        ultimo_codigo = estado_actual[0]["codigo"] if estado_actual and estado_actual[0].get("codigo") else 13
        await websocket.send_json({
            "type": "ESTADO_INICIAL",
            "vehiculo": id_vehiculo,
            "status": ultimo_codigo,
            "esp_conectado": ws_manager.dispositivo_conectado(id_vehiculo),
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.desconectar_web(id_vehiculo, websocket)
        # Seguridad física: si un invitado se desconecta, detenemos el carrito de inmediato
        if actor.get("rol") == "INVITADO":
            await detener_vehiculo_seguro(id_vehiculo)

@app.websocket("/ws/device/{id_vehiculo}")
async def websocket_dispositivo_esp(websocket: WebSocket, id_vehiculo: int, key: str = Query(...)):
    """Canal dedicado y autenticado para el ESP8266 físico."""
    if key != DEVICE_WS_KEY:
        await websocket.close(code=4003)
        return

    await ws_manager.conectar_dispositivo(id_vehiculo, websocket)
    try:
        await websocket.send_json({"status": 13})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.desconectar_dispositivo(id_vehiculo, websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)