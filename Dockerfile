# Evidence-First Harness Sandbox
# Ephemeral Docker container for executing untrusted repository code.
# Multi-stage: builder installs tools, runtime is minimal.

FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install evidence tools
RUN pip install --no-cache-dir \
    ruff \
    pyright \
    pytest \
    pytest-cov

FROM python:3.12-slim AS runtime

# Create non-root user
RUN useradd --create-home --shell /bin/bash sandbox

# Copy installed tools from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Install runtime deps for tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up sandbox user
USER sandbox
WORKDIR /workspace

# Default command (overridden by harness)
CMD ["echo", "Sandbox ready"]
