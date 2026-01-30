import asyncio
import time
import logging
from contextlib import asynccontextmanager
from starlette.exceptions import HTTPException as StarletteHTTPException
from database import engine, Base, get_db, SessionLocal
from fastapi import FastAPI, Request, Depends, Cookie, Form, File, UploadFile, BackgroundTasks
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
from auth_utils import verify_token, get_password_hash, verify_password 
from database import engine, Base, get_db

import auth, poll, admin 
import models, crud, schemas

# Import da função de e-mail
from email_utils import send_change_email_request

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
            logger.info("--- ADMIN CRIADO: admin@admin / admin ---")
    except Exception as e:
        logger.error(f"Erro ao criar admin padrão: {e}")

# --- TAREFA EM SEGUNDO PLANO (LOOP INFINITO) ---
async def periodic_cleanup_task():
    """
    Roda infinitamente a cada 1 hora para limpar usuários expirados.
    """
    while True:
        try:
            db = SessionLocal()
            # Chama a função que criamos no crud.py
            count = crud.delete_expired_unverified_users(db)
            if count > 0:
                logger.info(f"🧹 Limpeza Automática: {count} usuários expirados foram removidos.")
            db.close()
        except Exception as e:
            logger.error(f"Erro na tarefa de limpeza automática: {e}")
        
        # Espera 1 hora (3600 segundos) antes de verificar de novo
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- LÓGICA DE RETRY (AGUARDAR BANCO) ---
    max_retries = 30
    retry_interval = 2
    logger.info("⏳ Iniciando verificação de conexão com o Banco de Dados...")
    for i in range(max_retries):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("✅ Banco de Dados conectado com sucesso!")
            break
        except Exception as e:
            logger.warning(f"⚠️ Banco indisponível. Tentativa {i+1}/{max_retries}...")
            time.sleep(retry_interval)
    else:
        logger.error("❌ Falha crítica: Não foi possível conectar ao banco.")

    # Startup normal
    try:
        models.Base.metadata.create_all(bind=engine)
        create_default_admin()
        
        # --- INICIA A TAREFA DE LIMPEZA EM SEGUNDO PLANO ---
        # Isso dispara o loop sem travar a inicialização do servidor
        asyncio.create_task(periodic_cleanup_task())
        # ---------------------------------------------------
        
    except Exception as e:
        logger.error(f"Erro durante a inicialização das tabelas: {e}")

    yield

app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Incluindo Rotas
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(poll.router, prefix="/polls", tags=["polls"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])

# --- MANIPULADOR DE ERRO 404 ---
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    # Tenta recuperar o usuário logado para não quebrar a navbar
    user = None
    try:
        token = request.cookies.get("access_token")
        if token:
            email = verify_token(token)
            if email:
                # Cria uma sessão rápida apenas para buscar o usuário
                db = SessionLocal() 
                user = crud.get_user_by_email(db, email)
                db.close()
    except:
        pass 
        
    return templates.TemplateResponse("404.html", {"request": request, "user": user}, status_code=404)

# --- CORREÇÃO 1: Rota /login redireciona para Home ---
@app.get("/login")
def login_redirect():
    return RedirectResponse("/", status_code=303)

# --- ROTA DA HOME PAGE (CORRIGIDA) ---
@app.get("/", response_class=HTMLResponse)
def read_root(
    request: Request, 
    db: Session = Depends(get_db),
    error: str = None,
    success: str = None
):
    user = None
    token = request.cookies.get("access_token")
    if token:
        email = verify_token(token)
        if email:
            user = crud.get_user_by_email(db, email)
            # --- AJUSTE AQUI ---
            # Removi o RedirectResponse("/dashboard").
            # Agora, se o usuário existe, ele simplesmente carrega a página (user=user).
            # O base.html cuidará de mostrar o menu logado.

    recent_polls = crud.get_recent_public_polls(db, limit=12)
    
    for p in recent_polls:
        p.vote_count = db.query(models.Vote).filter(models.Vote.poll_id == p.id).count()

    return templates.TemplateResponse("login.html", {
        "request": request, 
        "polls": recent_polls,
        "user": user, # Passa o usuário para a navbar
        "error": error,
        "success": success
    })

