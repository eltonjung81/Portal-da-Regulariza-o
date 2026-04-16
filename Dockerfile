# Use the official Microsoft Playwright image as base
# It includes Python and all system dependencies for browsers
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Set work directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PORT 8000

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Install only Chromium (to save space)
RUN playwright install chromium

# Expose port
EXPOSE 8000

# Run gunicorn with uvicorn workers
CMD gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT
