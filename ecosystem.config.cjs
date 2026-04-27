module.exports = {
  apps: [
    {
      name: "invest-main",
      script: "/home/zy/miniconda3/envs/investment_bot/bin/python",
      args: "main.py",
      interpreter: "none",
      autorestart: true,
      watch: false,
      log_date_format: "YYYY-MM-DD HH:mm Z",
      // 注： API Key 不写在这里，由 main.py 内部的 load_dotenv 从 .env 加载
      env: {
        http_proxy: "http://127.0.0.1:10810",
        https_proxy: "http://127.0.0.1:10810",
        all_proxy: "http://127.0.0.1:10810",
        ENABLE_CLAUDE_BOT: ""
      }
    },
    {
      name: "invest-scheduler",
      script: "/home/zy/miniconda3/envs/investment_bot/bin/python",
      args: "bots/daily_report/scheduler_runner.py",
      interpreter: "none",
      autorestart: true,
      watch: false,
      log_date_format: "YYYY-MM-DD HH:mm Z",
      // 注： API Key 不写在这里，由 scheduler_runner.py 内部的 load_dotenv 从 .env 加载
      env: {
        http_proxy: "http://127.0.0.1:10810",
        https_proxy: "http://127.0.0.1:10810",
        all_proxy: "http://127.0.0.1:10810"
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
