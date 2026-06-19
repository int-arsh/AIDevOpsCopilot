FROM python:3.11-slim

# Keep Python output unbuffered and avoid writing pip caches into the image.
ENV PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1

# Install curl and CA certificates so we can download the official kubectl binary.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

# Install kubectl v1.30.0 from the official Kubernetes release URL.
RUN curl -fsSL -o /tmp/kubectl https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl \
	&& chmod +x /tmp/kubectl \
	&& mv /tmp/kubectl /usr/local/bin/kubectl

# Set the application working directory.
WORKDIR /app

# Copy dependency metadata first so Docker can cache the pip install layer.
COPY requirements.txt ./

# Install Python dependencies for the FastAPI application.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the image.
COPY . .

# Create a non-root user and grant it ownership of the application directory.
RUN useradd --create-home --shell /bin/bash appuser \
	&& chown -R appuser:appuser /app

# Switch to the non-root user for runtime execution.
USER appuser

# Expose the FastAPI service port.
EXPOSE 8000

# Start the API server.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
