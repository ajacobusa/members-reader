"""WSGI entrypoint for production hosts (gunicorn / waitress).

    gunicorn wsgi:app          # Linux hosts (Render, Railway, Fly, any VPS)
    waitress-serve --port=$PORT wsgi:app   # Windows

The webhook server exposes:  /health  /order (Etsy/Make)  /ask (Ask Ange)
Order intake also works without inbound webhooks via the scheduled `poll-etsy`.
"""
from quoteforge.automation.webhook_server import app  # noqa: F401

if __name__ == "__main__":
    from quoteforge.automation.webhook_server import run_server
    run_server()
