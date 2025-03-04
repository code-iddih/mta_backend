#!/usr/bin/env python3

from flask import Flask, jsonify, request, current_app, g
from flask_migrate import Migrate
from sqlalchemy.exc import IntegrityError
from models import db, User, Profile, Wallet, Transaction, DashboardMetric, Log, Beneficiary
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from jwt import ExpiredSignatureError, InvalidTokenError
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
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
                token = token.split(" ")[1]  # Extract token from "Bearer <token>"
                data = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
                # Assuming 'user_id' is in the JWT payload, set g.current_user to the User object
                g.current_user = db.session.get(User, data['user_id'])
            except jwt.ExpiredSignatureError:
                return jsonify({'message': 'Token has expired!'}), 401
            except jwt.InvalidTokenError:
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

    # Login
    @app.route('/api/users/login', methods=['POST'])
    def login():
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            # Generate JWT token including the user_id and is_admin flag
            token = jwt.encode({
                'user_id': user.id,
                'is_admin': user.is_admin,  # Include the is_admin flag
                'exp': datetime.utcnow() + timedelta(hours=1)
            }, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")
            
            return jsonify({
                'message': 'Login successful', 
                'token': token, 
                'user_id': user.id,
                'is_admin': user.is_admin  # Return is_admin status in the response
            }), 200
        else:
            return jsonify({'message': 'Invalid email or password'}), 401
    
    # Add Profile Route (POST)
    # User Routes
    @app.route('/api/users/profiles', methods=['GET'])
    @token_required
    def get_profiles():

        profiles = Profile.query.all()  # Fetch all profiles from the database

        # Convert profiles into a list of dictionaries
        profiles_data = []
        for profile in profiles:
            profiles_data.append({
                'first_name': profile.first_name,
                'last_name': profile.last_name,
                'phone_number': profile.phone_number,
                'date_of_birth': profile.date_of_birth.isoformat() if profile.date_of_birth else None,
                'address': profile.address,
                'city': profile.city,
                'country': profile.country,
            })
        
        return jsonify(profiles_data)

    # Create Profile Route (POST)
    @app.route('/api/users/profile', methods=['POST'])
    @token_required
    def create_profile():
        data = request.get_json()

        # Ensure first_name and last_name are in the request body
        first_name = data.get('firstName')
        last_name = data.get('lastName')

        # Check if the required fields are present
        if not first_name or not last_name:
            return jsonify({"error": "First name and last name are required."}), 400

        # Create a new profile and associate it with the current user
        new_profile = Profile(
            user_id=g.current_user.id,
            first_name=first_name,  # Use the first name from the request
            last_name=last_name,    # Use the last name from the request
            phone_number=data.get('phoneNumber'),
            date_of_birth=data.get('dateOfBirth'),
            address=data.get('address'),
            city=data.get('city'),
            country=data.get('country'),
            profile_picture_url=data.get('profilePictureUrl')  # Ensure the correct field name
        )

        try:
            db.session.add(new_profile)
            db.session.commit()
            return jsonify({"message": "Profile created successfully", "profile": new_profile.phone_number}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500
            
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
    
    # Fetch User Wallet Balance
    @app.route('/api/wallets/balance', methods=['GET'])
    @token_required
    def get_wallet_balance():
        # Fetch the user's active wallet
        wallet = Wallet.query.filter_by(user_id=g.current_user.id, is_active=True).first()

        if not wallet:
            return jsonify({'message': 'No active wallet found for user'}), 404
        
        return jsonify({
            'balance': float(wallet.balance),
            'currency': wallet.currency
        })
    
    # Add Funds
    @app.route('/api/add-funds', methods=['POST'])
    @token_required
    def add_funds():
        data = request.get_json()
        amount = data.get('amount')
        user_id = data.get('user_id')  # Get user_id from the request body

        # Convert amount to Decimal to avoid type issues
        try:
            amount = Decimal(amount)
        except ValueError:
            return jsonify({'error': 'Invalid amount value'}), 400

        # Ensure the amount is greater than 0
        if amount <= 0:
            return jsonify({'error': 'Amount must be greater than 0'}), 400

        try:
            # Fetch the user's active wallet
            wallet = Wallet.query.filter_by(user_id=user_id, is_active=True).first()
            
            if not wallet:
                # Create a new wallet if none exists
                wallet = Wallet(user_id=user_id, balance=Decimal(0.0000), currency='USD', is_active=True)
                db.session.add(wallet)
                db.session.commit()

            # Add funds to the wallet
            wallet.balance += amount
            wallet.last_transaction_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'totalBalance': float(wallet.balance),  # Convert balance to float for response
                'currency': wallet.currency,
            }), 200  # Explicitly return a 200 status code for success
        except Exception as e:
            db.session.rollback()
            print(f"Error: {e}")
            return jsonify({'error': 'Error processing request'}), 500
        
    # Send Money
    @app.route("/api/send-money", methods=["POST"])
    @token_required
    def send_money():
        data = request.get_json()
        beneficiary_email = data.get("beneficiary")
        amount = Decimal(data.get("amount", 0))

        if amount <= 0:
            return jsonify({"error": "Amount must be greater than 0"}), 400

        try:
            sender = g.current_user
            recipient = User.query.filter_by(email=beneficiary_email).first()

            if not recipient:
                return jsonify({"error": "Recipient not found"}), 404

            sender_wallet = sender.wallets[0]  # Assuming only one wallet
            recipient_wallet = recipient.wallets[0]  # Assuming only one wallet

            if sender_wallet.balance < amount:
                return jsonify({"error": "Insufficient balance"}), 400

            # Deduct from sender's wallet
            sender_wallet.balance -= amount

            # Add to recipient's wallet
            recipient_wallet.balance += amount

            # Commit changes
            db.session.commit()

            return jsonify({
                "updatedAnalytics": {"totalBalance": float(sender_wallet.balance)},
                "recipientBalance": float(recipient_wallet.balance),
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "Error processing transaction", "details": str(e)}), 500

    # Transaction Routes
    @app.route('/api/transactions', methods=['GET'])
    @token_required
    def get_transactions():
        transactions = Transaction.query.all()  # Fetch all transactions

        # Create a list of transaction details
        transactions_data = []
        for transaction in transactions:
            transactions_data.append({
                'transaction_id': transaction.id,
                'sender_wallet_id': transaction.sender_wallet_id,
                'receiver_wallet_id': transaction.receiver_wallet_id,
                'beneficiary': transaction.beneficiary.name if transaction.beneficiary else None,
                'amount': str(transaction.amount),  # Convert to string for JSON serialization
                'currency': transaction.currency,
                'transaction_type': transaction.transaction_type,
                'status': transaction.status,
                'reference_code': transaction.reference_code,
                'description': transaction.description,
                'fee': str(transaction.fee),  # Convert fee to string
                'created_at': transaction.created_at.isoformat(),
                'updated_at': transaction.updated_at.isoformat() if transaction.updated_at else None,
                'completed_at': transaction.completed_at.isoformat() if transaction.completed_at else None
            })
        
        return jsonify(transactions_data)
    
    # Beneficiaries
    # Get Beneficiaries Route
    # Get Beneficiaries Route
    @app.route('/api/beneficiaries', methods=['GET'])
    @token_required
    def get_beneficiaries():
        user_id = g.current_user.id  # Get the user ID from the token

        # Fetch beneficiaries for the current user directly from the Beneficiary table
        beneficiaries = Beneficiary.query.filter_by(user_id=user_id).all()

        # Serialize the beneficiaries list
        beneficiaries_data = [beneficiary.serialize() for beneficiary in beneficiaries]

        return jsonify({'beneficiaries': beneficiaries_data}), 200


    # Add Beneficiary Route
    # Add Beneficiary Route
    @app.route('/api/beneficiaries', methods=['POST'])
    @token_required
    def add_beneficiary():
        data = request.get_json()

        # Validate the required fields: 'name' and 'email'
        if not data.get('name') or not data.get('email'):
            return jsonify({'message': 'Name and email are required.'}), 400

        user_id = g.current_user.id  # Get the user ID from the token

        try:
            # Fetch the user based on email to get wallet_id
            user = User.query.filter_by(email=data['email']).first()

            # If user does not exist with that email
            if not user:
                return jsonify({'message': 'No user found with this email.'}), 404

            # Fetch wallet_id associated with the user
            wallet = Wallet.query.filter_by(user_id=user.id).first()

            if not wallet:
                return jsonify({'message': 'User does not have a wallet.'}), 404

            wallet_id = wallet.id  # Get the wallet_id from the wallet associated with the user

            # Check if the beneficiary already exists (unique constraint check for user_id, wallet_id, and email)
            existing_beneficiary = Beneficiary.query.filter_by(
                user_id=user_id, email=data['email'], wallet_id=wallet_id
            ).first()

            if existing_beneficiary:
                return jsonify({'message': 'This beneficiary already exists.'}), 409

            # Create a new beneficiary with 'name' and 'email'
            new_beneficiary = Beneficiary(
                user_id=user_id,
                wallet_id=wallet_id,
                name=data['name'],  # Save the beneficiary name
                email=data['email']  # Save the email
            )

            db.session.add(new_beneficiary)
            db.session.commit()

            # Log the creation of the new beneficiary (this should not cause an error)
            create_log("CREATE_BENEFICIARY", "BENEFICIARY", new_beneficiary.id, new_value=new_beneficiary.to_dict())

            return jsonify({
                'message': 'Beneficiary added successfully',
                'beneficiary': new_beneficiary.serialize()  # Assuming you have a `serialize()` method in the model
            }), 201

        except Exception as e:
            # Rollback in case of an exception
            db.session.rollback()

            # Log the error (you can also use a more specific logging method here)
            create_log("ERROR", "BENEFICIARY_CREATION", None, new_value={'error': str(e)})

            # Return a generic error message to the client, without revealing details
            return jsonify({'message': 'Something went wrong. Please try again later.'}), 500
    
    # Admin Routes

    # View all users - Only accessible by admin
    @app.route('/api/users/admin', methods=['GET'])
    @token_required
    @admin_required
    def get_users():
        users = User.query.all()
        return jsonify([{
            'id': user.id,
            'email': user.email,
            'is_admin': user.is_admin
        } for user in users])

    # Register new user
    @app.route('/api/users/create', methods=['POST'])
    @token_required
    @admin_required
    def create_user():
        data = request.get_json()

        if User.query.filter_by(email=data['email']).first():
            return jsonify({'message': 'Email already registered'}), 400

        user = User(email=data['email'])
        user.set_password(data['password'])

        profile = Profile(
            first_name=data['first_name'],
            last_name=data['last_name'],
            phone_number=data.get('phone_number'),
            date_of_birth=data.get('date_of_birth'),
            address=data.get('address'),
            city=data.get('city'),
            country=data.get('country'),
            user=user
        )

        try:
            db.session.add(user)
            db.session.add(profile)
            db.session.commit()
            return jsonify({'message': 'User registered successfully'}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'message': 'Error registering user', 'error': str(e)}), 500

    # Edit user - Admin or the user themselves can update details
    @app.route('/api/users/<int:user_id>', methods=['PUT'])
    @token_required
    def edit_user(user_id):
        if g.current_user.id != user_id and not g.current_user.is_admin:
            return jsonify({'message': 'Permission denied'}), 403

        data = request.get_json()
        user = User.query.get_or_404(user_id)

        if 'email' in data:
            user.email = data['email']
        
        profile = user.profile
        if 'first_name' in data:
            profile.first_name = data['first_name']
        if 'last_name' in data:
            profile.last_name = data['last_name']
        if 'phone_number' in data:
            profile.phone_number = data['phone_number']
        if 'date_of_birth' in data:
            profile.date_of_birth = data.get('date_of_birth')
        if 'address' in data:
            profile.address = data['address']
        if 'city' in data:
            profile.city = data['city']
        if 'country' in data:
            profile.country = data['country']
        
        try:
            db.session.commit()
            return jsonify({'message': 'User updated successfully'}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'message': 'Error updating user', 'error': str(e)}), 500

    # Delete user - Only accessible by admin
    @app.route('/api/users/<int:user_id>', methods=['DELETE'])
    @token_required
    @admin_required
    def delete_user(user_id):
        user = User.query.get_or_404(user_id)
        try:
            db.session.delete(user.profile)
            db.session.delete(user)
            db.session.commit()
            return jsonify({'message': 'User deleted successfully'}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'message': 'Error deleting user', 'error': str(e)}), 500
        
    # All Wallet Analytics

    @app.route('/api/wallets/analytics', methods=['GET'])
    @token_required
    def get_wallet_analytics():
        wallets = Wallet.query.all()  # Assuming Wallet is a model with balance info
        wallets_data = []

        for wallet in wallets:
            wallets_data.append({
                'user_id': wallet.user_id,
                'balance': str(wallet.balance),  # Convert balance to string for JSON serialization
                'currency': wallet.currency,
                'created_at': wallet.created_at.isoformat(),
            })

        return jsonify(wallets_data)


    return app

# Running the app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5555, debug=True)