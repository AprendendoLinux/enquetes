from fastapi import APIRouter, Depends, HTTPException, status, Form, Response, Request, Cookie, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

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
    create_reset_token,
    verify_reset_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

# Utilitários de E-mail
from email_utils import send_verification_email, send_reset_password_email

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# --- LOGIN E REGISTRO ---

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
        hashed_password=hashed_password,
        is_verified=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Enviar e-mail de verificação
    verify_token_str = create_verification_token(email)
    base_url = str(request.base_url)
    background_tasks.add_task(send_verification_email, email, verify_token_str, base_url)
    
    return templates.TemplateResponse("register_success.html", {"request": request})

@router.post("/token")
def login_for_access_token(
    response: Response, 
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_email(db, form_data.username)
    
    # 1. Verifica credenciais (Usuário existe e senha bate)
    if not user or not verify_password(form_data.password, user.hashed_password):
        return RedirectResponse(url="/?error=Credenciais inválidas", status_code=303)
    
    # 2. Verifica bloqueio
    if user.is_blocked:
         return RedirectResponse(url="/?error=Sua conta foi bloqueada pelo administrador.", status_code=303)

    # 3. Verifica e-mail confirmado (Opcional, se seu sistema exigir)
    # if not user.is_verified:
    #      return RedirectResponse(url="/?error=Por favor, verifique seu e-mail antes de entrar.", status_code=303)

    # Sucesso: Gera Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # OBS: Se seu auth_utils.create_access_token aceita expires_delta, use assim:
    # access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    # Caso contrário (versão antiga), use apenas data:
    access_token = create_access_token(data={"sub": user.email})
    
    # Redirecionamento
    if user.email == "admin@admin":
        response = RedirectResponse(url="/admin/setup", status_code=303)
    else:
        response = RedirectResponse(url="/dashboard", status_code=303)

    response.set_cookie(
        key="access_token", 
        value=access_token, 
        httponly=True,
        max_age=1800,
        expires=1800,
        samesite="lax"
    )
    return response

@router.get("/logout")
def logout(response: Response):
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    return response

# --- RECUPERAÇÃO DE SENHA ---

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})

@router.post("/forgot-password")
def forgot_password_action(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_email(db, email)
    
    if not user:
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "error": "Este e-mail não está cadastrado em nossa base de dados."
        })

    reset_token = create_reset_token(email)
    base_url = str(request.base_url)
    background_tasks.add_task(send_reset_password_email, email, reset_token, base_url)
    
    return templates.TemplateResponse("reset_sent.html", {"request": request})


@router.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_form(request: Request, token: str):
    email = verify_reset_token(token)
    if not email:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token})

@router.post("/reset-password") 
def reset_password_action(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    email = verify_reset_token(token)
    if not email:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
    
    user = crud.get_user_by_email(db, email)
    if not user:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
    
    if new_password != confirm_password:
        return templates.TemplateResponse("reset_password.html", {
            "request": request, 
            "token": token,
            "error": "As senhas não coincidem."
        })

    new_hash = get_password_hash(new_password)
    crud.update_user_password(db, user.id, new_hash)
    
    return templates.TemplateResponse("reset_success.html", {"request": request})


# --- REENVIO DE VERIFICAÇÃO ---

@router.post("/resend-verification")
def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_email(db, email)
    if user and not user.is_verified:
        verify_token_str = create_verification_token(email)
        base_url = str(request.base_url)
        background_tasks.add_task(send_verification_email, email, verify_token_str, base_url)
        return {"status": "success", "message": "E-mail reenviado com sucesso."}
    
    return {"status": "error", "message": "Usuário não encontrado ou já verificado."}

@router.get("/verify/{token}")
def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    email = verify_email_token(token)
    if not email:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
    
    user = crud.get_user_by_email(db, email)
    if not user:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)
        
    if user.is_verified:
        return templates.TemplateResponse("verify_success.html", {"request": request})
        
    user.is_verified = True
    db.commit()
    return templates.TemplateResponse("verify_success.html", {"request": request})