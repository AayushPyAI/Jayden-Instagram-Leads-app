module.exports = {
    apps: [
      {
        name: "jayden-leads",
        cwd: "/home/node/jayden-codebase/Jayden",
        script: ".venv/bin/uvicorn",
        interpreter: "none",
        args: "app:app --host 0.0.0.0 --port 20158 --workers 1",
        autorestart: true,
        max_restarts: 10,
        env: {
          PORT: "20158",
          WORKBOOK_STORAGE: "s3",
          LOG_LEVEL: "INFO",
        },
      },
    ],
  };