from fastapi import APIRouter, Depends, HTTPException, Request, Form, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

# Imports do sistema
from database import get_db
import schemas, crud, models
from auth_utils import verify_token

MAX_VOTES_PER_IP = 3 

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        return x_real_ip
    return request.client.host

@router.get("/{public_link}", response_class=HTMLResponse)
def view_poll(public_link: str, request: Request, voted: str | None = None, db: Session = Depends(get_db)):
    poll = crud.get_poll_by_link(db, public_link)
    
    if not poll:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    # 1. Lógica de Expiração
    is_expired = False
    if poll.archived:
        is_expired = True
    elif poll.deadline and datetime.now() > poll.deadline:
        is_expired = True

    # 2. Lógica de Voto Já Realizado
    already_voted = False
    cookie_name = f"voted_{poll.public_link}"
    
    if voted == "true" or request.cookies.get(cookie_name) == "true":
        already_voted = True
    elif poll.check_ip: 
        voter_ip = get_client_ip(request)
        ip_votes = db.query(models.Vote).filter(
            models.Vote.poll_id == poll.id, 
            models.Vote.voter_ip == voter_ip
        ).count()
        if ip_votes >= MAX_VOTES_PER_IP:
            already_voted = True

    options = db.query(models.Option).filter(models.Option.poll_id == poll.id).all()

    return templates.TemplateResponse("poll.html", {
        "request": request, 
        "poll": poll, 
        "options": options,
        "is_archived": poll.archived, # Passa o status real
        "is_expired": (poll.deadline and datetime.now() > poll.deadline),
        "already_voted": already_voted
    })

@router.post("/{public_link}/vote")
def vote_poll(
    public_link: str, 
    request: Request, 
    db: Session = Depends(get_db),
    option: int = Form(None),       
    options: list[int] = Form(None) 
):
    poll = crud.get_poll_by_link(db, public_link)
    if not poll: raise HTTPException(404, "Enquete não encontrada")
    
    if poll.archived or (poll.deadline and datetime.now() > poll.deadline):
        return RedirectResponse(f"/polls/{public_link}", status_code=303)

    cookie_name = f"voted_{public_link}"
    if request.cookies.get(cookie_name) == "true":
        return RedirectResponse(f"/polls/{public_link}?voted=true", status_code=303)

    voter_ip = get_client_ip(request)
    if poll.check_ip:
        ip_votes = db.query(models.Vote).filter(
            models.Vote.poll_id == poll.id, 
            models.Vote.voter_ip == voter_ip
        ).count()
        if ip_votes >= MAX_VOTES_PER_IP:
            return RedirectResponse(f"/polls/{public_link}?voted=true", status_code=303)

    selected = []
    if poll.multiple_choice:
        if options: selected = options
    else:
        if option: selected = [option]

    if not selected:
        options_db = db.query(models.Option).filter(models.Option.poll_id == poll.id).all()
        return templates.TemplateResponse("poll.html", {
            "request": request, 
            "poll": poll, 
            "options": options_db,
            "is_archived": poll.archived,
            "is_expired": (poll.deadline and datetime.now() > poll.deadline),
            "already_voted": False,
            "error": "Selecione ao menos uma opção"
        })

    poll_options = db.query(models.Option).filter(models.Option.poll_id == poll.id).all()
    valid_ids = {o.id for o in poll_options}
    for opt_id in selected:
        if opt_id not in valid_ids: raise HTTPException(400, "Opção inválida")

    for opt_id in selected:
        db.add(models.Vote(poll_id=poll.id, option_id=opt_id, voter_ip=voter_ip))
    db.commit()

    redirect = RedirectResponse(url=f"/polls/{public_link}?voted=true", status_code=303)
    redirect.set_cookie(key=cookie_name, value="true", max_age=31536000, httponly=True, samesite="lax")
    return redirect

@router.get("/{public_link}/results")
def view_results(public_link: str, request: Request, db: Session = Depends(get_db)):
    poll = crud.get_poll_by_link(db, public_link)
    if not poll:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    options = db.query(models.Option).filter(models.Option.poll_id == poll.id).all()
    votes = db.query(models.Vote).filter(models.Vote.poll_id == poll.id).all()
    
    total_votes = len(votes)
    
    results_data = []
    for opt in options:
        count = sum(1 for v in votes if v.option_id == opt.id)
        if total_votes > 0:
            percent = round((count / total_votes) * 100, 1)
        else:
            percent = 0
            
        results_data.append({
            "text": opt.text, 
            "votes": count,
            "percent": percent 
        })

    return templates.TemplateResponse("results.html", {
        "request": request,
        "poll": poll,
        "results": results_data,
        "total_votes": total_votes
    })

# --- ROTAS DE GERENCIAMENTO (USUÁRIO) ---

@router.post("/{poll_id}/update_deadline")
def update_deadline(
    poll_id: int, 
    request: Request,
    deadline: str = Form(None),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    poll = db.query(models.Poll).filter(models.Poll.id == poll_id).first()
    
    if not poll or poll.creator_id != user.id:
        raise HTTPException(403, "Não autorizado")

    deadline_dt = None
    if deadline:
        try:
            deadline_dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass

    crud.update_poll_deadline(db, poll.id, deadline_dt)
    return RedirectResponse("/dashboard", status_code=303)

# ROTA: ALTERAR VISIBILIDADE (NOVO)
@router.post("/{poll_id}/toggle_visibility")
def toggle_visibility_user(
    poll_id: int, 
    request: Request,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    poll = db.query(models.Poll).filter(models.Poll.id == poll_id).first()
    
    if not poll or poll.creator_id != user.id:
        raise HTTPException(403, "Não autorizado")

    # Inverte o status atual
    poll.is_public = not poll.is_public
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)

# ROTA: ARQUIVAR
@router.post("/{poll_id}/toggle_archive")
def toggle_archive_user(
    poll_id: int, 
    request: Request,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    poll = db.query(models.Poll).filter(models.Poll.id == poll_id).first()
    
    if not poll or poll.creator_id != user.id:
        raise HTTPException(403, "Não autorizado")

    poll.archived = not poll.archived
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)

@router.post("/{poll_id}/delete")
def delete_poll_action(
    poll_id: int, 
    request: Request,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None)
):
    email = verify_token(access_token)
    if not email: return RedirectResponse("/login", status_code=303)
    
    user = crud.get_user_by_email(db, email)
    poll = db.query(models.Poll).filter(models.Poll.id == poll_id).first()
    
    if not poll or poll.creator_id != user.id:
        raise HTTPException(403, "Não autorizado")

    crud.delete_poll(db, poll_id)
    return RedirectResponse("/dashboard", status_code=303)