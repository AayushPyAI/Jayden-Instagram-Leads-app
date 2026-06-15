module.exports = {
  apps: [
    {
      name: "jayden-leads",
      cwd: "/home/node/jayden-codebase/Jayden",
      script: ".venv/bin/python",
      args: "-m uvicorn app:app --host 0.0.0.0 --port 20158",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      merge_logs: true,
      time: true,
    },
  ],
};
