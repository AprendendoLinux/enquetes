import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Cookie, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy.sql import text # Necessário para o teste de conexão
import shutil
import os
import uuid
from datetime import datetime

# Imports do seu sistema
from auth_utils import verify_token, get_password_hash 
from database import engine, Base, get_db

import auth, poll, admin 
import models, crud, schemas

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pasta de uploads
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- CRIAÇÃO DO ADMIN PADRÃO (Função auxiliar) ---
def create_default_admin():
    try:
        # Cria uma nova sessão apenas para essa operação
        db = next(get_db())
        admin_email = "admin@admin"
        user = crud.get_user_by_email(db, admin_email)
        
        if not user:
            logger.info("--- CRIANDO USUÁRIO ADMINISTRADOR PADRÃO ---")
            hashed = get_password_hash("admin")
            admin_user = models.User(
                first_name="Super",
                last_name="Admin",
                email=admin_email,
                hashed_password=hashed,
                is_verified=True, 
                is_admin=True,    
                is_blocked=False
            )
            db.add(admin_user)
            db.commit()
            logger.info(f"Admin criado: {admin_email} / senha: admin")
    except Exception as e:
        logger.error(f"Erro ao criar admin padrão: {e}")

# --- LIFESPAN: PRELOAD DO BANCO DE DADOS ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Função executada ANTES da aplicação começar a receber requisições.
    Serve para aguardar o banco de dados estar pronto.
    """
    logger.info("⏳ Aguardando banco de dados iniciar...")
    
    db_ready = False
    while not db_ready:
        try:
            # Tenta uma conexão simples
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            db_ready = True
            logger.info("✅ Banco de dados conectado com sucesso!")
        except Exception as e:
            logger.warning("⚠️ Banco ainda não disponível. Tentando novamente em 2 segundos...")
            time.sleep(2)
    
    # Agora que o banco respondeu, criamos as tabelas
    logger.info("🛠️ Verificando/Criando tabelas...")
    Base.metadata.create_all(bind=engine)
    
    # Verifica/Cria o admin
    create_default_admin()
    
    yield # A aplicação roda aqui
    
    logger.info("🛑 Aplicação encerrando...")

# --- INICIALIZAÇÃO DO APP ---
# Passamos o lifespan para o FastAPI gerenciar o start
app = FastAPI(lifespan=lifespan)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Roteadores
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(poll.router, prefix="/polls", tags=["polls"])
app.include_router(admin.router, prefix="/admin", tags=["admin"]) 

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, access_token: str | None = Cookie(default=None)):
    if access_token and verify_token(access_token):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), access_token: str | None = Cookie(default=None)):
    email = verify_token(access_token)
    if not email:
        return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    if not user:
        return RedirectResponse("/login", status_code=303)

    polls = db.query(models.Poll).filter(models.Poll.creator_id == user.id).all()
    
    for p in polls:
        p.vote_count = db.query(models.Vote).filter(models.Vote.poll_id == p.id).count()

    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "polls": polls})

@app.get("/create_poll", response_class=HTMLResponse)
async def create_poll_page(request: Request, access_token: str | None = Cookie(default=None)):
    if not access_token or not verify_token(access_token):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("create_poll.html", {"request": request})

@app.post("/create_poll")
async def create_poll_action(
    request: Request,
    title: str = Form(...),
    description: str = Form(None), # <--- NOVO (Atualizado conforme sua solicitação anterior)
    multiple_choice: bool = Form(False),
    check_ip: bool = Form(False),
    options: list[str] = Form(...),
    deadline: str | None = Form(None),
    image_file: UploadFile = File(None),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    email = verify_token(access_token)
    if not email:
        return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    
    cleaned_options = [opt.strip() for opt in options if opt.strip()]
    if len(cleaned_options) < 2:
        return templates.TemplateResponse("create_poll.html", {
            "request": request, 
            "error": "A enquete precisa de pelo menos duas opções válidas."
        })

    deadline_dt = None
    if deadline:
        try:
            deadline_dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass

    image_path_db = None
    if image_file and image_file.filename:
        extension = image_file.filename.split(".")[-1]
        new_filename = f"{uuid.uuid4()}.{extension}"
        file_location = f"{UPLOAD_DIR}/{new_filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)
        image_path_db = f"/static/uploads/{new_filename}"

    poll_create = schemas.PollCreate(
        title=title,
        description=description, # <--- NOVO
        multiple_choice=multiple_choice,
        check_ip=check_ip,
        options=cleaned_options,
        deadline=deadline_dt,
        image_path=image_path_db
    )
    
    crud.create_poll(db, poll_create, creator_id=user.id)
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response