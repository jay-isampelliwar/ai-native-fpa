# Frontend

Next.js 16, React 19, TypeScript and Tailwind CSS 4. The architecture is explained in the [root README](../README.md).

## Run

```bash
pnpm install
pnpm dev
```

Open http://localhost:3000. The backend must be running on port 8000, or set `BACKEND_ORIGIN`.

## How it talks to the backend

- The browser calls `/api/*` on its own origin. [next.config.ts](next.config.ts) rewrites those calls to the backend, so there is no CORS.
- [lib/api.ts](lib/api.ts) is the typed client for every route.
- [lib/stream.ts](lib/stream.ts) reads a run's server-sent events. It keeps the last event id and reconnects with `?after=`, so a dropped connection loses nothing.
- [lib/types.ts](lib/types.ts) holds the event and UI block types. They must change together with the backend's `features/runs/events.py` and `agent/blocks.py`.

## Main parts

| Folder | Holds |
|---|---|
| [components/chat](components/chat) | The chat workspace, message timeline, composer, approval card and file chips |
| [components/blocks](components/blocks) | One card per UI block type. `BlockView` picks the card. |
| [components/imports](components/imports) | The review panel for an uploaded file |
| [components/forms](components/forms) | The form panel the agent can open |
| [lib](lib) | API client, stream reader, types, session, voice and upload hooks |

## How a card appears

- A tool returns a typed block, such as `hero` for net worth.
- The backend sends it as a `ui.block` event with the tool call id.
- The model writes `{{card:<id>}}` in its reply.
- [lib/cards.ts](lib/cards.ts) cuts the reply at that marker.
- `MessageTimeline` draws the matching card there.

Design system: [DESIGN.md](DESIGN.md).
