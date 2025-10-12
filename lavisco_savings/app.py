from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config
from models import db, User

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    
    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))
    
    # Import and register routes
    from routes import init_routes
    init_routes(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        
        # Create default admin user if not exists
        if User.query.filter_by(username='admin').first() is None:
            admin = User(
                username='admin',
                email='admin@lavisco.com',
                full_name='System Administrator'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
    
    return app