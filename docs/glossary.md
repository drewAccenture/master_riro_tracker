# Glossary

Business words (joiner, checklist file, roll-on date, sync, status as of) are defined in `docs/requirements.md`
section 1. This list adds the technical words used in the architecture.

| Word | Meaning |
|---|---|
| Atomic save | Write the data to a temporary file, then replace the real file in one step, so a crash never leaves half a file |
| Bridge | The small Python file that lists what the page may ask Python to do |
| CDP (Chrome DevTools Protocol) | The way a program talks to a running Edge: open a page, run a script, close. Edge speaks it when started with a debugging port |
| Connector | Code that talks to one outside system (here SharePoint) and hides its details from the rest of the app |
| Core | The pure rules: reading a checklist, deadline offsets, statuses. No files, no network |
| Edge profile | A folder where Edge keeps its sign-in and settings. The app uses its own, separate from the PMO's normal Edge |
| Embeddable Python | An official zip of Python from python.org that runs from any folder, without installing or admin rights |
| ETag | A version tag SharePoint gives each file. It changes when the file changes, so the app only downloads changed files |
| Headless | Edge running without a visible window |
| Job Object | A Windows feature that groups processes so the app can end Edge and all its child processes in one call |
| Normalized owner | The Checklist Owner text trimmed, in lower case, with repeated spaces made single. Used to match files to joiners |
| pywebview | A Python package that shows HTML in a normal desktop window, using the Edge engine built into Windows (WebView2) |
| REST call | A web request to SharePoint's `_api` address that returns data (folder list, file bytes) instead of a page |
| Schema version | A number in the data file that says which layout it has, so a new app version can upgrade it |
| Silent renewal | Getting a fresh SharePoint sign-in from the longer Microsoft sign-in, without showing anything |
| Single-flight | Only one sync runs at a time; a second request while one runs does not start another |
| Slice (vertical slice) | A small piece that goes through every layer end to end, built to prove the design works |
| UniqueId | SharePoint's permanent id for a file. It stays the same when the file is renamed or edited |
| WebView2 | The Edge engine that other Windows apps can embed. Part of Windows 11 |
