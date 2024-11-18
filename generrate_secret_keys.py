import secrets

# Generating a 32-byte hex secret key
secret_key = secrets.token_hex(32)
print(secret_key)
