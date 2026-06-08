from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.settings import get_settings
from backend.api.routes import (
    auth, users, clients, materials, services, spools,
    settings as settings_routes, quotes, dashboard, inbox, health,
    calibration, capacity, trends, config,
)
from backend.infra.watcher.runner import start_background_task as start_watcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks for the API.

    Replaces the deprecated ``@app.on_event("startup")`` decorators. We spawn
    background tasks here (watcher + daily trends collector) and cancel them
    cleanly on shutdown so reload/dev cycles don't leak coroutines.
    """
    s = get_settings()
    tasks = []

    if s.watch_dir:
        app.state.watcher_task = start_watcher(s.watch_dir)
        tasks.append(app.state.watcher_task)

    if s.trends_enabled:
        from backend.infra.scheduler.trends import start_background_task as start_trends

        app.state.trends_task = start_trends()
        tasks.append(app.state.trends_task)

    try:
        yield
    finally:
        for t in tasks:
            t.cancel()


settings = get_settings()
app = FastAPI(title="3D Analytics", version="0.1.0", lifespan=lifespan)

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
app.include_router(calibration.router, prefix="/calibration", tags=["calibration"])
app.include_router(capacity.router, prefix="/capacity", tags=["capacity"])
app.include_router(trends.router, prefix="/trends", tags=["trends"])
app.include_router(config.router, prefix="/config", tags=["config"])
