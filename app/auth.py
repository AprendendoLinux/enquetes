from fastapi import APIRouter, Depends, HTTPException, status, Form, Response, Request, Cookie, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

# Imports do sistema
from database import get_db
import crud, models

# Utilitários de Autenticação
from auth_utils import (
    verify_password, 
    get_password_hash, 
    create_access_token, 
    verify_token, 
    create_verification_token, 
    verify_email_token,
    create_reset_token,  # <--- NOVO
    verify_reset_token   # <--- NOVO
)

# Utilitários de E-mail
from email_utils import send_verification_email, send_reset_password_email # <--- NOVO

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# --- REGISTRO E LOGIN ---

@router.post("/register")
def register(
    request: Request,
    background_tasks: BackgroundTasks, 
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    db_user = crud.get_user_by_email(db, email)
    if db_user:
        return templates.TemplateResponse("email_exists.html", {"request": request}, status_code=400)
    
    hashed_password = get_password_hash(password)
    
    new_user = models.User(
        first_name=first_name,
        last_name=last_name,
        email=email, 
        hashed_password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Gera token de verificação e detecta URL
    verify_token_str = create_verification_token(email)
    base_url = str(request.base_url)

    # Envia E-mail em segundo plano
    background_tasks.add_task(send_verification_email, email, verify_token_str, base_url)
    
    return templates.TemplateResponse("register_success.html", {"request": request, "email": email})

# ... imports ...
# Localize a função login e altere o bloco de verificação:

@router.post("/token")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_email(db, form_data.username)
    
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Usuário não encontrado"}, status_code=401)
    
    # CHECK DE BLOQUEIO (NOVO)
    if user.is_blocked:
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "error": "Esta conta foi suspensa pelo administrador."
        }, status_code=403)
    
    if not verify_password(form_data.password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Senha incorreta"}, status_code=401)

    # CHECK DE VERIFICAÇÃO DE E-MAIL
    if not user.is_verified:
        # Exceção: O Admin padrão já nasce verificado, então essa lógica não barra ele
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "error": "Conta não verificada. Por favor, verifique seu e-mail antes de entrar."
        }, status_code=403)

    access_token = create_access_token(data={"sub": user.email})
    
    # Se for o admin padrão, redirecionamos direto para o setup
    if user.email == "admin@admin":
         response = RedirectResponse(url="/admin/setup", status_code=303)
    else:
         response = RedirectResponse(url="/dashboard", status_code=303)
         
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax")
    return response

# --- VERIFICAÇÃO DE E-MAIL ---

@router.get("/verify/{token}", response_class=HTMLResponse)
def verify_account(token: str, request: Request, db: Session = Depends(get_db)):
    email = verify_email_token(token)
    
    if not email:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
    
    user = crud.get_user_by_email(db, email)
    if not user:
         return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
    
    if user.is_verified:
        return templates.TemplateResponse("verify_success.html", {"request": request})

    crud.activate_user(db, user)
    return templates.TemplateResponse("verify_success.html", {"request": request})

# --- TROCA DE SENHA (LOGADO) ---

@router.get("/change-password", response_class=HTMLResponse)
def change_password_page(request: Request):
    return templates.TemplateResponse("change_password.html", {"request": request})

@router.post("/change-password")
def change_password_action(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...), # Novo campo recebido
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    if not user: return RedirectResponse("/login", status_code=303)
    
    # 1. Verifica senha atual
    if not verify_password(current_password, user.hashed_password):
        return templates.TemplateResponse("change_password.html", {
            "request": request, 
            "error": "A senha atual está incorreta."
        })
    
    # 2. Validação no Backend: Nova senha confere com a confirmação?
    if new_password != confirm_password:
        return templates.TemplateResponse("change_password.html", {
            "request": request, 
            "error": "A nova senha e a confirmação não coincidem."
        })
        
    # 3. Atualiza para nova senha
    new_hash = get_password_hash(new_password)
    crud.update_user_password(db, user.id, new_hash)
    
    return RedirectResponse("/dashboard", status_code=303)

# --- RECUPERAÇÃO DE SENHA (ESQUECI A SENHA) ---

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})

@router.post("/forgot-password")
def forgot_password_action(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_email(db, email)
    
    # Se o usuário existir, gera token e envia e-mail
    if user:
        token = create_reset_token(email)
        base_url = str(request.base_url)
        background_tasks.add_task(send_reset_password_email, email, token, base_url)
    
    # Retorna sucesso sempre (segurança para não revelar e-mails cadastrados)
    return templates.TemplateResponse("reset_sent.html", {"request": request, "email": email})

@router.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_page(token: str, request: Request):
    # Apenas verifica se o token é válido para mostrar o formulário
    email = verify_reset_token(token)
    if not email:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
    
    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token})

# Rota POST atualizada com validação de confirmação
@router.post("/reset-password/{token}")
def reset_password_action(
    token: str,
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...), # Novo campo recebido do form
    db: Session = Depends(get_db)
):
    email = verify_reset_token(token)
    if not email:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
    
    user = crud.get_user_by_email(db, email)
    if not user:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
    
    # Validação no Backend: Senhas conferem?
    if new_password != confirm_password:
        return templates.TemplateResponse("reset_password.html", {
            "request": request, 
            "token": token,
            "error": "As senhas não coincidem."
        })

    # Atualiza a senha no banco
    new_hash = get_password_hash(new_password)
    crud.update_user_password(db, user.id, new_hash)
    
    return templates.TemplateResponse("reset_success.html", {"request": request})