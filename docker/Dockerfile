FROM nikolaik/python-nodejs:python3.9-nodejs14

# Update apt, first
RUN ["apt", "update"]

# Copy context and cd into it
COPY / /home/pn/app
WORKDIR /home/pn/app

# Install dependencies
RUN ["pip", "install", "-r", "requirements.txt"]
RUN ["npm", "install"]
RUN ["npx", "witnet-toolkit", "update"]

# Set the entrypoint
ENTRYPOINT ["python", "price_feeds_poller.py", "--loop_interval_secs", "45"]
CMD ["--toml_file", "$1"]
