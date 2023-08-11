FROM ubuntu:jammy

# Update APT and install system dependencies
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && \
    apt-get install -yqq --no-install-recommends \
        build-essential \
        npm \
        pip \
        python3-dev

# Copy context and cd into it
COPY / /home/pn/app
WORKDIR /home/pn/app

# Install Python and NodeJS dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
RUN --mount=type=cache,target=/node_modules \
    npm install
RUN npx witnet-toolkit update

# Set the entrypoint
ENTRYPOINT ["python3", "price_feeds_poller.py"]
