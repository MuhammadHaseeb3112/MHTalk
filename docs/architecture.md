# System Architecture

```text
               Client Applications
                       │
       REST API / WebSocket Requests
                       │
        Django REST Framework APIs
                       │
              Business Logic Layer
                       │
      Chat | Calls | Status | Accounts
                       │
         Models • Serializers • Services
                       │
      SQLite/PostgreSQL        Redis
                       │
               Django Channels
                       │
             WebSocket Consumers
                       │
            Real-Time Communication
```