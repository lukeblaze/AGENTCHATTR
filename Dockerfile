FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8300 8200 8201

ENV AGENTCHATTR_HOST=0.0.0.0
ENV AGENTCHATTR_ALLOW_NETWORK=1

CMD ["python", "run.py", "--allow-network"]
