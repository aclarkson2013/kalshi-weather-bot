FROM node:20-slim

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --production=false

# Copy application code
COPY . .

# Accept API URL as build arg (baked into JS bundle by Next.js)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Build the Next.js app
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
