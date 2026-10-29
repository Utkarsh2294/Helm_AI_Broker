FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5180
CMD ["node", "node_modules/vite/bin/vite.js", "--host", "0.0.0.0", "--port", "5180", "--strictPort"]
