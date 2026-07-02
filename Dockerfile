FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY clean_run/requirements.txt /app/clean_run/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/clean_run/requirements.txt

COPY clean_run /app/clean_run

EXPOSE 7860

CMD ["uvicorn", "clean_run.api:app", "--host", "0.0.0.0", "--port", "7860"]
