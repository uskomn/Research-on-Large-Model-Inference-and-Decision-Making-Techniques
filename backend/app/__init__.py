from flask import Flask
from flask_cors import CORS
from backend.app.api.chat import chat_bp

def create_app():
    app=Flask(__name__)
    CORS(app,supports_credentials=True,resources={r"/api/*": {"origins": "*"}})

    app.register_blueprint(chat_bp,url_prefix='/chat')
    return app