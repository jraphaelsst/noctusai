FROM node:18-alpine AS build

WORKDIR /app

COPY products/core/frontend/package*.json ./
RUN npm ci

COPY products/core/frontend/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY products/core/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5173

CMD ["nginx", "-g", "daemon off;"]
