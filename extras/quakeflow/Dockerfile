# ---- build stage ---------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --prefix=/install .

# ---- runtime stage -------------------------------------------------------
FROM python:3.12-slim

LABEL org.opencontainers.image.title="quakeflow" \
      org.opencontainers.image.description="USGS earthquake ETL pipeline" \
      org.opencontainers.image.licenses="MIT"

RUN useradd --create-home --uid 1000 quake
WORKDIR /app

COPY --from=builder /install /usr/local
COPY sql ./sql

ENV PYTHONUNBUFFERED=1 QF_BRONZE_DIR=/app/data/bronze
RUN mkdir -p /app/data/bronze && chown -R quake:quake /app
USER quake

ENTRYPOINT ["quakeflow"]
CMD ["run", "--days", "1"]
