import os

class Config:
    # Flask secret key (change this in production)
    SECRET_KEY = os.environ.get("SECRET_KEY", "my_secret_key_123")

    # MongoDB Atlas URI
    MONGO_URI = os.environ.get(
        "MONGO_URI",
        "mongodb+srv://sumitha142005_db_user:MSumi1234@cluster0.zxmfqu6.mongodb.net/ecommerce?retryWrites=true&w=majority"
    )