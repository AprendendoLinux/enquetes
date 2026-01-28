from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

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

class PollCreate(BaseModel):
    title: str
    description: Optional[str] = None
    multiple_choice: bool = False
    check_ip: bool = True
    
    # --- NOVO CAMPO ---
    is_public: bool = True
    # ------------------
    
    options: list[str]
    deadline: Optional[datetime] = None
    image_path: Optional[str] = None

class PollOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    multiple_choice: bool
    check_ip: bool
    is_public: bool # <--- NOVO
    public_link: str
    deadline: Optional[datetime]
    image_path: Optional[str]

    model_config = ConfigDict(from_attributes=True)