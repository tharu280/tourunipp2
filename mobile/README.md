# TourUni Mobile

React Native / Expo mobile client for the `clean_run` FastAPI backend.

## Run

```bash
source ~/.nvm/nvm.sh
nvm use 22
npm install
npm run android
```

The app defaults to:

```text
https://tourismproject-backendtouruni.hf.space
```

Override it with:

```bash
EXPO_PUBLIC_API_BASE_URL=http://YOUR_BACKEND_URL npm run android
```
