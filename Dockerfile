FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 10001 paved
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY workloads ./workloads
RUN pip install --no-cache-dir .
USER paved
ENV PAVED_ROOT=/app PAVED_EVENTS=/data/events.sqlite
EXPOSE 8000
CMD ["uvicorn", "paved.api:app", "--host", "0.0.0.0", "--port", "8000"]
