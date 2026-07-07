# Message Flow

```text
User A

   │

POST /messages/

   │

Django REST API

   │

Save Message

   │

Redis Channel Layer

   │

WebSocket Consumer

   │

Broadcast

   │

User B Receives Message
```

---

# Call Flow

```text
Caller

 │

POST /api/calls/start/

 │

Call Created

 │

Incoming Call Event

 │

WebSocket Broadcast

 │

Receiver Accepts

 │

POST /api/calls/{id}/accept/

 │

Call Status → Ongoing

 │

WebRTC Offer / Answer

 │

ICE Candidates Exchange

 │

Media Connected

 │

POST /api/calls/{id}/end/

 │

Call Ended

 │

Call History Saved
```