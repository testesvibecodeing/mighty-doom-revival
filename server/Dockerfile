FROM node:24-bookworm-slim
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY src ./src
COPY config ./config
COPY public ./public
RUN mkdir -p /app/data /app/runtime
ENV HOST=0.0.0.0 PORT=8080 DB_PATH=/app/runtime/revival.sqlite3 GAME_DATA_PATH=/app/data/game-data.json REVIVAL_CONFIG_PATH=/app/config/revival.json PACKS_CONFIG_PATH=/app/config/packs.json EVENTS_CONFIG_PATH=/app/config/events.json
EXPOSE 8080
CMD ["npm", "start"]
