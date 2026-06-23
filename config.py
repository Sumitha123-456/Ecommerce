import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "my_secret_key_123")
    MONGO_URI = os.environ.get("MONGO_URI")