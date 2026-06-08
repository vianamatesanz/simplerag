FROM python:3.10-slim

# Set the environment paths
ENV PYTHONPATH="/app" \
    CURL_CA_BUNDLE=""

# Set the working directory in the container
WORKDIR /app

# Copy just the requirements.txt first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

# Install libreoffice
RUN apt-get update && apt-get install -y \
    libreoffice \
    libreoffice-writer \
    libreoffice-impress \
    libreoffice-calc \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy the rest of the application
COPY ./modules /app/modules
COPY ./utils /app/utils
COPY ./app.py /app/app.py
COPY ./data /app/data
COPY ./.env /app/.env