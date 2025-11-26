# Publishing Industry Data Intelligence Platform Frontend

A flexible, dynamic frontend for the auto-generated API backend. This React application automatically adapts to schema changes and displays data from any table in your database.

## Tech Stack

- **Build Tool**: Vite
- **Framework**: React 18
- **Routing**: React Router v6
- **Data Fetching**: TanStack Query (React Query)
- **UI**: Tailwind CSS
- **HTTP Client**: Axios

## Features

- ✅ **Dynamic Table Discovery**: Automatically detects available tables from auto-generated API endpoints
- ✅ **Flexible Column Display**: Automatically renders all columns from API responses
- ✅ **Schema-Agnostic**: Adapts automatically when tables or columns change
- ✅ **Search & Pagination**: Built-in search and pagination controls
- ✅ **Clean UI**: Simple, modern design with Tailwind CSS
- ✅ **TypeScript**: Fully type-safe codebase

## Setup Instructions

1. **Install Dependencies**
   ```bash
   cd Implementation/frontend
   npm install
   ```

2. **Configure API URL** (optional)
   
   Create a `.env` file in the frontend directory:
   ```
   VITE_API_BASE_URL=http://localhost:8000
   ```
   
   Or modify `src/lib/axios.ts` if you need a different default.

3. **Start Development Server**
   ```bash
   npm run dev
   ```
   
   The frontend will be available at `http://localhost:3000`

4. **Build for Production**
   ```bash
   npm run build
   ```

## Usage

1. **Start the Backend API** (if not already running)
   ```bash
   cd Implementation/backend
   docker-compose up -d
   ```

2. **Access the Frontend**
   - Open `http://localhost:3000` in your browser
   - The dashboard will show all available tables
   - Click on any table to view its data

3. **View Table Data**
   - Navigate to any table to see all records
   - Use the search bar to filter results
   - Use pagination controls to navigate through pages

## Project Structure

```
frontend/
├── src/
│   ├── components/      # Reusable components
│   │   ├── Layout.tsx   # Main layout wrapper
│   │   ├── Dashboard.tsx # Table selection dashboard
│   │   └── DataTable.tsx # Dynamic data table component
│   ├── pages/           # Page components
│   │   ├── Home.tsx     # Home page (shows dashboard)
│   │   └── TableDetail.tsx # Individual table view
│   ├── hooks/           # Custom React hooks
│   │   └── useAutoTable.ts # Hook for fetching table data
│   ├── lib/             # Utility functions
│   │   ├── axios.ts     # Axios instance
│   │   └── utils.ts     # Helper functions
│   ├── types/           # TypeScript type definitions
│   │   └── api.ts       # API response types
│   ├── App.tsx          # Main app component
│   └── main.tsx         # Entry point
├── package.json
├── vite.config.js
└── tailwind.config.js
```

## How It Works

1. **Table Discovery**: On the home page, the app tries to connect to known table endpoints (`/auto/publishers`, `/auto/agents`, etc.) and shows only those that exist.

2. **Dynamic Rendering**: When viewing a table, the component:
   - Fetches data from `/auto/{tableName}`
   - Extracts column names from the first item
   - Renders a table with all columns automatically
   - Handles pagination and search

3. **Schema Flexibility**: Since the frontend dynamically reads column names from API responses, any schema changes in the backend are immediately reflected in the UI without code changes.

## Troubleshooting

**Frontend can't connect to API**
- Make sure the backend is running: `docker-compose up -d` in the backend directory
- Check that the API is accessible at `http://localhost:8000`
- Verify CORS is enabled in the backend (should already be configured)

**No tables showing**
- Ensure the backend API is running and healthy
- Check browser console for errors
- Verify `/health` endpoint returns success

**Build errors**
- Make sure all dependencies are installed: `npm install`
- Check Node.js version (requires Node 18+)
- Clear cache: `rm -rf node_modules package-lock.json && npm install`

