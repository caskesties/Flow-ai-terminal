# Northflank: build context /, Dockerfile /Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY backend/*.py /app/
ENV PYTHONUNBUFFERED=1
ENV FLOW_BRIDGE_PORT=8765
EXPOSE 8765
CMD ["python", "massive_bridge.py"]
