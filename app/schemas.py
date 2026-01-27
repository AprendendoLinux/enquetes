from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

# --- SCHEMAS DE USUÁRIO (Essenciais para o login e registro) ---
class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str

class UserOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS DE ENQUETE (Com o novo campo description) ---
class PollCreate(BaseModel):
    title: str
    description: Optional[str] = None  # Novo campo
    multiple_choice: bool = False
    check_ip: bool = True
    options: list[str]
    deadline: Optional[datetime] = None
    image_path: Optional[str] = None

class PollOut(BaseModel):
    id: int
    title: str
    description: Optional[str]  # Novo campo
    multiple_choice: bool
    check_ip: bool
    public_link: str
    deadline: Optional[datetime]
    image_path: Optional[str]

    model_config = ConfigDict(from_attributes=True)