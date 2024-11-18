from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
import random
from app import create_app, db  # Import Flask app and db from your project
from models import User, Profile, Wallet, Transaction, DashboardMetric, Log  # Import models

# Helper function to generate random data
def generate_random_email(index):
    return f'user{index}@example.com'

def generate_random_name():
    first_names = ['John', 'Jane', 'Alice', 'Bob', 'Charlie']
    last_names = ['Smith', 'Doe', 'Johnson', 'Brown', 'Davis']
    return random.choice(first_names), random.choice(last_names)

def generate_random_wallet_balance():
    return round(random.uniform(50.0, 5000.0), 4)

def generate_random_transaction_type():
    return random.choice(['DEPOSIT', 'TRANSFER', 'WITHDRAWAL'])

def generate_random_transaction_status():
    return random.choice(['PENDING', 'COMPLETED', 'FAILED'])

def generate_random_transaction_amount():
    return round(random.uniform(10.0, 1000.0), 4)

def generate_random_fee():
    return round(random.uniform(0.0, 10.0), 4)

# Seed Users
def seed_users(num_users=10):
    users = []
    for i in range(num_users):
        email = generate_random_email(i)
        password_hash = generate_password_hash('password123')
        user = User(
            email=email,
            password_hash=password_hash,
            is_active=True,
            is_admin=(i == 0),  # making the first user an admin
            email_verified=True if i % 2 == 0 else False,  # some verified, some not
        )
        db.session.add(user)
        users.append(user)
    db.session.commit()
    return users

# Seed Profiles
def seed_profiles(users):
    for user in users:
        first_name, last_name = generate_random_name()
        profile = Profile(
            user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            phone_number=f"+1{random.randint(1000000000, 9999999999)}",
            date_of_birth=datetime(1990, 1, 1) + timedelta(days=random.randint(0, 10000)),
            address=f"{random.randint(100, 999)} Some St",
            city="Sample City",
            country="Sample Country",
        )
        db.session.add(profile)
    db.session.commit()

# Seed Wallets
def seed_wallets(users):
    wallets = []
    for user in users:
        wallet = Wallet(
            user_id=user.id,
            balance=generate_random_wallet_balance(),
            currency='USD',
        )
        db.session.add(wallet)
        wallets.append(wallet)
    db.session.commit()
    return wallets

# Seed Transactions
def seed_transactions(wallets, num_transactions=50):
    for _ in range(num_transactions):
        sender_wallet = random.choice(wallets)
        receiver_wallet = random.choice(wallets)
        if sender_wallet.id == receiver_wallet.id:  # avoiding sending to the same wallet
            continue
        
        transaction = Transaction(
            sender_wallet_id=sender_wallet.id,
            receiver_wallet_id=receiver_wallet.id,
            amount=generate_random_transaction_amount(),
            currency='USD',
            transaction_type=generate_random_transaction_type(),
            status=generate_random_transaction_status(),
            reference_code=f"T{random.randint(100000, 999999)}",
            description="Test transaction",
            fee=generate_random_fee(),
        )
        db.session.add(transaction)
    db.session.commit()

# Seed Dashboard Metrics
def seed_dashboard_metrics(num_metrics=10):
    for i in range(num_metrics):
        metric_date = datetime.utcnow() - timedelta(days=i)
        metric = DashboardMetric(
            metric_date=metric_date.date(),
            total_users=random.randint(50, 200),
            active_users=random.randint(30, 150),
            total_transactions=random.randint(200, 1000),
            total_transaction_volume=round(random.uniform(10000.0, 1000000.0), 4),
            total_fees_collected=round(random.uniform(500.0, 10000.0), 4),
            currency='USD',
        )
        db.session.add(metric)
    db.session.commit()

# Seed Logs
def seed_logs(users, wallets, num_logs=30):
    for i in range(num_logs):
        user = random.choice(users)
        wallet = random.choice(wallets)
        log = Log(
            user_id=user.id,
            action="Updated wallet balance",
            entity_type="WALLET",
            entity_id=wallet.id,
            old_value={"balance": round(random.uniform(50.0, 5000.0), 4)},
            new_value={"balance": round(random.uniform(50.0, 5000.0), 4)},
            ip_address=f"192.168.1.{random.randint(1, 255)}",
            user_agent="Mozilla/5.0",
        )
        db.session.add(log)
    db.session.commit()

# Main function to run all seeds
def run_seeds():
    app = create_app()  # Initializing the Flask app
    
    with app.app_context():  # Creating application context for database session
        print("Seeding Users...")
        users = seed_users()

        print("Seeding Profiles...")
        seed_profiles(users)

        print("Seeding Wallets...")
        wallets = seed_wallets(users)

        print("Seeding Transactions...")
        seed_transactions(wallets)

        print("Seeding Dashboard Metrics...")
        seed_dashboard_metrics()

        print("Seeding Logs...")
        seed_logs(users, wallets)

        print("Seeding complete!")

if __name__ == "__main__":
    run_seeds()
