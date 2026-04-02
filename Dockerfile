FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

# Copy source
COPY . .
RUN pip install --no-cache-dir -e .

# Seed question bank + lectures
RUN python scripts/seed_local.py && python scripts/seed_lectures.py

# Expose port
EXPOSE 8000

# Run web server
CMD ["python", "-m", "phd_platform", "serve"]
