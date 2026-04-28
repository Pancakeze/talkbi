from fastapi import APIRouter

from app.api.routes import auth, charts, chat, dashboards, data_sources, me, themes

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(data_sources.router)
api_router.include_router(themes.router)
api_router.include_router(chat.router)
api_router.include_router(charts.router)
api_router.include_router(dashboards.router)
