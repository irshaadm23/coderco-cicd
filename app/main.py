from fastapi import FastAPI

app = FastAPI(title="Service Status API")


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/version")
def version():
    return {"version": "1.0.0"}