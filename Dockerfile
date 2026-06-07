# QuoteForge / Joffiels webhook + Ask Ange server (24/7).
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt requirements-server.txt ./
RUN pip install -r requirements.txt -r requirements-server.txt

COPY . .

# Hosts inject $PORT; default 5050 for local docker run.
ENV PORT=5050
EXPOSE 5050

# Production WSGI server. /health /order /ask are served by wsgi:app.
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120"]
