FROM python:3.8-slim-buster
    
ENV PYTHONUNBUFFERED=TRUE
RUN apt-get update -y && apt-get install -y libexpat1 libgomp1 openssl libssl-dev
COPY requirements.txt .
RUN pip3 install --upgrade pip
RUN pip3 install -U --no-cache-dir -r requirements.txt
