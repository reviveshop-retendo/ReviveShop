FROM node:22-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev 2>/dev/null || npm install --omit=dev

COPY . .

EXPOSE 8443

CMD ["node", "server/index.js"]
