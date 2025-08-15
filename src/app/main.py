from fastapi import FastAPI

app = FastAPI(title="Apex Ingestion Platform")


@app.get("/health", tags=["Monitoring"])
def health_check():
    return {"status": "live-reload is working perfectly!"}
