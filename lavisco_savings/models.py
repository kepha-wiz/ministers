from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    full_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Minister(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    date_joined = db.Column(db.Date, default=datetime.utcnow().date())
    total_savings = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with payments
    payments = db.relationship('Payment', backref='minister', lazy='dynamic', cascade='all, delete-orphan')
    
    def update_total_savings(self):
        total = db.session.query(db.func.sum(Payment.amount)).filter_by(minister_id=self.id).scalar() or 0
        self.total_savings = total
        db.session.commit()
    
    def __repr__(self):
        return f'<Minister {self.full_name}>'

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    minister_id = db.Column(db.Integer, db.ForeignKey('minister.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, default=datetime.utcnow().date())
    week_number = db.Column(db.Integer)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Payment {self.amount} for {self.minister.full_name}>'