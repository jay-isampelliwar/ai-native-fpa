```
app/
├── main.py
├── core/
│   ├── config.py
│   ├── exceptions.py
│   └── logging.py
├── db/
│   ├── session.py
│   └── migrations/
├── modules/
│   ├── conversations/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── repository.py
│   │   └── models.py
│   ├── messages/
│   │   ├── service.py
│   │   ├── repository.py
│   │   └── models.py
│   └── agent_runs/
│       ├── router.py
│       ├── schemas.py
│       ├── service.py
│       ├── repository.py
│       ├── models.py
│       └── graph.py
├── integrations/
│   ├── openai_client.py
│   └── redis_client.py
├── workers/
│   └── agent_worker.py
└── tests/
```