import firebase_admin
from firebase_admin import credentials, auth
import os
from dotenv import load_dotenv
load_dotenv()

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)

users = [
    {"email": "admin@technion.ac.il", "password": "password123", "displayName": "Admin User"},
    {"email": "student@technion.ac.il", "password": "password123", "displayName": "John Doe"},
    {"email": "lecturer@technion.ac.il", "password": "password123", "displayName": "Dr. Smith"},
    {"email": "jane@technion.ac.il", "password": "password123", "displayName": "Jane Roe"},
]

for u in users:
    try:
        user = auth.create_user(
            email=u["email"],
            password=u["password"],
            display_name=u["displayName"]
        )
        print(f"Successfully created user: {user.email}")
    except Exception as e:
        print(f"Error creating user {u['email']}: {e}")

print("Done creating auth users!")
