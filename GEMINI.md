# Dependency Management Rules

- **Do Not Downgrade API Versions**: Never downgrade API versions or project dependencies (e.g., in `requirements.txt`) to fix bugs or compatibility issues unless explicitly instructed to do so by the user. If an API update introduces breaking changes or connectivity issues, patch the application code to handle the newer version (e.g., via monkey-patching or fallback handlers) rather than reverting to an older, deprecated library version.
