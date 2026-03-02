# Lightweight Node.js image for serving static files
FROM node:18-slim

# Set working directory
WORKDIR /usr/src/app

# Copy everything from root folder (telemetry, logs, html, json)
COPY . .

# Install simple static file server globally
RUN npm install -g serve

# Expose HTTP port (change if needed)
EXPOSE 8080

# Serve dist/ if exists, fallback to serving root files
CMD ["sh", "-c", "serve -s dist -l 8080 || serve -s . -l 8080"]
