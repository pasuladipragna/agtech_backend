# Deploying AgriTech on Render

The backend and frontend are separate repositories, so deploy them as separate Render Blueprints using their respective `render.yaml` files.

## Backend

1. Push the backend repository, including `render.yaml`, to GitHub.
2. In Render, choose **New +** then **Blueprint**, select the backend repository, and sync the blueprint.
3. The blueprint creates the `agtech-backend` web service. Set its private `DATABASE_URL` environment variable to the Supabase **Session Pooler** connection string (IPv4-compatible), replacing the password placeholder with the database password. Avoid the direct `db.<project-ref>.supabase.co:5432` endpoint when it resolves to IPv6, which may be unreachable from Render. The service uses a generated `SECRET_KEY` and the frontend's default Render origin in `CORS_ORIGINS`.
4. Wait for the service health check at `/health` to pass. The API docs will be at `https://agtech-backend.onrender.com/docs`.
5. Create the first administrator from the service's Shell with `python create_admin.py`. Choose a strong password that meets the script's requirements; do not use demo credentials.

The blueprint uses a paid Starter web-service plan. Review Render's current pricing before syncing it. If you change the service hostname or use a custom domain, update the backend `CORS_ORIGINS` value to a JSON array containing the exact frontend origin, for example `["https://app.example.com"]`.

## Frontend

1. Push the frontend repository, including its `render.yaml`, to GitHub.
2. In Render, create a second Blueprint from the frontend repository and sync it.
3. Verify `NEXT_PUBLIC_API_URL` is `https://agtech-backend.onrender.com/api/v1`. This is a public build-time setting, not a secret. If the backend hostname differs, update it and redeploy the frontend.
4. Open `https://agtech-frontend.onrender.com`, register/log in, and verify browser requests reach the backend without CORS errors.

For custom domains, set the frontend origin in the backend's `CORS_ORIGINS` environment variable and the backend API URL in the frontend's `NEXT_PUBLIC_API_URL`, then redeploy both services.

## Optional Integrations

- Configure Cloudinary credentials (`CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET`) for persistent image storage. Render's service filesystem is not a durable upload store by default.
- Configure a reachable MQTT broker and its credentials before connecting physical rovers. With no broker, the API can start, but hardware commands cannot reach a rover.
- Configure SMTP, SMS, Telegram, or OpenRouter credentials only when those integrations are enabled. Keep all private credentials in Render environment variables, never in the frontend.
- `database/seed.py` is for optional demo data only. It requires `SEED_ADMIN_PASSWORD` and `SEED_FARMER_PASSWORD`, is idempotent, and does not clear existing records. For a real deployment, create the admin with `create_admin.py` instead.

## Deployment Checks

- Backend: `https://agtech-backend.onrender.com/health` returns `{"status":"healthy"}`.
- Backend docs: `https://agtech-backend.onrender.com/docs` loads.
- Frontend: the home, login, registration, farmer, and admin routes return successfully.
- Browser developer tools show no failed API calls or CORS errors after login.
