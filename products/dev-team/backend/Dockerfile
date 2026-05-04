FROM python:3.11-slim

WORKDIR /app

# Install root requirements (shared deps including seed in editable mode)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install the dev_team engine package (editable to track repo changes)
COPY dev_team /opt/dev_team
RUN pip install --no-cache-dir -e /opt/dev_team

# Copy dev-team backend code
COPY products/dev-team/backend/ .

EXPOSE 8009

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
