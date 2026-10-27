FROM node:20-slim AS base

WORKDIR /app
COPY package.json ./
RUN npm install

COPY . .
# 같은 도메인의 /api 경로로 API를 호출한다(프록시가 /api 를 FastAPI로 전달). 빌드 시점에 고정되는 값이다.
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
