module.exports = {
  apps: [
    {
      name: "invest-main",
      script: "venv/bin/python",
      args: "main.py",
      interpreter: "none",
      autorestart: true,
      watch: false,
      log_date_format: "YYYY-MM-DD HH:mm Z",
      env: {
        http_proxy: "http://127.0.0.1:10809",
        https_proxy: "http://127.0.0.1:10809",
        all_proxy: "socks5://127.0.0.1:10808"
      }
    },
    {
      name: "invest-scheduler",
      script: "venv/bin/python",
      args: "bots/daily_report/scheduler_runner.py",
      interpreter: "none",
      autorestart: true,
      watch: false,
      log_date_format: "YYYY-MM-DD HH:mm Z",
      env: {
        http_proxy: "http://127.0.0.1:10809",
        https_proxy: "http://127.0.0.1:10809",
        all_proxy: "socks5://127.0.0.1:10808"
      }
    },
    {
      name: "invest-cleanup",
      script: "bash",
      args: "clean.sh",
      interpreter: "none",
      autorestart: false,
      cron_restart: "0 2 * * 5", // 每周五凌晨 2点运行清理
      log_date_format: "YYYY-MM-DD HH:mm Z"
    }
  ]
};
