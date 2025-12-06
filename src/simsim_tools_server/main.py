from dotenv import load_dotenv
import os
from fastapi import FastAPI
from .api.router import api_router


env = os.getenv("ENV", "development")
load_dotenv(".env.production" if env == "production" else ".env")


app = FastAPI()
app.include_router(api_router)


def main():
    import uvicorn

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
