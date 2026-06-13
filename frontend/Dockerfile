# Stage 1 — build os assets estáticos
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --frozen-lockfile || npm install
COPY . .
RUN npm run build

# Stage 2 — imagem mínima que publica o build no volume compartilhado.
# Caddy é quem realmente serve em produção; essa imagem só "deposita" os
# arquivos no volume nomeado `frontend_build` e fica viva pra Docker
# considerar o serviço UP.
#
# IMPORTANTE: os assets ficam baked em /build (NÃO em /srv/frontend). O volume
# nomeado é montado em /srv/frontend e o Docker só o semeia a partir da imagem
# quando ele está VAZIO (primeiro deploy) — em deploys seguintes o conteúdo
# antigo do volume sombreia os assets novos da imagem. Por isso copiamos
# /build -> /srv/frontend no start do container, sobrescrevendo o volume, pra
# que cada deploy publique de fato a versão nova.
FROM alpine:3.20
COPY --from=build /app/build /build
RUN mkdir -p /srv/frontend
CMD ["sh", "-c", "find /srv/frontend -mindepth 1 -delete 2>/dev/null; cp -a /build/. /srv/frontend/ && tail -f /dev/null"]
