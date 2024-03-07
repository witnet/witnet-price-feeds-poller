FROM python:3.10.13-bookworm

# Update APT and install system dependencies
RUN apt update && \
    apt install -yq ca-certificates curl gnupg build-essential

# Install Nodejs
ENV NODE_MAJOR=20
RUN mkdir -p /etc/apt/keyrings
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
RUN apt install nodejs npm -yq

# Copy context and cd into it
COPY ./ /home/pn/app
WORKDIR /home/pn/app

# Install Python and NodeJS dependencies
RUN pip install -r requirements.txt
RUN npm install
RUN npx witnet-toolkit update

# Set the entrypoint
ENTRYPOINT ["python3", "price_feeds_poller.py"]