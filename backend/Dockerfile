FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Pehle libraries (taaki code badalne par dobara install na ho)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Phir poora backend code
COPY . .

EXPOSE 8000
CMD ["python", "docker_start.py"]