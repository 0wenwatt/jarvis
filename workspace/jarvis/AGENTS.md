# Repository Conventions

## Documentation Placement
- Put all project documentation under `docs/`.
- Do not add new top-level `*.md` docs in the repository root unless they are required by tooling.
- When moving or creating docs, update links so they resolve from `docs/`.

## Secret Handling
- Never commit real credentials.
- Keep local secrets only in `.env` and `workspace/.env` (ignored by git).
- Keep shareable templates in `.env.example` and `workspace/.env.example`.

## Project filetree
- The file tree must be a deep nested tree.
-