# --- ROTA DE REGISTRO ---
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

# --- DASHBOARD ---
# --- DASHBOARD (SUBSTITUIR ESTA FUNÇÃO INTEIRA) ---
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request, 
    db: Session = Depends(get_db),
    error: str = None,
    success: str = None
):
    token = request.cookies.get("access_token")
    if not token: return RedirectResponse("/", status_code=303)
    
    email = verify_token(token)
    if not email: return RedirectResponse("/", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    if not user: return RedirectResponse("/", status_code=303)
    
    # Busca as enquetes do usuário
    user_polls = db.query(models.Poll).filter(models.Poll.creator_id == user.id).order_by(models.Poll.id.desc()).all()
    
    # --- LÓGICA NOVA: Calcular estatísticas para os Modais de Resultados ---
    for p in user_polls:
        # 1. Conta o total de votos
        votes = db.query(models.Vote).filter(models.Vote.poll_id == p.id).all()
        p.vote_count = len(votes)
        
        # 2. Calcula porcentagem por opção
        options = db.query(models.Option).filter(models.Option.poll_id == p.id).all()
        summary = []
        for opt in options:
            opt_votes = sum(1 for v in votes if v.option_id == opt.id)
            percent = 0
            if p.vote_count > 0:
                percent = round((opt_votes / p.vote_count) * 100, 1)
            
            summary.append({
                "text": opt.text,
                "votes": opt_votes,
                "percent": percent
            })
        
        # Anexa o resumo na enquete para o template ler
        p.results_summary = summary
    # ---------------------------------------------------------------------

    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": user, 
        "polls": user_polls,
        "error": error,
        "success": success
    })

