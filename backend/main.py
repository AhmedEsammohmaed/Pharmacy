from fastapi import FastAPI

app = FastAPI(
    title="Pharmacy AI Agent",
    description="AI-powered pharmacy operations platform",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "Pharmacy AI Agent API is running",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }