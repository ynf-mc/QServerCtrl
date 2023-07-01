"""
QServerCtrl enables users in a QQ group to control Minecraft servers via QQ messages.

Avaliable commands for users:
/ctrl list
/ctrl start <name>
/ctrl stop <name>
"""


import argparse
import json
from html import unescape
from time import sleep
from mcstatus import JavaServer
import websocket
from qserverctrl.server import *


class CloudServiceController:
    """Controls the underlying cloud service provider."""

    def __init__(
        self,
        name: str,
        description: str,
        port: int,
        timeout: int,
        cloud_service_provider: AbstractCloudServiceProvider,
    ) -> None:
        self.name = name
        self.description = description
        self.port = port
        self.timeout = timeout
        self.cloud_service_provider = cloud_service_provider
        self.poll_status_thread = None

    def start(self) -> Optional[str]:
        if not self.cloud_service_provider.start():
            return None
        return self.get_play_address()

    def stop(self) -> bool:
        return self.cloud_service_provider.stop()

    def is_running(self) -> bool:
        return self.cloud_service_provider.is_running()

    def get_play_address(self) -> str:
        return f"{self.cloud_service_provider.get_ip()}:{self.port}"

    def pool_status(self):
        """
        Poll the status of the server until the no one is online.
        If so, stop the server after $timeout seconds if no one is online.
        """
        server = JavaServer.lookup(self.get_play_address())
        try:
            while True:
                if server.status().players.online == 0:
                    sleep(self.timeout)
                    if server.status().players.online == 0:
                        self.stop()
                        break
                sleep(5)
        except Exception as e:
            e.print_stack()


class MainController:
    """Controls several CloudServiceControllers."""

    def __init__(self, cloud_service_controllers: list[CloudServiceController]) -> None:
        self.cloud_service_controllers = cloud_service_controllers

    def start(self, server_name: str) -> str:
        """
        Returns whether the server is started successfully.
        Returns the message to be sent to the QQ group.
        """
        for controller in self.cloud_service_controllers:
            if controller.name == server_name:
                addr = controller.start()
                if addr is None:
                    return "Failed to start the server."
                return "The server is started at " + addr
        return "No such server."

    def stop(self, server_name: str) -> str:
        """
        Returns whether the server is stopped successfully.
        Returns the message to be sent to the QQ group.
        """
        for controller in self.cloud_service_controllers:
            if controller.name == server_name:
                if controller.stop():
                    return "The server is stopped."
                return "Failed to stop the server."
        return "No such server."

    def list_server(self) -> str:
        """Returns the message to be sent to the QQ group."""
        msg = "Available servers:\n"
        for controller in self.cloud_service_controllers:
            msg += f"-> {controller.name}"
            if controller.is_running():
                msg += ": running"
                msg += f" at {controller.get_play_address()}"
            msg += f" \n{controller.description}\n\n"
        return msg
    
    def get_help(self) -> str:
        """Returns the message to be sent to the QQ group."""
        return "Available commands:\n/ctrl list\n/ctrl start <name>\n/ctrl stop <name>"


class QQBot(websocket.WebSocketApp):
    """Interacts with go-cqhttp with Websocket."""

    def __init__(self, api: str, qq_group: int, controller: MainController) -> None:
        self.api = api
        self.qq_group = qq_group
        self.controller = controller
        websocket.enableTrace(True)
        super().__init__(api, on_message=self.on_message)

    def start(self) -> bool:
        """Start the bot and block the current process."""
        return self.run_forever()

    def on_message(self, ws, message):
        """Handle messages from the QQ group."""
        msg = json.loads(message)
        if msg["message_type"] != "group":
            return
        if msg["group_id"] != self.qq_group:
            return
        if msg["message"].startswith("/ctrl"):
            self.handle_command(msg)

    def handle_command(self, msg):
        """Handle commands from the QQ group."""
        command = msg["message"].split(" ")
        if command[1] == "list":
            self.send_message(self.controller.list_server())
        elif command[1] == "start":
            self.send_message(self.controller.start(command[2]))
        elif command[1] == "stop":
            self.send_message(self.controller.stop(command[2]))
        elif command[1] == "help":
            self.send_message(self.controller.get_help())

    def send_message(self, message):
        """Send message to the QQ group."""
        self.send(
            json.dumps(
                {
                    "action": "send_group_msg",
                    "params": {
                        "group_id": self.qq_group,
                        "message": unescape(message),
                    },
                }
            )
        )


def main():
    parser = argparse.ArgumentParser(
        prog="qserverctrl",
        description="Control Minecraft servers via QQ messages.",
    )
    parser.add_argument(
        "-c", "--config", type=str, default="config.py", help="Configuration script."
    )
    args = parser.parse_args()
    _locals = locals()
    exec(open(args.config).read(), globals(), _locals)
    bot: QQBot = _locals["bot"]
    bot.start()


if __name__ == "__main__":
    main()
