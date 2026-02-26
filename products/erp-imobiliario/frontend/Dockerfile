FROM node:18-alpine AS build

WORKDIR /app

COPY products/erp-imobiliario/frontend/package*.json ./
RUN npm ci

COPY products/erp-imobiliario/frontend/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY products/erp-imobiliario/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
