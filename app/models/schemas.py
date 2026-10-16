from pydantic import BaseModel, Field
from typing import Optional

class VehiculoRequest(BaseModel):
    nombre: str
    modelo: str
    descripcion: str
    microcontrolador: str
    activo: bool = True

class ComandoRequest(BaseModel):
    nombre: str
    codigo: int
    descripcion: str
    activo: bool = True

class DemoRequest(BaseModel):
    nombre: str
    descripcion: str
    activo: bool = True

class DemoMovimientoRequest(BaseModel):
    id_comando: int
    orden: int
    duracion_ms: int
    pausa_ms: int = 0

class MovimientoRequest(BaseModel):
    id_comando: int = Field(..., gt=0, description="ID del comando a ejecutar (1 al 13)")
    origen: str = Field(default="WEB_UI", max_length=30)