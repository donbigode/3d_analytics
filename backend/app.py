from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.settings import get_settings
from backend.api.routes import (
    auth, users, clients, materials, services, spools,
    settings as settings_routes, quotes, dashboard, inbox, health,
)

settings = get_settings()
app = FastAPI(title="3D Analytics", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(clients.router, prefix="/clients", tags=["clients"])
app.include_router(materials.router, prefix="/materials", tags=["materials"])
app.include_router(services.router, prefix="/services", tags=["services"])
app.include_router(spools.router, prefix="/spools", tags=["spools"])
app.include_router(settings_routes.router, prefix="/settings", tags=["settings"])
app.include_router(quotes.router, prefix="/quotes", tags=["quotes"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(inbox.router, prefix="/inbox", tags=["inbox"])
