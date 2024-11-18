#!/usr/bin/env python3

from flask import Flask, jsonify, request, current_app, g
from flask_migrate import Migrate
from sqlalchemy.exc import IntegrityError
from models import db, User, Profile, Wallet, Transaction, DashboardMetric, Log
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from jwt import ExpiredSignatureError, InvalidTokenError
from functools import wraps
import jwt
import uuid
import os
from pathlib import Path
from flask_cors import CORS
from decimal import Decimal

# Load .env file
dotenv_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path)

# Flask Application Factory
def create_app():
    app = Flask(
        __name__,
        static_url_path='',
        static_folder='../Frontend/build',
        template_folder='../Frontend/build'
    )

    # Enabling CORS for all routes
    CORS(app)

    # Configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')

    # Initializing database, migration, and JWT
    db.init_app(app)
    migrate = Migrate(app, db)

    # Token verification decorator
    def token_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get('Authorization')
            if not token:
                return jsonify({'message': 'Token is missing!'}), 403
            try:
                token = token.split(" ")[1]  
                data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
                g.current_user = db.session.get(User, data['user_id'])
            except ExpiredSignatureError:
                return jsonify({'message': 'Token has expired!'}), 401
            except InvalidTokenError:
                return jsonify({'message': 'Invalid token!'}), 401
            except Exception as e:
                return jsonify({'message': 'Token is invalid!', 'error': str(e)}), 403
            return f(*args, **kwargs)
        return decorated_function

    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.current_user.is_admin:
                return jsonify({'message': 'Admin privileges required'}), 403
            return f(*args, **kwargs)
        return decorated_function

    # Logging creation function
    def create_log(action, entity_type, entity_id, old_value=None, new_value=None):
        log = Log(
            user_id=g.current_user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        db.session.add(log)
        db.session.commit()

    # Auth Routes
    @app.route('/api/users/register', methods=['POST'])
    def register():
        data = request.get_json()

        # Checking if the email is already registered
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'message': 'Email already registered'}), 400
        
        # Creating the user
        user = User(email=data['email'])
        user.set_password(data['password'])

        # Saving user to DB
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'message': 'User registered successfully'}), 201

    @app.route('/api/users/login', methods=['POST'])
    def login():
        data = request.get_json()
        user = User.query.filter_by(email=data['email']).first()
        
        if user and user.check_password(data['password']):
            # Setting the user in g.current_user
            g.current_user = user
            
            # Updating the last_login_at field with timezone-aware datetime
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            
            token = jwt.encode(
                {'user_id': user.id, 'exp': datetime.utcnow() + timedelta(days=1)},
                current_app.config['SECRET_KEY']
            )
            
            create_log("LOGIN", "USER", user.id)
            return jsonify({'token': token})
        
        return jsonify({'message': 'Invalid credentials'}), 401

    # User Routes
    @app.route('/api/users/profile', methods=['GET'])
    @token_required
    def get_profile():
        return jsonify({
            'email': g.current_user.email,
            'profile': {
                'phone_number': g.current_user.profile.phone_number,
                'date_of_birth': g.current_user.profile.date_of_birth.isoformat() if g.current_user.profile.date_of_birth else None,
            }
        })

    @app.route('/api/users/profile', methods=['PUT'])
    @token_required
    def update_profile():
        data = request.get_json()

        # The user_id is already available via g.current_user.id
        profile = db.session.get(Profile, g.current_user.id)

        if not profile: 
            # If no profile exists, create a new one
            profile = Profile(user_id=g.current_user.id)
            db.session.add(profile)

        old_profile_data = profile.to_dict()

        # Update the profile fields
        for key, value in data.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        try:
            db.session.commit()
            # Log the profile update or creation
            create_log("UPDATE_PROFILE" if old_profile_data else "CREATE_PROFILE", "PROFILE", profile.id, old_value=old_profile_data, new_value=profile.to_dict())
            return jsonify({'message': 'Profile updated/created successfully'})
        except IntegrityError as e:
            db.session.rollback()
            return jsonify({'error': 'Profile update failed. Integrity error.'}), 400
            
    # Wallet Routes
    @app.route('/api/wallets', methods=['GET'])
    @token_required
    def get_wallets():
        wallets = g.current_user.wallets
        return jsonify([{
            'id': w.id,
            'balance': float(w.balance),
            'currency': w.currency,
            'is_active': w.is_active,
            'last_transaction_at': w.last_transaction_at.isoformat() if w.last_transaction_at else None
        } for w in wallets])

    @app.route('/api/wallets', methods=['POST'])
    @token_required
    def create_wallet():
        data = request.get_json()
        currency = data.get('currency', 'USD')
        if Wallet.query.filter_by(user_id=g.current_user.id, currency=currency).first():
            return jsonify({'message': f'Wallet for {currency} already exists'}), 400
        wallet = Wallet(user_id=g.current_user.id, currency=currency)
        db.session.add(wallet)
        db.session.commit()
        
        create_log("CREATE_WALLET", "WALLET", wallet.id)
        return jsonify({
            'id': wallet.id,
            'balance': float(wallet.balance),
            'currency': wallet.currency
        }), 201

    # Transaction Routes
    @app.route('/api/transactions', methods=['POST'])
    @token_required
    def create_transaction():
        data = request.get_json()
        sender_wallet = Wallet.query.get_or_404(data['sender_wallet_id'])
        if sender_wallet.user_id != g.current_user.id:
            return jsonify({'message': 'Unauthorized access to wallet'}), 403
        if sender_wallet.balance < Decimal(str(data['amount'])):
            return jsonify({'message': 'Insufficient funds'}), 400
        transaction = Transaction(
            sender_wallet_id=sender_wallet.id,
            receiver_wallet_id=data['receiver_wallet_id'],
            amount=data['amount'],
            currency=sender_wallet.currency,
            transaction_type='TRANSFER',
            reference_code=str(uuid.uuid4()),
            description=data.get('description')
        )
        db.session.add(transaction)
        db.session.commit()
        
        create_log("CREATE_TRANSACTION", "TRANSACTION", transaction.id, new_value=transaction.to_dict())
        return jsonify({
            'id': transaction.id,
            'reference_code': transaction.reference_code,
            'status': transaction.status
        }), 201

    # Dashboard Routes
    @app.route('/api/dashboard/metrics', methods=['GET'])
    @token_required
    @admin_required
    def get_dashboard_metrics():
        date_from = request.args.get('from')
        date_to = request.args.get('to')
        metrics = DashboardMetric.query.filter(
            DashboardMetric.metric_date.between(date_from, date_to)
        ).order_by(DashboardMetric.metric_date.desc()).all()
        return jsonify([{
            'date': m.metric_date.isoformat(),
            'total_users': m.total_users,
            'active_users': m.active_users,
            'total_transactions': m.total_transactions,
            'total_transaction_volume': float(m.total_transaction_volume),
            'total_fees_collected': float(m.total_fees_collected),
            'currency': m.currency
        } for m in metrics])

    return app

# Running the app

if __name__ == '__main__':
    app = create_app()
    app.run(port=5555, debug=False)
