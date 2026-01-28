import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Cookie, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy.sql import text 
import shutil
import os
import uuid
from datetime import datetime

# Imports do sistema
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

def create_default_admin():
    try:
        db = next(get_db())    
        any_user = db.query(models.User).first()
        
        if not any_user:
            logger.info("--- TABELA VAZIA DETECTADA: CRIANDO ADMIN PADRÃO ---")
            hashed = get_password_hash("admin")
            admin_user = models.User(
                first_name="Super",
                last_name="Admin",
                email="admin@admin",
                hashed_password=hashed,
                is_verified=True, 
                is_admin=True,    
                is_blocked=False
            )
            db.add(admin_user)
            db.commit()
            logger.info("✅ Admin criado: admin@admin / senha: admin")
        else:
            logger.info("ℹ️ Tabela de usuários já contém dados. Criação do admin padrão ignorada.")
            
    except Exception as e:
        logger.error(f"Erro ao verificar/criar admin padrão: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("⏳ Aguardando banco de dados iniciar...")
    db_ready = False
    while not db_ready:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            db_ready = True
            logger.info("✅ Banco de dados conectado com sucesso!")
        except Exception as e:
            logger.warning(f"⚠️ Banco ainda não disponível. Erro: {e}")
            logger.warning("Tentando novamente em 2 segundos...")
            time.sleep(2)
    
    logger.info("🛠️ Verificando/Criando tabelas...")
    Base.metadata.create_all(bind=engine)
    create_default_admin()
    yield
    logger.info("🛑 Aplicação encerrando...")

app = FastAPI(lifespan=lifespan)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(poll.router, prefix="/polls", tags=["polls"])
app.include_router(admin.router, prefix="/admin", tags=["admin"]) 

# --- ROTA RAIZ ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db), access_token: str | None = Cookie(default=None)):
    user = None
    if access_token:
        email = verify_token(access_token)
        if email:
            user = crud.get_user_by_email(db, email)
    
    recent_polls = crud.get_recent_public_polls(db)
    
    for p in recent_polls:
         p.vote_count = db.query(models.Vote).filter(models.Vote.poll_id == p.id).count()

    return templates.TemplateResponse("login.html", {
        "request": request, 
        "polls": recent_polls, 
        "user": user 
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page_redirect():
    return RedirectResponse("/", status_code=303)

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

# --- DASHBOARD COM RESULTADOS PRÉ-CALCULADOS ---
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
        # Busca todos os votos dessa enquete
        votes = db.query(models.Vote).filter(models.Vote.poll_id == p.id).all()
        p.vote_count = len(votes)
        
        # Busca opções e calcula porcentagens para o modal de resumo
        options = db.query(models.Option).filter(models.Option.poll_id == p.id).all()
        p.results_summary = []
        
        for opt in options:
            opt_votes = sum(1 for v in votes if v.option_id == opt.id)
            percent = 0
            if p.vote_count > 0:
                percent = round((opt_votes / p.vote_count) * 100, 1)
            
            p.results_summary.append({
                "text": opt.text,
                "votes": opt_votes,
                "percent": percent
            })
        
        # Ordena as opções por número de votos (maior para menor) para ficar bonito no gráfico
        p.results_summary.sort(key=lambda x: x['votes'], reverse=True)

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
    description: str = Form(None),
    multiple_choice: bool = Form(False),
    check_ip: bool = Form(False),
    is_public: bool = Form(False),
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
        description=description,
        multiple_choice=multiple_choice,
        check_ip=check_ip,
        is_public=is_public,
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