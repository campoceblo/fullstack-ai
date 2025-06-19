# ---------- Build Stage ----------
FROM node:18-bullseye AS build-stage

WORKDIR /app
RUN rm -rf node_modules/
# 1. Install dependencies
COPY package*.json ./
RUN chmod -R 777 /home/node
RUN npm install
RUN chmod -R 777 /home/node
# 2. Fix permission for vue-cli-service


# 3. Copy source code
COPY . .

# 4. Build
RUN npm run build -- --skip-plugins @vue/cli-plugin-eslint

# ---------- Production Stage ----------
FROM nginx:stable-alpine AS production-stage

COPY --from=build-stage /app/dist /usr/share/nginx/html

# Add custom nginx config to allow large uploads
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
