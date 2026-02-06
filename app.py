from flask import Flask
from flask_cors import CORS
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create Flask app
app = Flask(__name__)

# Enable CORS (allows your app to make requests to this API)
CORS(app)

# Configure Flask
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Connect to MongoDB
mongo_uri = os.getenv('MONGO_URI')
client = MongoClient(mongo_uri)
db = client.get_database()

# Import routes
import routes
