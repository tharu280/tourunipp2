# reactui

Vite + React PWA for `tourunipp2`.

What it does:

- account creation and sign-in with a secure refresh cookie
- separate flight and trip intake stages
- flight selection, route planning, maps, crowd/weather/road views, and tips
- saved-session dashboard loading

How to run:

1. Start the backend from `/Users/dilshantharushika/Desktop/routemvp/tourunipp2`

```bash
JWT_SECRET="$(openssl rand -hex 32)" COOKIE_SECURE=false \
  uvicorn clean_run.api:app --host 127.0.0.1 --port 7860
```

2. Install frontend dependencies

```bash
cd /Users/dilshantharushika/Desktop/routemvp/tourunipp2/reactui
nvm use
npm install
```

3. Start the React dev server

```bash
npm run dev
```

4. Open:

`http://127.0.0.1:4173`

Default backend URL:

- `http://127.0.0.1:7860`

Set `VITE_API_BASE_URL=http://127.0.0.1:7860` for local development.

Production uses the same-origin `/api` path by default. `vercel.json` proxies that
path to Railway so mobile Safari treats the HTTP-only authentication cookie as a
first-party cookie. On Vercel, remove an old direct Railway value for
`VITE_API_BASE_URL` or set it exactly to `/api`, then redeploy.

Required Railway additions:

```text
JWT_SECRET=<output of openssl rand -hex 32>
COOKIE_SECURE=true
```

Do not set `COOKIE_DOMAIN`. Keep the existing MongoDB variables in Railway.

Build:

```bash
npm run build
```
