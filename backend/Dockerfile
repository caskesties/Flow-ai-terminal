FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY flow_classifier.py server_signals.py push_alerts.py structure_model.py elephant_model.py post_signal_monitor.py wave_research.py absorption_research.py massive_bridge.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python","massive_bridge.py"]
