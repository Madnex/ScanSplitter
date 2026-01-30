
FROM python:3.12-slim

LABEL maintainer="you@example.com"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install runtime libraries useful for many Python packages (OpenCV, etc.)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
	   curl \
	   ca-certificates \
	   libgl1 \
	   libglib2.0-0 \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy app files (adjust COPY as needed for your project)
COPY . /app

# Create a non-root user for safer container runtime and create home
RUN groupadd -r app \
	&& useradd -m -r -g app app \
	&& mkdir -p /home/app/.local/bin \
	&& chown -R app:app /home/app /app

# Install uv via pip (system-wide) so `uv` and `uvx` are on PATH for all users
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
	&& pip install --no-cache-dir uv

# Ensure uv user tool bin is available when running as non-root
ENV PATH="/home/app/.local/bin:${PATH}"

# Switch to non-root user and install scansplitter as a persistent uv tool
USER app
RUN uv tool install scansplitter || true

# Expose default API port and run the ScanSplitter API on container start
# Invoke the scansplitter binary installed by `uv` directly to avoid depending
# on the `uvx` shim being on PATH.
EXPOSE 8000
CMD ["/home/app/.local/share/uv/tools/scansplitter/bin/scansplitter", "api", "--host", "0.0.0.0"]
