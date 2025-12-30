from dotenv import load_dotenv
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.router import api_router
from .core.logging import setup_logging
import uvicorn


env = os.getenv("ENV", "development")
load_dotenv(".env.production" if env == "production" else ".env")

setup_logging()

app = FastAPI()
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_origins=["http://localhost:5173", "https://simsimdob.github.io"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def main():
    if env == "production":
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10827)))
    else:
        uvicorn.run(
            "simsim_tools_server.main:app",
            host="0.0.0.0",
            port=int(os.getenv("PORT", 10827)),
            reload=True,
        )


if __name__ == "__main__":
    main()
