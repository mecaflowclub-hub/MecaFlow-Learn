FROM continuumio/miniconda3:latest AS builder 

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Configure conda channels and create environment
RUN conda config --add channels conda-forge && \
    conda config --set channel_priority strict && \
    for i in {1..3}; do \
        echo "Attempt $i: Creating conda environment" && \
        (conda create -n app-env python=3.11 -y && break) || \
        (if [ $i -eq 3 ]; then exit 1; fi && sleep 5); \
    done && \
    for i in {1..3}; do \
        echo "Attempt $i: Installing pythonocc-core" && \
        (conda install -n app-env -c conda-forge pythonocc-core -y && break) || \
        (if [ $i -eq 3 ]; then exit 1; fi && sleep 5); \
    done && \
    conda clean -afy && \
    conda init bash && \
    echo "conda activate app-env" >> ~/.bashrc

# Create a modified requirements file without OCC-Core
RUN grep -v "OCC-Core" requirements.txt > requirements_docker.txt

# Install Python dependencies
SHELL ["/bin/bash", "-c"]
RUN /opt/conda/envs/app-env/bin/pip install --no-cache-dir -r requirements_docker.txt

# Second stage
FROM python:3.11-slim

# Install required runtime dependencies
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglu1-mesa \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy conda environment from builder
COPY --from=builder /opt/conda/envs/app-env /opt/conda/envs/app-env
ENV PATH=/opt/conda/envs/app-env/bin:$PATH

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONPATH=/app:/usr/local/lib/python3.11/site-packages
ENV LD_LIBRARY_PATH=/usr/local/lib
ENV PYTHONUNBUFFERED=1
ENV DOCKER_RUN_PATH=/app/docker_run.py

# Healthcheck configuration
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f "http://0.0.0.0:8000/api/health" || exit 1

# Entrypoint
RUN echo '#!/bin/bash\n\
echo "Starting server on fixed port 8000"\n\
exec python /app/docker_run.py\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]

# Expose port (Railway will map its own $PORT externally)
EXPOSE 8000
