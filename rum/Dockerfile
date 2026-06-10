FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY rum ./rum
COPY templates ./templates
RUN pip install --no-cache-dir .

# Findings DB + evidence snapshots live on a mounted volume (req. 6:
# evidence retained >= 5 years).
ENV RUM_DATABASE_URL=sqlite:////data/rum.db \
    RUM_EVIDENCE_DIR=/data/evidence
VOLUME /data

EXPOSE 8000
CMD ["rum", "serve", "--host", "0.0.0.0"]
