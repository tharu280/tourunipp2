# reactui

Proper Vite + React frontend for `tourunipp2`.

What it does:

- talks to the backend `POST /chat` endpoint
- keeps the returned session state between turns
- shows missing fields live
- shows a structured session table while the planner collects data

How to run:

1. Start the backend from `/Users/dilshantharushika/Desktop/routemvp/tourunipp2`

```bash
python3 api.py
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

You can change the API base URL in the UI itself if needed.

Build:

```bash
npm run build
```
