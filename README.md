# 💬 WhatsUp Backend

> **A production-ready real-time messaging and calling backend inspired by WhatsApp.**

A scalable backend built with **Django**, **Django REST Framework**, **Django Channels**, **Redis**, **WebSockets**, and **WebRTC Signaling**.

Designed using clean architecture principles to provide secure authentication, real-time messaging, media sharing, voice/video call signaling, and status updates.

---

<p align="center">

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Django](https://img.shields.io/badge/Django-5.x-darkgreen?logo=django)
![DRF](https://img.shields.io/badge/Django_REST_Framework-API-red)
![Redis](https://img.shields.io/badge/Redis-Channel_Layer-red?logo=redis)
![WebSocket](https://img.shields.io/badge/WebSocket-Real_Time-success)
![JWT](https://img.shields.io/badge/JWT-Authentication-orange)
![OpenAPI](https://img.shields.io/badge/OpenAPI-Swagger-success)
![License](https://img.shields.io/badge/License-MIT-brightgreen)
![Status](https://img.shields.io/badge/Status-Production_Ready-success)

</p>

---

## 🌟 Why WhatsUp Backend?

Modern messaging applications require much more than simple CRUD APIs. This project demonstrates how to build a scalable backend capable of handling:

- 💬 Real-Time Messaging
- 📞 Audio & Video Call Signaling
- 📸 WhatsApp-style Status Updates
- 👥 Group Conversations
- 📂 Media Sharing
- 🔐 Secure JWT Authentication
- ⚡ WebSocket Communication
- 📖 Fully Documented REST APIs (Swagger/OpenAPI)

Whether you're learning Django Channels, building a messaging platform, or exploring WebRTC signaling, this project provides a solid foundation.

# 📑 Table of Contents

- [📖 Overview](#-overview)
- [🚀 Project Highlights](#-project-highlights)
- [✨ Features](#-features)
- [🛠 Technology Stack](#-technology-stack)
- [🏗 System Architecture](#-system-architecture)
- [📁 Project Structure](#-project-structure)
- [⚙ Installation](#-installation)
- [🐳 Docker Setup](#-docker-setup)
- [🔑 Environment Variables](#-environment-variables)
- [🗄 Database Migration](#-database-migration)
- [🚀 Running the Project](#-running-the-project)
- [📖 API Documentation](#-api-documentation)
- [📸 Swagger Preview](#-swagger-preview)
- [🔐 Authentication](#-authentication)
- [📡 WebSocket Endpoints](#-websocket-endpoints)
- [📚 API Examples](#-api-examples)
- [💬 Chat Flow](#-chat-flow)
- [📞 Call Flow](#-call-flow)
- [📊 API Modules](#-api-modules)
- [🧪 Testing](#-testing)
- [⚙ CI/CD](#-cicd)
- [🛣 Roadmap](#-roadmap)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)
- [👨‍💻 Author](#-author)


# 📖 Overview

**WhatsUp Backend** is a production-ready backend application inspired by the architecture of modern messaging platforms such as **WhatsApp**.

It combines REST APIs with WebSocket communication to deliver secure, scalable, and real-time messaging experiences.

The backend supports:

- 🔐 Secure JWT Authentication
- 💬 One-to-One Messaging
- 👥 Group Messaging
- 📂 Media Sharing
- 📸 Status Updates
- 📞 Audio & Video Call Signaling
- ⚡ Real-Time Notifications
- 📖 Interactive Swagger Documentation

The project is designed using Django best practices, making it suitable for both learning purposes and real-world applications.


# 🚀 Project Highlights

| Feature | Status |
|----------|:------:|
| 🔐 JWT Authentication | ✅ |
| 💬 Private Chat | ✅ |
| 👥 Group Chat | ✅ |
| 📂 Media Upload | ✅ |
| 🎤 Voice Notes | ✅ |
| 📸 Status Sharing | ✅ |
| 📞 Audio Calling | ✅ |
| 🎥 Video Calling | ✅ |
| ⚡ WebSocket Communication | ✅ |
| 📖 Swagger Documentation | ✅ |
| 🐳 Docker Support | ✅ |
| 🔄 Redis Channel Layer | ✅ |
| 📡 WebRTC Signaling | ✅ |
| 📚 OpenAPI Schema | ✅ |
| 🏗 Clean Architecture | ✅ |



# ✨ Features

## 🔐 Authentication

- ✅ User Registration
- ✅ Login & Logout
- ✅ JWT Authentication
- ✅ User Profile
- ✅ Profile Update

---

## 💬 Messaging

- ✅ Private Conversations
- ✅ Group Conversations
- ✅ Reply Messages
- ✅ Forward Messages
- ✅ Search Messages
- ✅ Message Reactions
- ✅ Pin Messages
- ✅ Star Messages
- ✅ Archive Chats
- ✅ Mute Chats
- ✅ Delete for Me
- ✅ Delete for Everyone

---

## 👥 Group Management

- ✅ Create Group
- ✅ Add Participants
- ✅ Remove Participants
- ✅ Leave Group
- ✅ Admin Management

---

## 📂 Media Sharing

- ✅ Images
- ✅ Videos
- ✅ Documents
- ✅ Audio Files
- ✅ Voice Notes
- ✅ Multiple Attachments

---

## 📸 Status

- ✅ Upload Status
- ✅ Image Status
- ✅ Video Status
- ✅ Status Privacy
- ✅ Status Viewers
- ✅ Delete Status

---

## 📞 Calls

- ✅ Audio Calls
- ✅ Video Calls
- ✅ Busy Detection
- ✅ Hold Call
- ✅ Resume Call
- ✅ Call History
- ✅ Missed Calls
- ✅ Screen Sharing Signaling
- ✅ Camera Toggle Events
- ✅ WebRTC Signaling

---

## ⚡ Real-Time

- ✅ Django Channels
- ✅ Redis Channel Layer
- ✅ WebSocket Messaging
- ✅ Live Typing Indicators
- ✅ Read Receipts
- ✅ Delivery Receipts
- ✅ Presence Updates
- ✅ Call Events


# 🛠 Technology Stack

The project is built using modern backend technologies that enable secure authentication, scalable APIs, real-time communication, and production-ready deployment.

| Technology | Purpose |
|------------|---------|
| 🐍 Python 3.12 | Programming Language |
| 🌐 Django | Backend Web Framework |
| 🚀 Django REST Framework | REST API Development |
| ⚡ Django Channels | WebSocket Support |
| 🔴 Redis | Channel Layer & Real-Time Communication |
| 🗄 PostgreSQL / SQLite | Database |
| 🔐 JWT (Simple JWT) | Authentication |
| 📖 drf-spectacular | OpenAPI & Swagger Documentation |
| 📡 WebRTC | Audio & Video Call Signaling |
| 🐳 Docker | Containerization |
| 🔄 GitHub Actions | Continuous Integration (CI) |

---

# 🏗 System Architecture

The backend follows a layered architecture that separates business logic, data access, and communication layers to improve maintainability and scalability.

```text
                        ┌────────────────────────────┐
                        │     Client Applications    │
                        │ Flutter • React • Next.js │
                        │ Android • iOS • Web       │
                        └──────────────┬─────────────┘
                                       │
                          REST API / WebSocket
                                       │
                  ┌────────────────────┴────────────────────┐
                  │                                         │
          Django REST Framework                    Django Channels
                  │                                         │
                  └────────────────────┬────────────────────┘
                                       │
                           Business Logic Layer
                                       │
      ┌────────────────────────────────┼──────────────────────────────┐
      │                                │                              │
 Accounts Module                 Chat Module                  Calls Module
      │                                │                              │
      └────────────────────────────────┼──────────────────────────────┘
                                       │
                               Status Module
                                       │
                                       ▼
                         Django Models & ORM Layer
                                       │
                    ┌──────────────────┴─────────────────┐
                    │                                    │
            PostgreSQL / SQLite                     Redis
                    │                                    │
                    └──────────────────┬─────────────────┘
                                       │
                           Real-Time Communication
```

---

# 📁 Project Structure

```text
WhatsUp-Backend/
│
├── apps/
│   ├── accounts/              # Authentication & Profiles
│   ├── chat/                  # Messaging System
│   ├── calls/                 # Audio & Video Calls
│   └── status/                # WhatsApp Status Module
│
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   │
│   ├── asgi.py
│   ├── urls.py
│   └── wsgi.py
│
├── docs/
│   ├── architecture.md
│   ├── sequence.md
│   └── swagger.png
│
├── docker/
│
├── media/
├── static/
├── tests/
├── scripts/
│
├── .github/
│   └── workflows/
│       └── django.yml
│
├── .dockerignore
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── manage.py
├── README.md
└── requirements.txt
```

---

# ⚙ Installation

## 1️⃣ Clone the Repository

```bash
git clone https://github.com/MuhammadHaseeb3112/WhatsUp-Backend.git

cd WhatsUp-Backend
```

---

## 2️⃣ Create a Virtual Environment

```bash
python -m venv venv
```

---

## 3️⃣ Activate the Virtual Environment

### Windows

```bash
venv\Scripts\activate
```

### Linux / macOS

```bash
source venv/bin/activate
```

---

## 4️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

# 🔑 Environment Variables

Create a `.env` file in the project root.

Example:

```env
SECRET_KEY=your_secret_key

DEBUG=True

ALLOWED_HOSTS=127.0.0.1,localhost

DATABASE_URL=sqlite:///db.sqlite3

REDIS_URL=redis://127.0.0.1:6379

ACCESS_TOKEN_LIFETIME=30

REFRESH_TOKEN_LIFETIME=7
```

You can also copy the sample configuration:

```bash
cp .env.example .env
```

---

# 🗄 Database Migration

Create the database tables.

```bash
python manage.py makemigrations

python manage.py migrate
```

Create an administrator account.

```bash
python manage.py createsuperuser
```

---

# 🚀 Running the Development Server

Start the Django development server.

```bash
python manage.py runserver
```

Your backend will be available at:

```
http://127.0.0.1:8000/
```

---

# 🔴 Running Redis

Start the Redis server before using WebSocket functionality.

```bash
redis-server
```

Redis is used for:

- ⚡ Django Channels
- 📡 WebSocket Communication
- 🔄 Real-Time Events
- 📞 Call Signaling

---

# 🐳 Docker Setup

The project includes Docker support for easy local development.

### Build the containers

```bash
docker compose build
```

### Start all services

```bash
docker compose up
```

Or build and start everything with one command:

```bash
docker compose up --build
```

Run in detached mode:

```bash
docker compose up -d
```

Stop all services:

```bash
docker compose down
```

---

### Docker Services

| Service | Description |
|----------|-------------|
| Django | Backend API |
| Redis | Channel Layer |
| PostgreSQL *(optional)* | Production Database |

After the containers start successfully, open:

```
http://127.0.0.1:8000/
```

to access the application.


# 📖 API Documentation

The backend exposes a fully documented REST API using **drf-spectacular (OpenAPI 3.0)**.

Interactive API documentation makes it easy to explore, test, and integrate every endpoint.

## 🌐 Swagger UI

```
http://127.0.0.1:8000/api/docs/
```

## 📄 OpenAPI Schema

```
http://127.0.0.1:8000/api/schema/
```

---

## 📖 Swagger UI

### API Overview

![Swagger](docs/images/swagger-home.png)

---

### Accounts APIs

![Accounts](docs/images/swagger-accounts.png)

---

### Chat APIs

![Chat](docs/images/swagger-chat.png)

# 🔐 Authentication

The API uses **JWT (JSON Web Token)** authentication.

After a successful login, the backend returns:

- Access Token
- Refresh Token

Include the access token in every authenticated request.

```http
Authorization: Bearer <access_token>
```

Example:

```http
GET /api/accounts/me/

Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

---

# 📡 WebSocket Endpoints

Real-time communication is handled using **Django Channels** and **Redis**.

## 💬 Chat WebSocket

```text
ws://127.0.0.1:8000/ws/chat/<room_id>/
```

Used for:

- Live Messages
- Typing Indicators
- Read Receipts
- Delivery Receipts
- Presence Updates

---

## 📞 Call WebSocket

```text
ws://127.0.0.1:8000/ws/calls/<call_id>/
```

Used for:

- Incoming Calls
- Accept / Reject
- ICE Candidates
- SDP Offer / Answer
- Hold / Resume
- Screen Share Events
- Camera Toggle
- Call End Events

---

# 📚 API Examples

## 👤 Register User

### Request

```http
POST /api/accounts/register/
```

```json
{
  "phone_number": "+923001234567",
  "password": "StrongPassword123",
  "first_name": "Muhammad",
  "last_name": "Haseeb"
}
```

### Response

```json
{
  "message": "User registered successfully.",
  "user": {
    "id": 1,
    "phone_number": "+923001234567",
    "first_name": "Muhammad",
    "last_name": "Haseeb"
  }
}
```

---

## 🔑 Login

### Request

```http
POST /api/accounts/login/
```

```json
{
  "phone_number": "+923001234567",
  "password": "StrongPassword123"
}
```

### Response

```json
{
  "access": "eyJhbGciOi...",
  "refresh": "eyJhbGciOi...",
  "user": {
    "id": 1,
    "phone_number": "+923001234567"
  }
}
```

---

## 💬 Send Message

### Request

```http
POST /api/chat/messages/
```

```json
{
  "room": 12,
  "content": "Hello World!"
}
```

### Response

```json
{
  "message": "Message sent successfully.",
  "data": {
    "id": 145,
    "content": "Hello World!",
    "sender": {
      "id": 1
    },
    "created_at": "2026-07-07T14:30:00Z"
  }
}
```

---

## 📞 Start Call

### Request

```http
POST /api/calls/start/
```

```json
{
  "room": 12,
  "call_type": "video"
}
```

### Response

```json
{
  "id": 5,
  "status": "ringing",
  "call_type": "video",
  "started_at": "2026-07-07T15:20:00Z"
}
```

---

# 💬 Chat Message Flow

```mermaid
sequenceDiagram

participant User A
participant Backend
participant Redis
participant User B

User A->>Backend: Send Message
Backend->>Redis: Publish Event
Redis->>User B: WebSocket Message
Backend-->>User A: Success Response
```

---

# 📞 Call Flow

```mermaid
sequenceDiagram

participant Caller
participant Backend
participant Redis
participant Receiver

Caller->>Backend: Start Call API
Backend->>Redis: Broadcast Incoming Call
Redis->>Receiver: Ringing Event
Receiver->>Backend: Accept Call
Backend->>Caller: Call Accepted
Caller->>Receiver: WebRTC Offer
Receiver->>Caller: WebRTC Answer
Caller->>Receiver: ICE Candidates
Receiver->>Caller: ICE Candidates
Note over Caller,Receiver: Media Connection Established
Caller->>Backend: End Call
Backend->>Redis: Broadcast End Event
```

---

# 🏛 Project Documentation

The repository contains additional documentation inside the **docs/** directory.

| Document | Description |
|----------|-------------|
| architecture.md | Overall Backend Architecture |
| sequence.md | Chat & Call Sequence Diagrams |
| swagger.png | Swagger UI Screenshot |
| api_examples.md *(optional)* | REST API Examples |
| deployment.md *(optional)* | Deployment Guide |

---

# 📊 API Modules

| Module | Description |
|----------|-------------|
| 🔐 Accounts | Registration, Login, JWT Authentication, User Profile |
| 💬 Chat | Private Chat, Groups, Media, Search, Reactions |
| 📞 Calls | Audio/Video Call Signaling, Hold, Resume, History |
| 📸 Status | WhatsApp-style Status Sharing & Privacy |


# 🧪 Testing

The project is structured to support automated testing using Django's built-in testing framework.

Run all tests:

```bash
python manage.py test
```

Run tests with verbose output:

```bash
python manage.py test -v 2
```

Future improvements include:

- ✅ Unit Tests
- ✅ Integration Tests
- ✅ API Tests
- ✅ WebSocket Tests
- ✅ Performance Tests

---

# ⚙ Continuous Integration (CI)

GitHub Actions is used to automatically verify the project on every push and pull request.

The CI pipeline performs:

- ✅ Install Dependencies
- ✅ Run Django Checks
- ✅ Apply Database Migrations
- ✅ Execute Test Suite
- ✅ Verify Build

Workflow location:

```text
.github/
└── workflows/
    └── django.yml
```

---

# 🐳 Docker Deployment

The project supports containerized deployment using Docker and Docker Compose.

## Build Containers

```bash
docker compose build
```

---

## Start Services

```bash
docker compose up
```

---

## Build & Start

```bash
docker compose up --build
```

---

## Run in Background

```bash
docker compose up -d
```

---

## Stop Services

```bash
docker compose down
```

---

### Docker Services

| Service | Purpose |
|----------|---------|
| Django | REST API & WebSockets |
| Redis | Channel Layer |
| PostgreSQL *(optional)* | Production Database |

---

# 🚀 Deployment

The backend is deployment-ready and can be hosted on:

- Render
- Railway
- DigitalOcean
- AWS EC2
- Microsoft Azure
- Google Cloud Platform
- Docker VPS
- Ubuntu Server
- Nginx + Gunicorn

Recommended production stack:

```text
Client

↓

Nginx

↓

Gunicorn

↓

Django

↓

Redis

↓

PostgreSQL
```

---

# 🔒 Security Features

The project follows modern backend security practices.

### Authentication

- ✅ JWT Authentication
- ✅ Refresh Tokens
- ✅ Token Blacklisting

### Authorization

- ✅ Permission-Based Access
- ✅ Participant Validation
- ✅ Ownership Validation

### API Security

- ✅ Serializer Validation
- ✅ Input Sanitization
- ✅ Authentication Middleware
- ✅ Protected Endpoints

### Communication

- ✅ WebSocket Authentication
- ✅ Secure Call Signaling
- ✅ Protected Media Access

---

# 📈 Performance & Scalability

The backend is designed with scalability in mind.

### Optimizations

- ✅ select_related()
- ✅ prefetch_related()
- ✅ Database Indexing
- ✅ Redis Channel Layer
- ✅ Asynchronous WebSockets
- ✅ Modular Django Apps

### Supports

- Multiple Concurrent Users
- Real-Time Messaging
- Real-Time Calls
- Efficient Database Queries
- Horizontal Scaling

---

# 📊 Project Statistics

| Metric | Value |
|---------|------:|
| Django Apps | 4 |
| REST APIs | 30+ |
| WebSocket Consumers | 2 |
| Authentication | JWT |
| Real-Time Features | 10+ |
| Media Types | 5 |
| Swagger Documentation | ✅ |
| Docker Support | ✅ |
| CI/CD Ready | ✅ |

---

# 🛣 Roadmap

Planned future enhancements include:

- 🔔 Firebase Push Notifications
- 🌍 STUN/TURN Server Integration
- 👥 Group Audio Calling
- 🎥 Group Video Calling
- 📹 Call Recording
- 📈 Call Quality Metrics
- 🔄 Automatic Reconnection Handling
- 🔒 End-to-End Encryption
- 🤖 AI Spam Detection
- ☁ Cloud Storage Integration
- 📱 Flutter Mobile Client
- 🌐 React / Next.js Frontend
- 📊 Admin Analytics Dashboard

---

# 🤝 Contributing

Contributions are welcome!

If you'd like to improve this project:

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature/new-feature
```

3. Commit your changes

```bash
git commit -m "Add new feature"
```

4. Push your branch

```bash
git push origin feature/new-feature
```

5. Open a Pull Request

Please ensure your code follows Django best practices and includes appropriate tests where applicable.

---

# 📄 License

This project is licensed under the **MIT License**.

See the `LICENSE` file for more information.

---

# 👨‍💻 Author

## Muhammad Haseeb

**BS Computer Science**

Backend Developer | Python Developer | Django Developer

### Technical Skills

- 🐍 Python
- 🌐 Django
- 🚀 Django REST Framework
- ⚡ Django Channels
- 🔴 Redis
- 📡 WebSockets
- 📞 WebRTC Signaling
- 🗄 PostgreSQL
- 🐳 Docker
- 🔄 GitHub Actions

### Connect

**GitHub**

```
https://github.com/MuhammadHaseeb3112
```

---

# ⭐ Support the Project

If you found this project useful:

⭐ Star the repository

🍴 Fork the project

🐞 Report issues

💡 Suggest new features

📢 Share it with others

Your support helps improve the project and motivates future development.

---

<p align="center">

Made with ❤️ using Django, Django REST Framework, Django Channels, Redis & WebRTC.

</p>