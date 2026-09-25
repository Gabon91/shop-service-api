# GitHub Copilot Master Instructions - 180-Min Technical Challenge

You are an expert AI pair programmer assisting a development team in building a full-stack mini e-commerce web application under a strict **180-minute time limit**. Speed, working features, and clean integration take absolute priority over over-engineering.

## Tech Stack & Architecture
- **Frontend:** React (Vite) + Tailwind CSS + Lucide Icons. Deployed to GitHub Pages.
- **Backend:** Python FastAPI. Deployed to a free cloud service (Render/Railway/Fly.io).
- **Database:** Supabase (PostgreSQL).
- **API Contract:** Strict OpenAPI 3.0 specification agreed upon by both frontend and backend developers.

---

## Core Engineering Principles for This Project

1. **Strict API Adherence:** 
   - Never alter endpoint paths, HTTP methods, or JSON payload structures without explicit instruction.
   - Maintain the agreed contract for products, customers, orders, and order status updates.

2. **Speed Over Perfection:**
   - Write clean, working code quickly. Avoid unnecessary abstractions, heavy state management libraries (use React built-in state/hooks), or complex design patterns.
   - If a feature is tricky, implement a simplified version that works end-to-end first.

3. **Database & Backend Rules (FastAPI + Supabase):**
   - Use the official `supabase-py` client or direct HTTP requests via `httpx`.
   - Implement automatic customer creation (Upsert logic by email) inside the `POST /api/orders` endpoint.
   - Ensure CORS is properly configured in FastAPI (`CORSMiddleware`) to allow requests from the frontend public URL.

4. **Frontend Rules (React + Tailwind):**
   - Keep components modular and readable (`ProductCatalog`, `CartDrawer`, `CheckoutForm`, `OrderHistory`, `BusinessDashboard`).
   - Use environment variables (`import.meta.env.VITE_API_BASE_URL`) for API calls, falling back gracefully to `http://localhost:3000`.
   - Handle loading and error states cleanly (e.g., simple spinners or error banners).

---

## Quick Reference: API Endpoints
- `GET /api/products?search=...` - Fetch products (with optional name filter).
- `GET /api/customers` - Fetch all registered customers (Business view).
- `GET /api/orders?customer_id=...` - Fetch orders (all for business, or filtered by customer).
- `POST /api/orders` - Create order + auto-create customer.
- `PATCH /api/orders/{id}/status` - Update order status (Pending/Completed/Cancelled).