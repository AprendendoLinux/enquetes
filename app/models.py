from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, func, Text
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Poll(Base):
    __tablename__ = "polls"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    multiple_choice = Column(Boolean, default=False)
    check_ip = Column(Boolean, default=True)
    
    # --- NOVO CAMPO ---
    is_public = Column(Boolean, default=True) 
    # ------------------
    
    creator_id = Column(Integer, ForeignKey("users.id"))
    public_link = Column(String(36), unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    archived = Column(Boolean, default=False)
    deadline = Column(DateTime, nullable=True)
    image_path = Column(String(255), nullable=True)

class Option(Base):
    __tablename__ = "options"
    id = Column(Integer, primary_key=True, index=True)
    poll_id = Column(Integer, ForeignKey("polls.id"), nullable=False)
    text = Column(String(500), nullable=False)

class Vote(Base):
    __tablename__ = "votes"
    id = Column(Integer, primary_key=True, index=True)
    poll_id = Column(Integer, ForeignKey("polls.id"), nullable=False)
    option_id = Column(Integer, ForeignKey("options.id"), nullable=False)
    voter_ip = Column(String(45), nullable=False)
    voted_at = Column(DateTime(timezone=True), server_default=func.now())