@app.get("/create_poll", response_class=HTMLResponse)
def create_poll_page(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token: return RedirectResponse("/", status_code=303)
    email = verify_token(token)
    if not email: return RedirectResponse("/", status_code=303)
    user = crud.get_user_by_email(db, email)
    
    return templates.TemplateResponse("create_poll.html", {"request": request, "user": user})

@app.post("/create_poll")
def create_poll_action(
    request: Request,
    title: str = Form(...),
    description: str = Form(None),
    options: list[str] = Form(...),
    multiple_choice: bool = Form(False),
    check_ip: bool = Form(False),
    is_public: bool = Form(False),
    deadline: str = Form(None),
    image_file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    if not token: return RedirectResponse("/", status_code=303)
    email = verify_token(token)
    user = crud.get_user_by_email(db, email)

    image_path = None
    if image_file and image_file.filename:
        safe_filename = f"{uuid.uuid4()}_{image_file.filename}"
        file_location = os.path.join(UPLOAD_DIR, safe_filename)
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)
        image_path = f"/static/uploads/{safe_filename}"

    deadline_dt = None
    if deadline:
        try:
            deadline_dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass

    poll_data = schemas.PollCreate(
        title=title,
        description=description,
        options=[opt for opt in options if opt.strip()],
        multiple_choice=multiple_choice,
        check_ip=check_ip,
        is_public=is_public,
        deadline=deadline_dt,
        image_path=image_path
    )
    
    crud.create_poll(db, poll_data, creator_id=user.id)
    
    return RedirectResponse("/dashboard?success=Enquete criada com sucesso!", status_code=303)

@app.get("/my_profile", response_class=HTMLResponse)
def my_profile(request: Request, db: Session = Depends(get_db), error: str = None, success: str = None):
    token = request.cookies.get("access_token")
    if not token: return RedirectResponse("/", status_code=303)
    email = verify_token(token)
    user = crud.get_user_by_email(db, email)
    if not user: return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse("my_profile.html", {
        "request": request, 
        "user": user,
        "error": error,
        "success": success
    })

@app.post("/my_profile/update_name")
def update_name(
    first_name: str = Form(...),
    last_name: str = Form(...),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    if not access_token: return RedirectResponse("/login", status_code=303)
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    user.first_name = first_name
    user.last_name = last_name
    db.commit()
    
    return RedirectResponse("/my_profile?success=Nome atualizado com sucesso.", status_code=303)

@app.post("/my_profile/upload_avatar")
def upload_avatar(
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    if not access_token: return RedirectResponse("/login", status_code=303)
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    
    if not avatar.content_type.startswith("image/"):
        return RedirectResponse("/my_profile?error=O arquivo deve ser uma imagem.", status_code=303)

    safe_filename = f"avatar_{uuid.uuid4()}_{avatar.filename}"
    file_location = os.path.join(UPLOAD_DIR, safe_filename)
    
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(avatar.file, buffer)
        
    user = crud.get_user_by_email(db, email)
    
    if user.avatar_path and os.path.exists(user.avatar_path.lstrip("/")):
        try: os.remove(user.avatar_path.lstrip("/"))
        except: pass

    user.avatar_path = f"/static/uploads/{safe_filename}"
    db.commit()
    
    return RedirectResponse("/my_profile?success=Foto de perfil atualizada.", status_code=303)

@app.post("/my_profile/request_email_change")
def request_email_change(
    request: Request,
    background_tasks: BackgroundTasks,
    new_email: str = Form(...),
    # current_password removido
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    if not access_token: return RedirectResponse("/login", status_code=303)
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    user = crud.get_user_by_email(db, email)

    # Verificação de senha removida
    
    if crud.get_user_by_email(db, new_email):
        return RedirectResponse("/my_profile?error=Este e-mail já está em uso.", status_code=303)

    user.pending_email = new_email
    token_str = str(uuid.uuid4())
    user.email_verification_token = token_str
    db.commit()

    base_url = str(request.base_url)
    background_tasks.add_task(send_change_email_request, new_email, token_str, base_url)

    return RedirectResponse("/my_profile?success=Link de confirmação enviado para o novo e-mail.", status_code=303)

@app.get("/my_profile/confirm_email_change/{token}", response_class=HTMLResponse)
def confirm_email_change(
    request: Request,
    token: str,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email_verification_token == token).first()
    
    if not user or not user.pending_email:
        return RedirectResponse("/my_profile?error=Link inválido ou expirado.", status_code=303)
    
    user.email = user.pending_email
    user.pending_email = None
    user.email_verification_token = None
    db.commit()

    response = templates.TemplateResponse("email_change_success.html", {"request": request})
    response.delete_cookie("access_token")
    return response

@app.post("/my_profile/change_password")
def change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    if not access_token: return RedirectResponse("/login", status_code=303)
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    user = crud.get_user_by_email(db, email)

    if not verify_password(current_password, user.hashed_password):
        return RedirectResponse("/my_profile?error=Senha atual incorreta.", status_code=303)

    if new_password != confirm_password:
        return RedirectResponse("/my_profile?error=A nova senha e a confirmação não coincidem.", status_code=303)

    user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return RedirectResponse("/my_profile?success=Senha foi alterada com sucesso.", status_code=303)

@app.post("/my_profile/delete_account")
def delete_account(
    password: str = Form(...),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    if not access_token: return RedirectResponse("/login", status_code=303)
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    user = crud.get_user_by_email(db, email)

    # 1. Proteção: Admin não pode se excluir
    if user.is_admin:
        return RedirectResponse("/my_profile?error=Administradores não podem excluir a própria conta.", status_code=303)

    # 2. Verifica Senha
    if not verify_password(password, user.hashed_password):
        return RedirectResponse("/my_profile?error=Senha incorreta. Conta não excluída.", status_code=303)

    # 3. Lógica Nova: DESVINCULAR enquetes em vez de apagar
    # Isso atualiza todas as enquetes desse usuário para ficarem sem dono (creator_id = None)
    db.query(models.Poll).filter(models.Poll.creator_id == user.id).update({"creator_id": None})

    # 4. Apaga o Usuário
    db.delete(user)
    db.commit()

    response = RedirectResponse("/?success=Sua conta foi excluída, mas suas enquetes públicas permanecerão ativas.", status_code=303)
    response.delete_cookie("access_token")
    return response