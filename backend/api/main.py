"""
VK Ads Manager - Entry Point
Минимальная точка входа для запуска API
"""
import uvicorn

from api.app import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
