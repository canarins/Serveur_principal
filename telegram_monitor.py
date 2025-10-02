#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import glob
import json
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp
import re

class CanarinLogMonitor:
    def __init__(self, bot_token, chat_id, log_directory="logs"):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.log_directory = log_directory
        self.device_status = {}
        self.last_update_id = 0

        # Exclude pseudo-devices here
        self.excluded_devices = {"invalid_json"}

        # Error patterns to alert on
        self.error_patterns = [
            r"error",
            r"fatal",
            r"exception",
            r"failed",
            r"critical",
            r"timeout",
            r"connection\.lost",
            r"unable\.connect",
        ]

        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("monitor.log"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger("canarin_monitor")

    def _is_excluded(self, device_name: str) -> bool:
        return device_name in self.excluded_devices

    async def send_telegram_message(self, message, reply_to_message_id=None, chat_id=None):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id if chat_id is not None else self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        self.logger.error(f"Telegram sendMessage failed: {resp.status} - {body}")
        except Exception as e:
            self.logger.error(f"Error sending Telegram message: {str(e)}")

    async def get_updates(self):
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {"timeout": 30, "offset": self.last_update_id + 1}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=35) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        self.logger.error(f"getUpdates HTTP {resp.status}: {body}")
                        return []
                    data = await resp.json(content_type=None)
                    return data.get("result", [])
        except Exception as e:
            self.logger.error(f"Error fetching updates: {e}")
            return []

    async def handle_command(self, message):
        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]

        if text == "/devices":
            await self.handle_devices_command(chat_id, message_id)
        elif text == "/status":
            await self.handle_status_command(chat_id, message_id)
        elif text.startswith("/ping"):
            await self.send_telegram_message("Pong 🏓", reply_to_message_id=message_id, chat_id=chat_id)
        else:
            await self.send_telegram_message("Commands: /devices, /status, /ping", reply_to_message_id=message_id, chat_id=chat_id)

    def list_log_files(self):
        pattern = os.path.join(self.log_directory, "*.log")
        return sorted(glob.glob(pattern))

    async def handle_devices_command(self, chat_id, reply_to_message_id):
        try:
            log_files = self.list_log_files()
            devices = []
            for logfile in log_files:
                device_name = os.path.basename(logfile).replace(".log", "")
                if self._is_excluded(device_name):
                    continue
                try:
                    stat = os.stat(logfile)
                    last_modified = datetime.fromtimestamp(stat.st_mtime)
                    status = "online" if (datetime.now() - last_modified) < timedelta(minutes=10) else "offline"
                    devices.append((device_name, status, last_modified))
                except Exception as e:
                    self.logger.error(f"Error reading {logfile}: {e}")

            if not devices:
                msg = "No devices to display."
                await self.send_telegram_message(msg, reply_to_message_id, chat_id)
                return

            lines = []
            for name, status, last_modified in devices:
                emoji = "✅" if status == "online" else "⚠️"
                lines.append(f"{emoji} `{name}` - {last_modified.strftime('%Y-%m-%d %H:%M:%S')}")

            message = "📱 Devices\n" + "\n".join(lines) + "\n🔗 Server: canarin-sensors.com"
            await self.send_telegram_message(message, reply_to_message_id, chat_id)
        except Exception as e:
            self.logger.error(f"Error in /devices: {e}")

    async def handle_status_command(self, chat_id, reply_to_message_id):
        try:
            await self.check_server_health()
            online_count = sum(1 for f in self.list_log_files()
                               if not self._is_excluded(os.path.basename(f).replace(".log", "")) and
                               (datetime.now() - datetime.fromtimestamp(os.stat(f).st_mtime)) < timedelta(minutes=10))
            offline_count = sum(1 for f in self.list_log_files()
                                if not self._is_excluded(os.path.basename(f).replace(".log", "")) and
                                (datetime.now() - datetime.fromtimestamp(os.stat(f).st_mtime)) >= timedelta(minutes=10))
            msg = f"Server OK\nDevices online: {online_count}\nDevices offline: {offline_count}\n🔗 Server: canarin-sensors.com"
            await self.send_telegram_message(msg, reply_to_message_id, chat_id)
        except Exception as e:
            self.logger.error(f"Error in /status: {e}")

    async def monitor_log_errors(self, log_file_path):
        device_name = os.path.basename(log_file_path).replace(".log", "")
        if self._is_excluded(device_name):
            return
        try:
            if not hasattr(self, "file_positions"):
                self.file_positions = {}
            if log_file_path not in self.file_positions:
                if os.path.exists(log_file_path):
                    with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(0, 2)
                        self.file_positions[log_file_path] = f.tell()
                else:
                    self.file_positions[log_file_path] = 0

            if os.path.exists(log_file_path):
                with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(self.file_positions[log_file_path])
                    new_lines = f.readlines()
                    self.file_positions[log_file_path] = f.tell()

                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    for pattern in self.error_patterns:
                        if re.search(pattern, line, re.IGNORECASE):
                            message = (
                                f"🔥 `{device_name}`\n"
                                f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"❌ Error:\n`{line[:200]}...`\n"
                                f"🔗 Server: canarin-sensors.com"
                            )
                            await self.send_telegram_message(message)
                            self.logger.warning(f"Error detected in {device_name}: {line[:100]}")
                            break
        except Exception as e:
            self.logger.error(f"Error monitoring {log_file_path}: {str(e)}")

    async def check_device_activity(self):
        try:
            log_files = self.list_log_files()
            current_time = datetime.now()

            for logfile in log_files:
                device_name = os.path.basename(logfile).replace(".log", "")
                if self._is_excluded(device_name):
                    continue

                try:
                    stat = os.stat(logfile)
                    last_modified = datetime.fromtimestamp(stat.st_mtime)
                    time_diff = current_time - last_modified

                    if time_diff > timedelta(minutes=10):
                        if self.device_status.get(device_name) != "offline":
                            message = (
                                f"⚠️ `{device_name}` - {last_modified.strftime('%H:%M')}\n"
                                f"📱 `{device_name}`\n"
                                f"⏰ Last seen: {last_modified.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"⌛ Offline for: {str(time_diff).split('.')[0]}\n"
                                f"🔗 Server: canarin-sensors.com"
                            )
                            await self.send_telegram_message(message)
                            self.device_status[device_name] = "offline"
                            self.logger.warning(f"Device {device_name} marked as offline")
                    else:
                        if self.device_status.get(device_name) == "offline":
                            message = (
                                f"✅ `{device_name}`\n"
                                f"⏰ Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"🔗 Server: canarin-sensors.com"
                            )
                            await self.send_telegram_message(message)
                            self.device_status[device_name] = "online"
                            self.logger.info(f"Device {device_name} back online")
                except Exception as e:
                    self.logger.error(f"Error checking device {device_name}: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error in check_device_activity: {e}")

    async def check_server_health(self):
        try:
            systemctl_path = "/usr/bin/systemctl"

            # canarin.service
            try:
                result = await asyncio.create_subprocess_exec(
                    systemctl_path, "is-active", "--quiet", "canarin",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.wait()
                tcp_running = result.returncode == 0
            except Exception as e:
                self.logger.error(f"Error checking canarin service: {e}")
                tcp_running = False

            # flaskapp.service
            try:
                result = await asyncio.create_subprocess_exec(
                    systemctl_path, "is-active", "--quiet", "flaskapp",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.wait()
                web_running = result.returncode == 0
            except Exception as e:
                self.logger.error(f"Error checking flaskapp service: {e}")
                web_running = False

            # confirm services exist
            try:
                result = await asyncio.create_subprocess_exec(
                    systemctl_path, "list-units", "--type=service", "--all",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()
                services_list = stdout.decode()
                canarin_exists = "canarin.service" in services_list
                flaskapp_exists = "flaskapp.service" in services_list
            except Exception as e:
                self.logger.error(f"Error listing services: {e}")
                canarin_exists = flaskapp_exists = False

            if canarin_exists and not tcp_running:
                if not hasattr(self, "tcp_alerted") or not self.tcp_alerted:
                    message = "🚨 canarin.service is not active"
                    await self.send_telegram_message(message)
                    self.tcp_alerted = True
            else:
                self.tcp_alerted = False

            if flaskapp_exists and not web_running:
                if not hasattr(self, "web_alerted") or not self.web_alerted:
                    message = "🚨 flaskapp.service is not active"
                    await self.send_telegram_message(message)
                    self.web_alerted = True
            else:
                self.web_alerted = False

        except Exception as e:
            self.logger.error(f"Error checking server health: {e}")

    async def poll_commands(self):
        updates = await self.get_updates()
        for update in updates:
            self.last_update_id = update["update_id"]
            message = update.get("message")
            if not message:
                continue
            try:
                await self.handle_command(message)
            except Exception as e:
                self.logger.error(f"Error handling message: {e}")

    async def run(self):
        self.logger.info("Starting CanarinLogMonitor...")
        while True:
            try:
                await asyncio.gather(
                    self.poll_commands(),
                    self.check_device_activity(),
                    self.monitor_all_logs_once(),
                    self.check_server_health(),
                )
            except Exception as e:
                self.logger.error(f"Main loop error: {e}")
            await asyncio.sleep(5)

    async def monitor_all_logs_once(self):
        tasks = []
        for logfile in self.list_log_files():
            # monitor_log_errors itself will skip excluded devices
            tasks.append(self.monitor_log_errors(logfile))
        if tasks:
            await asyncio.gather(*tasks)

if __name__ == "__main__":
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    log_directory = os.environ.get("CANARIN_LOG_DIR", "/home/ubuntu/logserver/logs").strip()

    if not bot_token or not chat_id:
        print("Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.")
        raise SystemExit(1)

    monitor = CanarinLogMonitor(bot_token, chat_id, log_directory)
    asyncio.run(monitor.run())
