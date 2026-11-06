# Smart AgriTech Rover System

A comprehensive software platform for managing agricultural robots, fields, crop health, and precision spraying. Designed with a robust modular architecture that is ready for hardware integration.

## Project Structure

The project is divided into a modern frontend web application and a secure backend API.

- `agtech_frontend/`: Next.js web application using React and Tailwind CSS.
- `agtech_backend/`: FastAPI Python application with SQLAlchemy and JWT authentication.
- `docs/`: System architecture and hardware integration documentation.

## Getting Started

### 1. Database & Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd agtech_backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/Mac:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create an environment file:
   Copy `.env.example` to `.env` and adjust settings as needed.
5. Create the database and admin user:
   ```bash
   python create_admin.py
   ```
6. Start the API server:
   ```bash
   uvicorn main:app --reload
   ```

### 2. Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd agtech_frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Create an environment file:
   Copy `.env.example` to `.env.local`
4. Start the development server:
   ```bash
   npm run dev
   ```

### 3. Accessing the Application

- **Web App**: http://localhost:3000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **API Docs (ReDoc)**: http://localhost:8000/redoc

**Default Admin Credentials**:
- Email: `admin@agtech.com`
- Password: `admin123`

## Key Features

- **Farmer Dashboard**: Real-time metrics on crop health, active sprayers, alerts, and field conditions.
- **Admin Dashboard**: System-wide statistics, registration approvals, and hardware (Rover) management.
- **Hardware Ready**: A structured Rover API allows physical hardware units to check-in, receive spraying instructions, and report safety faults.
- **Security**: JWT-based authentication, Role-Based Access Control (RBAC), and full data isolation between farmers.

## Documentation

For a deeper dive into how the system works and how to connect physical hardware, please see the documentation in the `docs/` folder:

- [Architecture Overview](docs/architecture.md)
- [Hardware Integration Guide](docs/rover-integration.md)
