# 🍽️ Canteen Hub — Online Ordering & Table Reservation System

A production-ready full-stack web application for school/office canteens and restaurants featuring **online food ordering**, **table reservations**, **cashless wallet payments**, and an **administrative kitchen operations dashboard**.

Configured for cloud deployment using **Neon Serverless PostgreSQL**, **GitHub**, and **Render**.

---

## 🌟 Key Features

### 🛒 Customer Features (Students & Guests)
- **Interactive Food Menu**: Browse meals, snacks, drinks, and desserts with live search, category filters, prices, and prep time badges.
- **Online Food Ordering**: Order takeout for fast pickup or pre-order food directly linked to a dine-in table reservation.
- **Table Reservations**: Book a table by selecting reservation date, convenient time slots, party size (1–10+ guests), seating area (Main Dining, Patio, Window, Booth), and special dietary requests.
- **Cashless Digital Wallet**: In-app wallet balance with instant reload via simulated GCash, Maya, or Card.
- **Multiple Payment Methods**: Pay via In-App Wallet, GCash, Maya, or Cash on Pickup/Seating.
- **Live Order & Reservation Tracking**: Visual status trackers (Pending &rarr; Preparing &rarr; Ready &rarr; Completed).
- **Auto-Refund Protection**: If a pending order is cancelled, funds are instantly refunded to the customer's wallet.

### 🛡️ Administrative Features (Kitchen & Staff)
- **Executive Operations Dashboard**: Real-time stats for Total Revenue, Total Orders, Kitchen Queue, Active Reservations, and Registered Students.
- **Kitchen Order Management**: Real-time order dispatching and status transitions (`pending` &rarr; `preparing` &rarr; `ready` &rarr; `completed` &rarr; `cancelled`).
- **Table Reservation Management**: View incoming table requests, filter by date, confirm bookings, seat guests upon arrival, and track table occupancy.
- **Menu Management**: Add, edit, toggle visibility (show/hide), and delete dishes.
- **Student Wallet Management**: View student balances and credit/top-up funds manually.

---

## 🏗️ System Architecture

```mermaid
flowchart LR
    A[Customers & Students] -->|Browse Menu / Reserve Table / Checkout| B[Render Web Service\nFlask + Gunicorn]
    C[Admin & Kitchen Staff] -->|Manage Orders & Reservations| B
    B -->|DATABASE_URL\nSSL Mode Require| D[(Neon Cloud PostgreSQL\nServerless Database)]
    B -.->|Local Development Fallback| E[(SQLite Local File\ncanteen.db)]
```

---

## 🚀 Quick Local Run

### Windows (1-Click)
Double-click `start_windows.bat`. It will automatically configure the virtual environment, install requirements, and open your browser at `http://localhost:5000`.

### Mac / Linux
Open terminal in this directory and run:
```bash
chmod +x start_mac_linux.command
./start_mac_linux.command
```

### Manual Run
```bash
# 1. Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch Flask server
python app.py
```

---

## 🐘 Step 1: Set Up Neon Serverless PostgreSQL

