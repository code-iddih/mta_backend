from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy_serializer import SerializerMixin

db = SQLAlchemy()

class User(db.Model, SerializerMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)

    # Relationships
    profile = db.relationship('Profile', backref='user', uselist=False, cascade='all, delete-orphan')
    wallets = db.relationship('Wallet', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Profile(db.Model, SerializerMixin):
    __tablename__ = 'profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), unique=True)
    date_of_birth = db.Column(db.Date)
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))
    profile_picture_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Wallet(db.Model, SerializerMixin):
    __tablename__ = 'wallets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    balance = db.Column(db.Numeric(19, 4), default=0.0000)
    currency = db.Column(db.String(3), default='USD')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_transaction_at = db.Column(db.DateTime)

    # Relationships
    sent_transactions = db.relationship('Transaction', 
                                      foreign_keys='Transaction.sender_wallet_id',
                                      backref='sender_wallet', lazy=True)
    received_transactions = db.relationship('Transaction',
                                          foreign_keys='Transaction.receiver_wallet_id',
                                          backref='receiver_wallet', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'currency', name='unique_user_wallet'),
    )

class Beneficiary(db.Model, SerializerMixin):
    __tablename__ = 'beneficiaries'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)  # Replaced `relationship` with `name`
    email = db.Column(db.String(255))  
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('beneficiaries', lazy=True))
    wallet = db.relationship('Wallet', backref=db.backref('beneficiaries', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'wallet_id', 'email', name='unique_beneficiary'),
    )

    def __repr__(self):
        return f"<Beneficiary(name={self.name}, email={self.email}, user_id={self.user_id}, wallet_id={self.wallet_id})>"

    def serialize(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'wallet_id': self.wallet_id,
            'name': self.name,
            'email': self.email,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

class Transaction(db.Model, SerializerMixin):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'))
    receiver_wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'))
    beneficiary_id = db.Column(db.Integer, db.ForeignKey('beneficiaries.id'), nullable=True)  # Optional
    amount = db.Column(db.Numeric(19, 4), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False)  # DEPOSIT, TRANSFER, WITHDRAWAL
    status = db.Column(db.String(50), nullable=False, default='PENDING')  # PENDING, COMPLETED, FAILED
    reference_code = db.Column(db.String(100), unique=True)
    description = db.Column(db.Text)
    fee = db.Column(db.Numeric(19, 4), default=0.0000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    # Relationships
    beneficiary = db.relationship('Beneficiary', backref=db.backref('transactions', lazy=True), uselist=False)

class DashboardMetric(db.Model, SerializerMixin):
    __tablename__ = 'dashboard_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    metric_date = db.Column(db.Date, nullable=False)
    total_users = db.Column(db.Integer, default=0)
    active_users = db.Column(db.Integer, default=0)
    total_transactions = db.Column(db.Integer, default=0)
    total_transaction_volume = db.Column(db.Numeric(19, 4), default=0)
    total_fees_collected = db.Column(db.Numeric(19, 4), default=0)
    currency = db.Column(db.String(3), default='USD')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('metric_date', 'currency', name='unique_daily_metric'),
    )

class Log(db.Model, SerializerMixin):
    __tablename__ = 'logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)  # USER, WALLET, TRANSACTION
    entity_id = db.Column(db.Integer)
    old_value = db.Column(db.JSON)
    new_value = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    user = db.relationship('User', backref=db.backref('logs', lazy=True))