from flask import Flask

# Initialize the Flask application
app = Flask(__name__)

# Import and register the main blueprint
from app.main import main as main_blueprint
app.register_blueprint(main_blueprint)