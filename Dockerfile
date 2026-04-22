# Use a multi-stage build to keep the image size down
FROM python:3.12-slim-bookworm

# Install system dependencies for Camoufox (Firefox) and Zendriver (Chromium/Brave)
# and some utilities.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    gnupg \
    ca-certificates \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libx11-xcb1 \
    libasound2 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    xvfb \
    # install brave
    && curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main"|tee /etc/apt/sources.list.d/brave-browser-release.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    brave-browser \
    && rm -rf /var/lib/apt/lists/*


# Create a non-root user with explicit UID/GID matching host user
ARG UID=1000
ARG GID=1000

RUN groupadd -r -g ${GID} appuser \
    && useradd -r -u ${UID} -g appuser -G audio,video appuser \
    && mkdir -p /home/appuser && chown -R appuser:appuser /home/appuser \
    && mkdir -p /app && chown -R appuser:appuser /app

USER appuser

# Set working directory
WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY --chown=appuser:appuser pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Create a data directory for persistence and set permissions
USER root
RUN mkdir -p /data/camoufox/cache /data/zendriver && chown -R appuser:appuser /data
USER appuser

# Set environment variables for persistence
ENV DATA_DIR=/data
# Camoufox uses XDG_CACHE_HOME to find its binaries and profile by default via platformdirs
ENV XDG_CACHE_HOME=${DATA_DIR}/cache
ENV CAMOUFOX_DATA_DIR=${DATA_DIR}/camoufox
ENV CAMOUFOX_CACHE_DIR=${CAMOUFOX_DATA_DIR}/cache
ENV ZENDRIVER_DATA_DIR=${DATA_DIR}/zendriver

# Default environment variables for the app
ENV PORT=3330
ENV ROOT_PATH=""
ENV HOST=0.0.0.0

# Copy the rest of the application
COPY --chown=appuser:appuser src ./src

# Expose the default port
EXPOSE 3330

# Run the application
CMD ["sh", "-c", "uv run uvicorn src.main:app --host ${HOST} --port ${PORT}"]
