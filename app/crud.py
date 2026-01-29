from sqlalchemy.orm import Session
import uuid
import models, schemas

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate, hashed_password: str):
    db_user = models.User(
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def create_poll(db: Session, poll: schemas.PollCreate, creator_id: int):
    # Cria a enquete salvando o novo campo is_public
    db_poll = models.Poll(
        title=poll.title,
        description=poll.description,
        multiple_choice=poll.multiple_choice,
        check_ip=poll.check_ip,
        is_public=poll.is_public,  # <--- NOVO CAMPO
        creator_id=creator_id,
        public_link=str(uuid.uuid4()),
        deadline=poll.deadline,
        image_path=poll.image_path
    )
    db.add(db_poll)
    db.commit()
    db.refresh(db_poll)

    for opt_text in poll.options:
        db_option = models.Option(poll_id=db_poll.id, text=opt_text)
        db.add(db_option)

    db.commit()
    return db_poll

def get_poll_by_link(db: Session, link: str):
    return db.query(models.Poll).filter(models.Poll.public_link == link).first()

# --- FUNCIONALIDADES DE DASHBOARD E LISTAGEM ---

def get_recent_public_polls(db: Session, limit: int = 10):
    """
    Busca as últimas enquetes que são PÚBLICAS e NÃO ESTÃO ARQUIVADAS.
    """
    return db.query(models.Poll).filter(
        models.Poll.is_public == True,
        models.Poll.archived == False
    ).order_by(models.Poll.id.desc()).limit(limit).all()

def delete_poll(db: Session, poll_id: int):
    # Exclusão em cascata manual
    db.query(models.Vote).filter(models.Vote.poll_id == poll_id).delete()
    db.query(models.Option).filter(models.Option.poll_id == poll_id).delete()
    db.query(models.Poll).filter(models.Poll.id == poll_id).delete()
    db.commit()

def update_poll_deadline(db: Session, poll_id: int, new_deadline):
    poll = db.query(models.Poll).filter(models.Poll.id == poll_id).first()
    if poll:
        poll.deadline = new_deadline
        db.commit()
        db.refresh(poll)
    return poll

def update_user_password(db: Session, user_id: int, new_hashed_password: str):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.hashed_password = new_hashed_password
        db.commit()

# --- FUNCIONALIDADES DE VERIFICAÇÃO DE E-MAIL ---

def activate_user(db: Session, user: models.User):
    user.is_verified = True
    db.commit()
    db.refresh(user)
    return user

def update_user_details(db: Session, user_id: int, first_name: str, last_name: str, email: str, hashed_password: str = None):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        if hashed_password:
            user.hashed_password = hashed_password
        db.commit()
        db.refresh(user)
    return user
