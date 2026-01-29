import time
import logging
from contextlib import asynccontextmanager
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

# --- ROTAS PRINCIPAIS ---

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
        votes = db.query(models.Vote).filter(models.Vote.poll_id == p.id).all()
        p.vote_count = len(votes)
        
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
        
        p.results_summary.sort(key=lambda x: x['votes'], reverse=True)

    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "polls": polls})

@app.get("/create_poll", response_class=HTMLResponse)
async def create_poll_page(request: Request, db: Session = Depends(get_db), access_token: str | None = Cookie(default=None)):
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    user = crud.get_user_by_email(db, email)
    return templates.TemplateResponse("create_poll.html", {"request": request, "user": user})

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
            "user": user,
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

# --- ROTAS DE PERFIL ---

@app.get("/my_profile", response_class=HTMLResponse)
async def my_profile_page(request: Request, success: str = None, error: str = None, db: Session = Depends(get_db), access_token: str | None = Cookie(default=None)):
    if not access_token:
        return RedirectResponse("/login", status_code=303)

    email = verify_token(access_token)
    if not email: 
        return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    if not user:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse("my_profile.html", {"request": request, "user": user, "success": success, "error": error})

@app.post("/my_profile/update_info")
async def update_info(
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
    return RedirectResponse("/my_profile?success=Dados atualizados com sucesso!", status_code=303)

@app.post("/my_profile/upload_avatar")
async def upload_avatar(
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    if not access_token: return RedirectResponse("/login", status_code=303)
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)

    if user.avatar_path and os.path.exists(user.avatar_path.lstrip("/")):
        try: os.remove(user.avatar_path.lstrip("/"))
        except Exception: pass

    extension = "png"
    new_filename = f"avatar_{user.id}_{uuid.uuid4()}.{extension}"
    file_location = f"{UPLOAD_DIR}/{new_filename}"
    
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(avatar.file, buffer)
    
    user.avatar_path = f"/static/uploads/{new_filename}"
    db.commit()
    
    return {"status": "ok"}

@app.post("/my_profile/request_email_change")
async def request_email_change(
    request: Request,
    background_tasks: BackgroundTasks,
    new_email: str = Form(...),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    if not access_token: return RedirectResponse("/login", status_code=303)
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    user = crud.get_user_by_email(db, email)

    # 1. VERIFICAÇÃO DE DUPLICIDADE
    existing = crud.get_user_by_email(db, new_email)
    if existing:
        return RedirectResponse("/my_profile?error=Este e-mail já está em uso por outro usuário.", status_code=303)

    token = str(uuid.uuid4())
    user.pending_email = new_email
    user.email_verification_token = token
    db.commit()

    base_url = str(request.base_url)
    background_tasks.add_task(send_change_email_request, new_email, token, base_url)

    return RedirectResponse("/my_profile?success=Um link de confirmação foi enviado para o novo e-mail.", status_code=303)

@app.get("/my_profile/verify_email")
async def verify_email_change(request: Request, token: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email_verification_token == token).first()
    
    # 1. ERRO
    if not user or not user.pending_email:
        return RedirectResponse("/login?error=Link de verificação inválido ou expirado.", status_code=303)

    # 2. VERIFICAÇÃO DE DUPLICIDADE (FINAL)
    existing_user = crud.get_user_by_email(db, user.pending_email)
    if existing_user and existing_user.id != user.id:
        return RedirectResponse("/login?error=Este e-mail já foi cadastrado por outro usuário nesse meio tempo.", status_code=303)

    # 3. EFETIVAÇÃO
    user.email = user.pending_email
    user.pending_email = None
    user.email_verification_token = None
    db.commit()

    # 4. RENDERIZA PÁGINA DE SUCESSO
    # Importante: Passamos user=None para o base.html renderizar a navbar de "não logado"
    response = templates.TemplateResponse("email_change_success.html", {"request": request, "user": None})
    response.delete_cookie("access_token")
    return response

# --- NOVA ROTA: ALTERAR SENHA (CORREÇÃO DO ERRO 404) ---
@app.post("/my_profile/change_password")
async def change_password_profile(
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
    
    # 1. Verifica se a senha atual está correta
    if not verify_password(current_password, user.hashed_password):
        return RedirectResponse("/my_profile?error=A senha atual está incorreta.", status_code=303)
    
    # 2. Verifica se as novas senhas conferem
    if new_password != confirm_password:
        return RedirectResponse("/my_profile?error=A nova senha e a confirmação não coincidem.", status_code=303)
        
    # 3. Atualiza no banco
    new_hash = get_password_hash(new_password)
    crud.update_user_password(db, user.id, new_hash)
    
    return RedirectResponse("/my_profile?success=Sua senha foi alterada com sucesso.", status_code=303)

@app.post("/my_profile/delete_account")
async def delete_account(
    password: str = Form(...),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    if not access_token: return RedirectResponse("/login", status_code=303)
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    user = crud.get_user_by_email(db, email)

    if not verify_password(password, user.hashed_password):
        return RedirectResponse("/my_profile?error=Senha incorreta. Conta não excluída.", status_code=303)

    poll_ids = db.query(models.Poll.id).filter(models.Poll.creator_id == user.id).all()
    poll_ids_list = [p[0] for p in poll_ids]
    
    if poll_ids_list:
        db.query(models.Vote).filter(models.Vote.poll_id.in_(poll_ids_list)).delete(synchronize_session=False)
        db.query(models.Option).filter(models.Option.poll_id.in_(poll_ids_list)).delete(synchronize_session=False)
        db.query(models.Poll).filter(models.Poll.id.in_(poll_ids_list)).delete(synchronize_session=False)

    db.delete(user)
    db.commit()

    response = RedirectResponse("/login?success=Sua conta foi excluída permanentemente.", status_code=303)
    response.delete_cookie("access_token")
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response