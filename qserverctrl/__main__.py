"""
QServerCtrl enables users in a QQ group to control Minecraft servers via QQ messages.

Avaliable commands for users:
/ctrl list
/ctrl start <name>
/ctrl stop <name>
"""


import argparse
from time import sleep
from mcstatus import JavaServer
import websockets
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

    def start(self) -> str:
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
            msg += f"{controller.name}"
            if controller.is_running():
                msg += ": running"
                msg += f" at {controller.get_play_address()}\n"
            msg += f" {controller.description}\n\n"
        return msg


class QQBot:
    """Interacts with go-cqhttp with Websocket."""

    def __init__(self, api: str, qq_group: int, controller: MainController) -> None:
        self.api = api
        self.qq_group = qq_group
        self.controller = controller

    def start(self):
        """Connect to the websocket."""
        with websockets.connect(self.api) as ws:
            while True:
                msg = ws.recv()
                if msg["message_type"] == "group" and msg["group_id"] == self.qq_group:
                    reply = self.handle_message(msg["message"])
                    if reply is not None:
                        ws.send(
                            {
                                "action": "send_group_msg",
                                "params": {
                                    "group_id": self.qq_group,
                                    "message": reply,
                                },
                            }
                        )

    def handle_message(self, msg: str):
        """Handle the message from the QQ group."""
        if msg.startswith("/ctrl "):
            msg = msg[6:]
            if msg.startswith("list"):
                return self.controller.list_server()
            elif msg.startswith("start "):
                server_name = msg[6:]
                return self.controller.start(server_name)
            elif msg.startswith("stop "):
                server_name = msg[5:]
                return self.controller.stop(server_name)


def main():
    parser = argparse.ArgumentParser(
        prog="qserverctrl",
        description="Control Minecraft servers via QQ messages.",
    )
    parser.add_argument(
        "-c", "--config", type=str, default="config.py", help="Configuration script."
    )
    args = parser.parse_args()
    bot = None
    with open(args.config) as f:
        exec(f.read())
    bot.start()
