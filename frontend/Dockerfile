# Stage 1 — build os assets estáticos
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --frozen-lockfile || npm install
COPY . .
RUN npm run build

# Stage 2 — imagem mínima que só carrega o build pra um volume compartilhado.
# Caddy é quem realmente serve em produção; essa imagem só "deposita" os
# arquivos no volume nomeado `frontend_build` e fica viva pra Docker
# considerar o serviço UP.
FROM alpine:3.20
RUN mkdir -p /srv/frontend
COPY --from=build /app/build /srv/frontend
CMD ["sh", "-c", "tail -f /dev/null"]
