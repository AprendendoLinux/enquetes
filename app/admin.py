from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime

from database import get_db
from auth_utils import verify_token, get_password_hash, create_access_token
import crud, models

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Dependência para garantir que é ADMIN
def get_current_admin(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token: return None
    email = verify_token(token)
    if not email: return None
    user = crud.get_user_by_email(db, email)
    if not user or not user.is_admin: return None
    return user

@router.get("/", response_class=HTMLResponse)
def admin_dashboard(
    request: Request, 
    q_users: str = None, 
    q_polls: str = None, 
    db: Session = Depends(get_db)
):
    admin = get_current_admin(request, db)
    if not admin: return RedirectResponse("/login", status_code=303)
    
    # Se ainda for o admin padrão, redireciona para configuração
    if admin.email == "admin@admin": 
        return RedirectResponse("/admin/setup", status_code=303)

    # --- BUSCA DE USUÁRIOS ---
    users_query = db.query(models.User)
    if q_users:
        search_term = f"%{q_users}%"
        users_query = users_query.filter(
            or_(
                models.User.first_name.like(search_term),
                models.User.last_name.like(search_term),
                models.User.email.like(search_term)
            )
        )
    users = users_query.order_by(models.User.id.desc()).all()

    # --- BUSCA DE ENQUETES ---
    polls_query = db.query(models.Poll)
    if q_polls:
        polls_query = polls_query.filter(models.Poll.title.like(f"%{q_polls}%"))
    polls = polls_query.order_by(models.Poll.id.desc()).all()
    
    # Metadados adicionais
    for p in polls:
        p.vote_count = db.query(models.Vote).filter(models.Vote.poll_id == p.id).count()
        creator = db.query(models.User).filter(models.User.id == p.creator_id).first()
        p.creator_email = creator.email if creator else "Usuário Removido"

    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request, 
        "users": users, 
        "polls": polls,
        "admin": admin,
        "q_users": q_users,
        "q_polls": q_polls
    })

# --- ROTA DE CONFIGURAÇÃO (SETUP) CORRIGIDA ---

@router.get("/setup", response_class=HTMLResponse)
def admin_setup_page(request: Request, db: Session = Depends(get_db)):
    admin = get_current_admin(request, db)
    if not admin: return RedirectResponse("/login", status_code=303)
    
    # Só permite acessar se o email for o padrão
    if admin.email != "admin@admin":
        return RedirectResponse("/admin", status_code=303)
        
    return templates.TemplateResponse("admin_setup.html", {"request": request, "admin": admin})

@router.post("/setup")
def admin_setup_action(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),          # Corrigido: espera 'email' e não 'new_email'
    password: str = Form(...),       # Corrigido: espera 'password' e não 'new_password'
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    admin_user = get_current_admin(request, db)
    if not admin_user: return RedirectResponse("/login", status_code=303)
    
    # 1. Validação de Senha
    if password != confirm_password:
        return templates.TemplateResponse("admin_setup.html", {
             "request": request, 
             "admin": admin_user,
             "error": "As senhas não coincidem."
         })

    # 2. Verifica duplicidade de e-mail
    if email != admin_user.email:
        existing_user = crud.get_user_by_email(db, email)
        if existing_user:
             return templates.TemplateResponse("admin_setup.html", {
                 "request": request, 
                 "admin": admin_user,
                 "error": "Este e-mail já está em uso por outro usuário."
             })

    # 3. Atualiza os dados
    admin_user.first_name = first_name
    admin_user.last_name = last_name
    admin_user.email = email
    admin_user.hashed_password = get_password_hash(password)
    db.commit()
    
    # 4. Gera novo token (Login Automático) e Redireciona para Dashboard
    access_token = create_access_token(data={"sub": admin_user.email})
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax")
    
    return response

# --- ROTAS DE AÇÃO (USERS/POLLS) ---
# (Mantidas inalteradas, apenas repliquei para o arquivo ficar completo se precisar copiar tudo)

@router.post("/users/create_admin")
def create_new_admin(request: Request, first_name: str = Form(...), last_name: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    admin = get_current_admin(request, db)
    if not admin: return RedirectResponse("/login", status_code=303)
    hashed = get_password_hash(password)
    new_user = models.User(first_name=first_name, last_name=last_name, email=email, hashed_password=hashed, is_verified=True, is_admin=True)
    try: db.add(new_user); db.commit()
    except: db.rollback()
    return RedirectResponse("/admin?tab=users", status_code=303)

@router.post("/users/{user_id}/toggle_block")
def toggle_block_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_current_admin(request, db)
    if not admin: return RedirectResponse("/login", status_code=303)
    if admin.id == user_id: return RedirectResponse("/admin?error=Você não pode bloquear a si mesmo.", status_code=303)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.is_blocked = not user.is_blocked
        db.commit()
    return RedirectResponse("/admin?tab=users", status_code=303)

@router.post("/users/{user_id}/delete")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_current_admin(request, db)
    if not admin: return RedirectResponse("/login", status_code=303)
    if admin.id == user_id: return RedirectResponse("/admin?error=Você não pode deletar a si mesmo.", status_code=303)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        # Deletar enquetes do usuário primeiro
        user_polls = db.query(models.Poll).filter(models.Poll.creator_id == user_id).all()
        for p in user_polls: crud.delete_poll(db, p.id)
        db.delete(user)
        db.commit()
    return RedirectResponse("/admin?tab=users", status_code=303)

@router.post("/polls/{poll_id}/toggle_visibility")
def toggle_visibility_poll(poll_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_current_admin(request, db)
    if not admin: return RedirectResponse("/login", status_code=303)
    poll = db.query(models.Poll).filter(models.Poll.id == poll_id).first()
    if poll:
        poll.is_public = not poll.is_public
        db.commit()
    return RedirectResponse("/admin?tab=polls", status_code=303)

@router.post("/polls/{poll_id}/toggle_archive")
def toggle_archive_poll(poll_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_current_admin(request, db)
    if not admin: return RedirectResponse("/login", status_code=303)
    poll = db.query(models.Poll).filter(models.Poll.id == poll_id).first()
    if poll:
        poll.archived = not poll.archived
        db.commit()
    return RedirectResponse("/admin?tab=polls", status_code=303)

@router.post("/polls/{poll_id}/update_deadline")
def admin_update_deadline(poll_id: int, request: Request, deadline: str = Form(None), db: Session = Depends(get_db)):
    admin = get_current_admin(request, db)
    if not admin: return RedirectResponse("/login", status_code=303)
    deadline_dt = None
    if deadline and deadline.strip():
        try: deadline_dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M")
        except ValueError:
            try: deadline_dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M:%S")
            except ValueError: pass 
    crud.update_poll_deadline(db, poll_id, deadline_dt)
    return RedirectResponse("/admin?tab=polls", status_code=303)

@router.post("/polls/{poll_id}/delete")
def admin_delete_poll(poll_id: int, request: Request, db: Session = Depends(get_db)):
    admin = get_current_admin(request, db)
    if not admin: return RedirectResponse("/login", status_code=303)
    crud.delete_poll(db, poll_id)
    return RedirectResponse("/admin?tab=polls", status_code=303)