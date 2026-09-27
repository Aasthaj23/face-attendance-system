from config import Config


class TestingConfig(Config):
    TESTING = True
    JWT_SECRET_KEY = "test-jwt-secret-0123456789-abcdefgh"
    API_KEY = "test-api-key-0123456789-abcdefghijk"
    PHOTO_SECRET = "test-photo-secret-0123456789-abcdef"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"