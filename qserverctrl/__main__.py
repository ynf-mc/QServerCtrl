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
import threading
from mcstatus import JavaServer
import websocket
from qserverctrl.server import *


class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self,  *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


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
        self.name: str = name
        self.description: str = description
        self.port: int = port
        self.timeout: int = timeout
        self.cloud_service_provider: AbstractCloudServiceProvider = cloud_service_provider
        self.poll_status_thread: Optional[StoppableThread] = None
        if cloud_service_provider.is_running():
            self.poll_status_thread = StoppableThread(target=self.pool_status)
            self.poll_status_thread.start()

    def start(self) -> Optional[str]:
        if self.cloud_service_provider.is_running():
            return self.get_play_address()
        if not self.cloud_service_provider.start():
            return None
        if self.poll_status_thread is not None:
            self.poll_status_thread.stop()
        self.poll_status_thread = StoppableThread(target=self.pool_status)
        self.poll_status_thread.start()
        return self.get_play_address()

    def stop(self) -> bool:
        if not self.cloud_service_provider.is_running():
            return True
        if self.poll_status_thread is not None:
            self.poll_status_thread.stop()
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
        global BOT
        while True:
            try:
                server = JavaServer.lookup(self.get_play_address())
                print(f"[{self.poll_status_thread}] Server players: {server.status().players.online}")
                # BOT.send_message(f"{self.name} players: {server.status().players.online}")
                if server.status().players.online == 0:
                    BOT.send_message(f"{self.name} has no players and will be stopped in {self.timeout} seconds.")
                    sleep(self.timeout)
                    if server.status().players.online == 0:
                        print(f"[{self.poll_status_thread}] No one is online. Stopping.")
                        BOT.send_message(f"{self.name} No one is online. Stopping.")
                        self.stop()
                    else:
                        BOT.send_message(f"{self.name} has {server.status().players.online} players. Stop cancelled.")
            except Exception as e:
                print(f"[{self.poll_status_thread}] Error polling server: {e}")
                sleep(self.timeout)
                try:  # FIXME: Whacky code
                    server = JavaServer.lookup(self.get_play_address())
                    _ = server.status().players.online
                except Exception as e:  # If error persists, stop the server
                    print(f"[{self.poll_status_thread}] Error polling server: {e}. Stopping.")
                    BOT.send_message(f"{self.name} Error polling server: {e}. Stopping.")
                    self.stop()
            if self.poll_status_thread.stopped():
                break
            sleep(5)


class MainController:
    """Controls several CloudServiceControllers."""

    def __init__(self, cloud_service_controllers: list[CloudServiceController]) -> None:
        self.cloud_service_controllers = cloud_service_controllers

    def start(self, servername: str) -> None:
        """
        Returns whether the server is started successfully.
        Returns the message to be sent to the QQ group.
        """
        global BOT
        for controller in self.cloud_service_controllers:
            if controller.name == servername:
                if controller.is_running():
                    return f"Server {servername} is already running at {controller.get_play_address()}."
                addr = controller.start()
                if addr is None:
                    # return f"Failed to start {server_name}."
                    BOT.send_message(f"Failed to start {servername}.")
                    return
                # return "The server is started at " + addr
                BOT.send_message(f"The server is started at {addr}")
                return
        # return "No such server."
        BOT.send_message("No such server.")

    def stop(self, servername: str) -> None:
        """
        Returns whether the server is stopped successfully.
        Returns the message to be sent to the QQ group.
        """
        global BOT
        for controller in self.cloud_service_controllers:
            if controller.name == servername:
                if not controller.is_running():
                    # return f"Server {server_name} is not running."
                    BOT.send_message(f"Server {servername} is not running.")
                    return
                if controller.stop():
                    # return f"Server {server_name} stopped."
                    BOT.send_message(f"Server {servername} stopped.")
                    return
                # return "Failed to stop the server."
                BOT.send_message(f"Failed to stop {servername}.")
                return
        # return "No such server."
        BOT.send_message("No such server.")

    def list_server(self) -> None:
        """Returns the message to be sent to the QQ group."""
        global BOT
        msg = "Available servers:\n"
        for controller in self.cloud_service_controllers:
            msg += f"-> {controller.name} "
            if controller.is_running():
                msg += f"running at {controller.get_play_address()}"
            else:
                msg += "stopped"
            msg += f"\n{controller.description}\n\n"
        # return msg
        BOT.send_message(msg)
    
    def get_help(self) -> None:
        """Returns the message to be sent to the QQ group."""
        global BOT
        # return "Available commands:\n/ctrl list\n/ctrl start <name>\n/ctrl stop <name>"
        BOT.send_message("Available commands:\n/ctrl list\n/ctrl start <name>\n/ctrl stop <name>")


class QQBot(websocket.WebSocketApp):
    """Interacts with go-cqhttp with Websocket."""

    def __init__(self, api: str, qq_group: int, controller: MainController) -> None:
        self.api = api
        self.qq_group = qq_group
        self.controller = controller
        websocket.enableTrace(False)
        super().__init__(api, on_message=self.on_message)

    def start(self) -> bool:
        """Start the bot and block the current process."""
        return self.run_forever()

    def on_message(self, _, message: str):
        """Handle messages from the QQ group."""
        try:
            msg = json.loads(message)
            if msg["message_type"] != "group":
                return
            if msg["group_id"] != self.qq_group:
                return
            if msg["message"].startswith("/ctrl"):
                threading.Thread(
                    target=self.handle_command,
                    args=(msg["message"],)
                ).start()
        except Exception as e:
            pass  # Slience errors
            # print(f"Error handling message: {e}")

    def handle_command(self, msg: str):
        """Handle commands from the QQ group."""
        command = msg.split(" ")
        if len(command) != 3:
            self.controller.get_help()
        if command[1] == "list":
            self.controller.list_server()
        elif command[1] == "start":
            self.controller.start(command[2])
        elif command[1] == "stop":
            self.controller.stop(command[2])
        elif command[1] == "help":
            self.controller.get_help()

    def send_message(self, message: str):
        """Send message to the QQ group."""
        unescaped = unescape(message)
        print(f"Sending message: {unescaped}")
        self.send(
            json.dumps(
                {
                    "action": "send_group_msg",
                    "params": {
                        "group_id": self.qq_group,
                        "message": unescaped,
                    },
                }
            )
        )


# Evil global variable but hey wtf it's just a small script
BOT: Optional[QQBot] = None

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
    global BOT
    BOT = _locals["bot"]
    print(f"Bot initialized at {BOT.api} with group {BOT.qq_group}.")
    BOT.start()


if __name__ == "__main__":
    main()
