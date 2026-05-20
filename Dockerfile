FROM python:3.14-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV MINTRY_JSON_LOGS=1

WORKDIR /app

# Copy package metadata and source code
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the mintry-fabric package globally
RUN pip install --no-cache-dir .

# Expose the default dashboard port
EXPOSE 8000

# Run the dashboard bound to 0.0.0.0 so it is accessible externally
ENTRYPOINT ["mintry", "dashboard", "--host", "0.0.0.0"]
