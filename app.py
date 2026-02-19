from flask import Flask
from flask_cors import CORS
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import routes 


load_dotenv()

app = Flask(__name__)

CORS(app)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

mongo_uri = os.getenv('MONGO_URI')
client = MongoClient(mongo_uri)
db = client.get_database()

