FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Sur cette image, seul l'upload manuel de GTFS est proposé (pas de
# sélection dans le catalogue existant)
ENV GTFS_DISABLE_CATALOG_SELECT=1

# Hugging Face Spaces runs containers as a non-root user (uid 1000)
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Spaces routes traffic to port 7860 by default
EXPOSE 7860

HEALTHCHECK CMD curl --fail http://localhost:7860/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=7860", \
    "--server.address=0.0.0.0", \
    "--server.enableCORS=false", \
    "--server.enableXsrfProtection=false"]
