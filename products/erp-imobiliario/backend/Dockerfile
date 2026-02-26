FROM python:3.11-slim

WORKDIR /app

# Install root requirements (shared deps)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy ERP backend code
COPY products/erp-imobiliario/backend/ .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
