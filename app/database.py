from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi.templating import Jinja2Templates
import os
from urllib.parse import quote_plus  # <--- 1. IMPORTAR ISTO

templates = Jinja2Templates(directory="templates")
templates.env.globals["app_version"] = os.environ.get("APP_VERSION", "dev-local")

# 2. CODIFICAR USUÁRIO E SENHA
# Isso transforma caracteres como '@' em '%40', permitindo que o banco entenda corretamente
db_user = quote_plus(os.getenv('DB_USER'))
db_password = quote_plus(os.getenv('DB_PASSWORD'))
db_host = os.getenv('DB_HOST')
db_name = os.getenv('DB_NAME')

DATABASE_URL = (
    f"mysql+mysqlconnector://"
    f"{db_user}:{db_password}@" # <--- 3. USAR AS VARIÁVEIS CODIFICADAS
    f"{db_host}/{db_name}"
    "?charset=utf8mb4"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()