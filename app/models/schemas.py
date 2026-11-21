from pydantic import BaseModel, Field
from typing import Optional, Literal

# ==========================================
# ESQUEMAS ORIGINALES (Compatibilidad 4.1/4.2)
# ==========================================
class VehiculoRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80)
    modelo: str = Field(..., max_length=80)
    descripcion: str = Field(default="", max_length=255)
    microcontrolador: str = Field(default="ESP8266", max_length=50)
    activo: bool = True

class ComandoRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=60)
    codigo: int = Field(..., ge=1, le=99)
    descripcion: str = Field(default="", max_length=255)
    activo: bool = True

class DemoRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80)
    descripcion: str = Field(default="", max_length=255)
    activo: bool = True

class DemoMovimientoRequest(BaseModel):
    id_comando: int = Field(..., gt=0)
    orden: int = Field(..., ge=1, le=200)
    duracion_ms: int = Field(..., ge=100, le=15000, description="Duración entre 100ms y 15000ms")
    pausa_ms: int = Field(default=0, ge=0, le=10000)

class MovimientoRequest(BaseModel):
    id_comando: int = Field(..., gt=0, description="ID o código del comando (1 al 13)")
    origen: str = Field(default="WEB_UI", max_length=30)

# ==========================================
# AUTENTICACIÓN Y USUARIOS
# ==========================================
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    nombre: str = Field(..., min_length=2, max_length=100)
    correo: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=6, max_length=100)

# ==========================================
# ADMINISTRACIÓN (Modelos y Unidades)
# ==========================================
EstadoComercial = Literal["DISPONIBLE", "VENDIDO", "EXHIBICION", "MANTENIMIENTO"]

class ModeloComercialRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    descripcion: str = Field(default="", max_length=255)
    especificaciones: str = Field(default="", max_length=255)
    microcontrolador_base: str = Field(default="ESP8266", max_length=50)
    activo: bool = True

class UnidadAdminCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80)
    id_modelo: int = Field(..., gt=0)
    numero_serie: str = Field(..., min_length=3, max_length=60)
    descripcion: str = Field(default="", max_length=255)
    microcontrolador: str = Field(default="ESP8266", max_length=50)
    estado_comercial: EstadoComercial = "DISPONIBLE"
    id_propietario: Optional[int] = None
    activo: bool = True

class UnidadAdminUpdateRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80)
    id_modelo: Optional[int] = None
    modelo: Optional[str] = Field(default=None, max_length=80)
    numero_serie: str = Field(..., min_length=3, max_length=60)
    descripcion: str = Field(default="", max_length=255)
    microcontrolador: str = Field(default="ESP8266", max_length=50)
    estado_comercial: EstadoComercial = "DISPONIBLE"
    id_propietario: Optional[int] = None
    activo: bool = True

class AsignarPropietarioRequest(BaseModel):
    id_propietario: Optional[int] = None
    estado_comercial: Optional[EstadoComercial] = None

class CambiarEstadoRequest(BaseModel):
    estado_comercial: EstadoComercial