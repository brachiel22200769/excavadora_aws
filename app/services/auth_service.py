import os
import uuid
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from app.services.db_service import DBService

load_dotenv(override=True)

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_cambiar_en_env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
GUEST_DURATION_MINUTES = int(os.getenv("GUEST_DURATION_MINUTES", "5"))
DEVICE_WS_KEY = os.getenv("DEVICE_WS_KEY", "EXCAVADORA_ESP8266_2026")

bearer_scheme = HTTPBearer(auto_error=False)
_db = DBService()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False

def crear_token_usuario(usuario: dict) -> tuple[str, datetime]:
    exp = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(usuario["id_usuario"]),
        "id_usuario": usuario["id_usuario"],
        "username": usuario["username"],
        "nombre": usuario["nombre"],
        "correo": usuario["correo"],
        "rol": usuario["rol"],
        "jti": uuid.uuid4().hex,
        "exp": exp,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM), exp

def crear_token_invitado(id_vehiculo: int) -> tuple[str, str, datetime]:
    jti = uuid.uuid4().hex
    exp = datetime.now(timezone.utc) + timedelta(minutes=GUEST_DURATION_MINUTES)
    payload = {
        "sub": f"guest:{jti}",
        "id_usuario": None,
        "username": "invitado",
        "nombre": "Invitado (Prueba 5 min)",
        "correo": "invitado@exhibicion",
        "rol": "INVITADO",
        "id_vehiculo": id_vehiculo,
        "jti": jti,
        "exp": exp,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM), jti, exp

def decodificar_y_validar_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión expirada.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")

    rol = payload.get("rol")
    if rol == "INVITADO":
        jti = payload.get("jti")
        rows = _db.ejecutar_consulta(
            "SELECT id_sesion, id_vehiculo, activa, expira_en "
            "FROM sesiones_invitado WHERE token_jti = %s LIMIT 1",
            (jti,),
        )
        if not rows or not rows[0]["activa"]:
            raise HTTPException(status_code=401, detail="La sesión de invitado ya finalizó.")
        exp_db = rows[0]["expira_en"]
        if exp_db.tzinfo is None:
            exp_db = exp_db.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= exp_db:
            _db.ejecutar_escritura(
                "UPDATE sesiones_invitado SET activa = FALSE, motivo_cierre = 'EXPIRADA' WHERE id_sesion = %s",
                (rows[0]["id_sesion"],),
            )
            raise HTTPException(status_code=401, detail="Tiempo de prueba de 5 minutos agotado.")
        return payload

    # Validar que el usuario exista y siga activo en RDS (nunca confiar ciegamente en el token)
    id_usuario = payload.get("id_usuario")
    users = _db.ejecutar_consulta(
        "SELECT id_usuario, username, nombre, correo, rol, activo FROM usuarios WHERE id_usuario = %s LIMIT 1",
        (id_usuario,),
    )
    if not users or not users[0]["activo"]:
        raise HTTPException(status_code=401, detail="Usuario inactivo o inexistente.")
    return users[0]

def get_current_actor(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Autenticación requerida (Bearer Token).")
    return decodificar_y_validar_token(creds.credentials)

def require_admin(actor: dict = Depends(get_current_actor)) -> dict:
    if actor.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="Acceso exclusivo para Administrador.")
    return actor

def validar_acceso_vehiculo(db: DBService, actor: dict, id_vehiculo: int, modo: str = "lectura") -> dict:
    """
    modo:
      - 'lectura': ver estado, historial, comandos, demos
      - 'operar': ejecutar movimiento manual o iniciar/cancelar demo
      - 'gestion_demos': crear/editar/borrar demos y sus pasos
    """
    rows = db.ejecutar_consulta("SELECT * FROM vehiculos WHERE id_vehiculo = %s LIMIT 1", (id_vehiculo,))
    if not rows:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado.")
    vehiculo = rows[0]
    rol = actor.get("rol")

    if rol == "ADMIN":
        # Regla de privacidad del negocio: Admin gestiona todo (inventario, demos, dueños),
        # pero NO teleopera un carrito que ya fue vendido a un comprador.
        if modo == "operar" and vehiculo.get("estado_comercial") == "VENDIDO":
            raise HTTPException(
                status_code=403,
                detail="El administrador no puede operar el control de una unidad vendida a un cliente.",
            )
        return vehiculo

    if rol == "USUARIO":
        if vehiculo.get("id_propietario") != actor.get("id_usuario"):
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para acceder a un vehículo que no es de tu propiedad.",
            )
        return vehiculo

    if rol == "INVITADO":
        if modo == "gestion_demos":
            raise HTTPException(status_code=403, detail="El modo invitado no puede modificar demos.")
        if actor.get("id_vehiculo") != id_vehiculo or vehiculo.get("estado_comercial") != "EXHIBICION":
            raise HTTPException(
                status_code=403,
                detail="El modo invitado solo puede usar la unidad de exhibición asignada.",
            )
        return vehiculo

    raise HTTPException(status_code=403, detail="Rol no autorizado.")