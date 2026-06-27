import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "my_super_secret_key_2026")
    MONGO_URI = os.getenv("MONGO_URI")