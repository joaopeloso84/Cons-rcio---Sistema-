from pydantic import BaseModel

class Settings(BaseModel):
    app_name: str = "Consorcio Portal MVP"
    secret_key: str = "CHANGE_ME_IN_PROD"
    database_url: str = "sqlite:///./consorcio.db"

settings = Settings()
