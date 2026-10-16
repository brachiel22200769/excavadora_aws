from pydantic import BaseModel, Field

class Estado(BaseModel):
    # Solo acepta enteros entre 1 y 13
    status: int = Field(ge=1, le=13)