from pydantic import BaseModel
from typing import Any, Dict, Optional

class CoffeeVarietiesCreate(BaseModel):
    data: Dict[str, Any]

class CoffeeVarietiesUpdate(BaseModel):
    data: Dict[str, Any]

class CoffeeVarietiesRead(BaseModel):
    data: Dict[str, Any]
