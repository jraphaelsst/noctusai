# Backend — Corretor Goal Hub API

FastAPI backend for the Corretor Goal Hub platform.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Environment Variables

Copy `.env.example` to `.env` and fill in your Supabase credentials:

```bash
cp .env.example .env
```

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py             # Environment configuration
│   ├── database.py           # Supabase/PostgreSQL connection
│   ├── routers/
│   │   └── matching.py       # /api/matching endpoints
│   ├── services/
│   │   └── matching.py       # Matching algorithm (business logic)
│   └── schemas/
│       └── matching.py       # Pydantic request/response models
├── requirements.txt
├── .env.example
└── README.md
```
