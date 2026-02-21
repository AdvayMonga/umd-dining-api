from flask import Flask
from flask_cors import CORS
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CORS(app)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

mongo_uri = os.getenv('MONGO_URI')

if not mongo_uri:
    raise ValueError("MONGO_URI environment variable required")

try:
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client.get_database()
    print("Connected to MongoDB successfully")
except Exception as e:
    print("Error connecting to MongoDB:", e)
    raise
