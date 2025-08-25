from app import create_app
app = create_app()

# schneller Healthcheck für Docker/Azure
@app.get("/healthz")
async def healthz():
    return {"ok": True}, 200