1. Go to **[https://neon.tech](https://neon.tech)** and sign up for a free account (you can sign in with GitHub).
2. Click **Create Project**:
   - **Project name**: `canteen-db` (or any name)
   - **Postgres version**: `16` (default)
   - **Region**: Choose the region closest to you (e.g. `US East`, `Singapore`, etc.)
3. Once created, you will see your **Connection Details** on the Neon Dashboard.
4. Select **Connection string** (choose `psycopg2` or `PostgreSQL` from the dropdown).
5. Copy the connection string. It will look like:
   ```text
   postgresql://neondb_owner:YOUR_PASSWORD@ep-example-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
6. **That's it!** Canteen Hub will automatically create all tables and seed sample menu items and demo accounts the first time it connects to Neon.

---

## 🐙 Step 2: Push Project to GitHub

1. Open a terminal / command prompt inside this project folder:
   ```bash
   cd "C:\Users\Gabriel\OneDrive\Desktop\canteen_system\canteen_system"
   ```

2. Initialize Git and commit the code:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Online Ordering and Table Reservation System with Neon PostgreSQL & Render deployment"
   ```

3. Create a new repository on GitHub:
   - Go to **[https://github.com/new](https://github.com/new)**
   - Name your repository (e.g., `canteen-ordering-system`)
   - Keep it **Public** (or Private)
   - Do **NOT** check "Add a README" (we already have one)
   - Click **Create repository**

4. Link and push to GitHub:
   ```bash
   git branch -M main
   git remote add origin https://github.com/sshinichirochan/canteen-ordering-system.git
   git push -u origin main
   ```

---

## 🌐 Step 3: Deploy to Render

### Method A: 1-Click Blueprint Deploy (Recommended)
Because this repository includes `render.yaml`, Render can configure everything automatically:

1. Go to **[https://dashboard.render.com](https://dashboard.render.com)** and log in.
2. Click **New +** &rarr; **Blueprint**.
3. Select your GitHub repository (`canteen-ordering-system`).
4. Render will read `render.yaml` and prompt you for the `DATABASE_URL` environment variable:
   - Paste your **Neon PostgreSQL connection string** copied in Step 1.
5. Click **Apply**. Render will build and deploy your app with a live HTTPS URL!

---

### Method B: Manual Web Service Setup
1. On **Render Dashboard**, click **New +** &rarr; **Web Service**.
2. Connect your GitHub repository (`canteen-ordering-system`).
3. Set the following configuration:
   - **Name**: `canteen-ordering-system`
   - **Language**: `Python 3`
   - **Branch**: `main`
   - **Region**: Same region as your Neon database (or closest)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: `Free`
4. Expand **Environment Variables** and add:
   - `DATABASE_URL`: *(Paste your Neon connection string)*
   - `SECRET_KEY`: *(Enter any long random string or leave Render to generate)*
   - `PYTHON_VERSION`: `3.11.9`
5. Click **Create Web Service**.
6. Once deployed, Render will provide a live URL (e.g. `https://canteen-ordering-system.onrender.com`).

---

## 🔑 Demo Accounts

The database comes pre-seeded with two accounts for instant testing:

| Role | Email | Password | Initial Balance | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| **Admin** | `admin@canteen.com` | `admin123` | ₱0.00 | Manage Menu, Orders, Reservations, and Student Wallets |
| **Student** | `student@canteen.com` | `student123` | ₱500.00 | Browse Menu, Place Orders, Book Tables, Reload Wallet |

*Note: Any newly registered student account automatically receives a welcome balance of ₱100.00!*

---

## 🧪 Testing the Complete Workflow

1. **Table Reservation**:
   - Log in as `student@canteen.com`
   - Go to **Book a Table** &rarr; select Date, Time, 4 Guests, Seating Area (e.g. Patio)
   - Check "Pre-order food now for this reservation" &rarr; click **Confirm Table Reservation**.

2. **Online Pre-Order with Reservation**:
   - Add meals (e.g. Chicken Adobo, Sisig, Iced Tea) to your cart.
   - Go to **Cart** &rarr; select **🪑 Dine-in Table** &rarr; choose your confirmed reservation from the dropdown.
   - Choose **In-App Wallet** or **GCash (Simulated)** &rarr; click **Confirm & Place Order**.

3. **Admin Kitchen Operations**:
   - Log out, then log in as `admin@canteen.com`.
   - On the **Admin Dashboard**, view real-time statistics, the active reservation, and incoming orders.
   - Go to **All Orders** &rarr; change status to `preparing` &rarr; `ready` &rarr; `completed`.
   - Go to **Reservations** &rarr; mark table reservation as `confirmed` &rarr; `seated`.

---

## 📂 Project Structure

```text
canteen_system/
├── app.py                     # Flask application: models, routes, Neon & SQLite auto-setup
├── requirements.txt           # Python dependencies (Flask, SQLAlchemy, psycopg2, gunicorn)
├── render.yaml                # Infrastructure-as-Code blueprint for 1-click Render deployment
├── Procfile                   # Process file for Render production server (gunicorn app:app)
├── .env.example               # Template for environment variables (DATABASE_URL, SECRET_KEY)
├── .gitignore                 # Git ignore file (excludes venv, .env, *.db)
├── start_windows.bat          # 1-click launcher for Windows
├── start_mac_linux.command    # 1-click launcher for Mac/Linux
├── README.md                  # Complete documentation and setup guide
├── static/
│   └── style.css              # Custom styling, order tracker stepper, badges, animations
└── templates/
    ├── base.html              # Main layout, responsive navigation, and session status
    ├── menu.html              # Menu catalog, instant search, category filter pills, food cards
    ├── cart.html              # Shopping tray, takeout vs dine-in selector, payment options
    ├── reservations.html      # Table reservation booking form and customer reservation list
    ├── orders.html            # Customer order receipts and visual cooking stepper tracker
    ├── wallet.html            # Cashless balance card, preset top-up chips, simulated GCash/Maya
    ├── admin_dashboard.html   # Admin operational metrics, split orders & reservations view
    ├── admin_orders.html      # Kitchen order management with status dispatching & auto-refunds
    ├── admin_reservations.html# Table reservation manager (confirm, seat, complete)
    ├── admin_menu.html        # Menu CRUD: add dishes, toggle availability, edit prices
    ├── admin_users.html       # Student management and manual wallet credit
    ├── login.html             # Login form with 1-click demo account autofill
    └── register.html          # Registration form with ₱100 welcome credit
```

---

## 📄 License
This project is open-source and available under the **MIT License**.
