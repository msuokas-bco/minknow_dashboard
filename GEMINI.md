# Dependency Management Rules

- **Do Not Downgrade API Versions**: Never downgrade API versions or project dependencies (e.g., in `requirements.txt`) to fix bugs or compatibility issues unless explicitly instructed to do so by the user. If an API update introduces breaking changes or connectivity issues, patch the application code to handle the newer version (e.g., via monkey-patching or fallback handlers) rather than reverting to an older, deprecated library version.
- **Ignore vulnerabilities that require elevated privileges to begin with**: If attacker has already elevated privileges, it makes little sense to try to attack via web dashboard
- **Telemetry options:* Run Info, Yield, Total reads, Temperatures, Read length, Channel state, Pore scans (every 1.5h), Q-scor and Bracode distribution as needed
- **Device control options:** Flow-cell check, Start run, Pause run, Resume run, Stop run
- **Start run options:**Experiment name, Sample name, Output directory, Run duration, Minimum q-score, Library kit, Basecaller model, Save POD5, Save Fastq, Save bam
