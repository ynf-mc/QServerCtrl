s1p = TencentCloudServiceProvider(
    secret_id="secret_id",
    secret_key="secret_key",
    region="ap-nanjing",
    instance_id="ins-12345678",
)

s1c = CloudServiceController(
    name="server1",
    description="A server",
    cloud_service_provider=s1p,
    port=25565,
    timeout=180,
)

main_controller = MainController([s1c])
bot = QQBot(
    api="ws://localhost:6700",
    qq_group=12345678,
    controller=main_controller,
)
