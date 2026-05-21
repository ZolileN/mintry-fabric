FROM node:22-slim AS dashboard-builder

WORKDIR /app/apps/dashboard

COPY apps/dashboard/package.json apps/dashboard/package-lock.json ./
RUN npm ci

COPY apps/dashboard/ ./
RUN npm run build

FROM node:22-slim AS node-runtime

FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1
ENV MINTRY_JSON_LOGS=1
ENV MINTRY_DASHBOARD_API_ORIGIN=http://127.0.0.1:8000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV MINTRY_DB_PATH=/root/.mintry/vouchers.db

WORKDIR /app

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

COPY --from=dashboard-builder /app/apps/dashboard/.next/standalone ./dashboard
COPY --from=dashboard-builder /app/apps/dashboard/.next/static ./dashboard/.next/static
COPY --from=dashboard-builder /app/apps/dashboard/public ./dashboard/public

COPY scripts/start-dashboard-runtime.sh /app/scripts/start-dashboard-runtime.sh
RUN chmod +x /app/scripts/start-dashboard-runtime.sh

EXPOSE 3000

ENTRYPOINT ["/app/scripts/start-dashboard-runtime.sh"]
