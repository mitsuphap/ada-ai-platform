# ADA AI Platform

> Full-stack AI-powered web intelligence platform — search, scrape, and analyze web data using Google Gemini AI and Google Custom Search.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-ada--frontend.vercel.app-brightgreen)](https://ada-frontend.vercel.app/scraper)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-61DAFB?logo=react)](https://react.dev/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL-336791?logo=postgresql)](https://www.postgresql.org/)
[![AI](https://img.shields.io/badge/AI-Google%20Gemini-4285F4?logo=google)](https://deepmind.google/technologies/gemini/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker)](https://www.docker.com/)

---

## 🔗 Live Demo

| Service | URL |
|---------|-----|
| 🌐 Frontend | [ada-frontend.vercel.app/scraper](https://ada-frontend.vercel.app/scraper) |

---

## 📌 Overview

ADA AI Platform is a full-stack web application that lets users search topics via **Google Custom Search**, automatically scrape and extract structured data (people, organizations, emails), and generate **AI-powered insights** using **Google Gemini**. All results are persisted in a PostgreSQL database and exposed via a clean RESTful API.

Built as part of the **Applied Research Project (CSIS4495)** at Douglas College — Team IntelliBase (Fall 2025).

---

## ✨ Features

- 🔍 **Web Scraper** — Search any topic via Google CSE and extract structured data automatically
- 🤖 **AI-Powered Analysis** — Google Gemini analyzes scraped content and generates insights
- 👤 **Person & Organization Tracking** — Stores scraped entities (name, email, affiliation) in PostgreSQL
- 📡 **RESTful API** — FastAPI backend with auto-generated Swagger/OpenAPI docs
- ⚡ **Modern Frontend** — React + TypeScript SPA with responsive UI
- 🐳 **Containerized** — Full Docker + docker-compose support
- ☁️ **Cloud Deployed** — Frontend on Vercel, backend containerized with Fly.io config

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI, SQLAlchemy |
| Database | PostgreSQL |
| AI / Search | Google Gemini API, Google Custom Search API |
| Deployment | Vercel (frontend), Docker, Fly.io |

---

## 👩‍💻 My Contributions

This was a team project (IntelliBase, Team 2). My responsibilities:

- **Backend** — FastAPI app, REST endpoints, SQLAlchemy models, Pydantic schemas, AI integration with Google Gemini
- **Frontend** — React + TypeScript SPA, UI components, API integration
- **Deployment** — Dockerized the backend, deployed frontend to Vercel, configured Fly.io for backend hosting

Team breakdown:
- **Isaac** — Web scraping logic
- **Summer** — Database design & migrations

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL
- API Keys: `GEMINI_API_KEY`, `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX`

### 1. Clone the repository

```bash
git clone https://github.com/mitsuphap/ada-ai-platform
cd ada-ai-platform
```

### 2. Backend setup

```bash
cd Implementation/backend
cp .env.example .env
pip install -r requirements.txt
uvicorn main:app --reload
```

### 3. Frontend setup

```bash
cd Implementation/frontend
npm install
npm run dev
```

### 4. Docker (Full Stack)

```bash
docker-compose up --build
```

---

## ⚙️ Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GOOGLE_CSE_API_KEY` | Google Custom Search API key |
| `GOOGLE_CSE_CX` | Google CSE Context ID |
| `VITE_API_URL` | Backend API base URL (frontend) |

---

## 📁 Project Structure

```
├── Implementation/
│   ├── backend/               # FastAPI backend
│   │   ├── app/
│   │   │   ├── auto_generator.py  # AI-powered insight generation
│   │   │   ├── db.py              # Database models (SQLAlchemy)
│   │   │   └── schemas.py         # Pydantic schemas
│   │   ├── main.py
│   │   └── Dockerfile
│   ├── frontend/              # React + TypeScript SPA
│   └── scraper/               # Web scraping logic
├── docker-compose.yml
└── fly.toml
```

---

## 📄 License

MIT License
