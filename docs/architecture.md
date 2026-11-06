# Smart AgriTech Rover: Architecture Overview

The Smart AgriTech Rover system is built as a robust, decoupled platform connecting IoT agricultural hardware (Rovers) with farmers and administrators through a modern web interface.

## 1. High-Level Architecture

The system consists of three main components:
1. **Physical Rovers (IoT Nodes)**: Physical robots moving in the field, equipped with sensors, cameras, and spray nozzles. They connect to the backend API over cellular or Wi-Fi networks.
2. **Backend API (FastAPI)**: The central nervous system. It processes telemetry, schedules tasks, handles video analysis (mocked in this version but ready for ML integration), and enforces safety constraints.
3. **Frontend Application (Next.js)**: The farmer and admin interfaces for monitoring, manual control, and reporting.

## 2. Core Modules (Backend)

The backend is modularized to ensure easy maintenance and scalability:

- **`core/`**: Configuration, security (JWT, password hashing), and database connection.
- **`models.py`**: SQLAlchemy ORM models defining the database schema.
- **`schemas.py`**: Pydantic models for data validation (input/output).
- **`services/`**: Core business logic decoupled from HTTP handlers:
  - `communication.py`: Handles sending commands to physical rovers.
  - `safety.py`: The `SafetyRuleEngine` ensures that spraying only occurs under safe conditions (e.g., wind speed < 15km/h, human detection = false).
  - `video_analysis.py`: Stubbed service representing an edge ML pipeline that detects weeds or crop diseases.
- **`modules/`**: The HTTP routers organizing the API into `auth`, `farmer`, `admin`, and `rover` namespaces.

## 3. Security & Access Control

- **Authentication**: JWT (JSON Web Tokens) are used for all API access. Tokens expire automatically.
- **Role-Based Access Control (RBAC)**:
  - `ADMIN`: Has full system visibility and can manage users and global settings.
  - `FARMER`: Can only access data associated with their own `Farmer` ID (farms, crops, rovers, fields).
  - `ROVER`: IoT devices authenticate via hardware-specific tokens to push telemetry.
- **Data Isolation**: All farmer-facing endpoints in `modules/farmer/` are strictly filtered by `current_user.id` to prevent cross-tenant data access.

## 4. Frontend Design System

The frontend utilizes a consistent "Earthy" design system defined in `tailwind.config.js` and `globals.css`:
- **Colors**: Agri-Green (`#2D6A4F`), Terra (`#E76F51`), Harvest (`#F4A261`), Cream (`#FEFAE0`), Earth (`#DDA15E`).
- **Terminology**: Centralized in `src/constants/terminology.ts` (e.g., "Farmer", "Farm", "Rover") to guarantee consistent UX terminology across all pages without hardcoding.

## 5. Future Scalability

- **Database**: Currently configured for SQLite for ease of development, but fully compatible with PostgreSQL. Change `DATABASE_URL` in `.env` to switch to PostgreSQL.
- **WebSockets**: Real-time telemetry from rovers can be implemented via FastAPI WebSockets (stubbed in configuration).
- **AI/ML**: The `video_analysis.py` service can be connected directly to an inference server (like TensorFlow Serving or ONNX) for live crop health detection.
