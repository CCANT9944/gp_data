# GP Data Manager Guidelines

## Scope
- This repository is a Python application with both a Tkinter desktop UI and a CLI entrypoint.
- Prefer focused changes that preserve existing behavior, public entrypoints, and test compatibility.

## Architecture
- Keep UI wiring in `ui/app.py` and related layout/controller modules. Put business logic in the narrowest controller or helper that already owns that workflow.
- Preserve the separation between `data_manager/` storage code, `models.py` record logic, and `settings*.py` persistence and normalization layers.
- Treat `settings.py`, `ui/app.py`, and compatibility re-export modules as stable public surfaces unless the task explicitly requires changing them.

## Change Strategy
- Fix issues at the root cause instead of layering duplicate UI-side checks or one-off patches.
- Avoid broad refactors unless the request explicitly asks for them.
- Do not change persisted local data files, backup files, or `settings.json` as part of normal feature or bug-fix work.
- Keep backup, restore, migration, inline edit, search/filter, and CSV preview changes regression-safe.

## Tests And Validation
- When behavior changes, update or add focused tests in the closest existing file under `tests/`.
- Run the narrowest meaningful pytest target first, then broaden validation only if needed.
- Use `MANUAL.txt` as the preferred plain-language source for current user-visible behavior, `README.md` for run and CLI commands, and `BUG_HUNTING.md` as the manual regression checklist for risky UI or persistence changes.

## Repo Conventions
- Follow the existing small-module structure and naming patterns instead of introducing a new abstraction style.
- Keep comments sparse and only add them when the code would otherwise be hard to parse.
- Prefer explicit error handling over broad exception swallowing.