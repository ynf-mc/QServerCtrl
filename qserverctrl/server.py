from tencentcloud.common.credential import Credential
from tencentcloud.cvm.v20170312 import cvm_client, models
from time import sleep


class AbstractCloudServiceProvider:
    def start(self) -> bool:
        """Start the server, returns whether successful or not."""
        raise NotImplementedError()

    def stop(self) -> bool:
        """Stop the server, returns whether successful or not."""
        raise NotImplementedError()

    def is_running(self) -> bool:
        raise NotImplementedError()

    def get_ip(self) -> str:
        """ "Get the server IP address. Return None if the server is not running."""
        raise NotImplementedError()


class TencentCloudServiceProvider(AbstractCloudServiceProvider):
    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        region: str,
        instance_id: str,
    ) -> None:
        self.credential = Credential(secret_id, secret_key)
        self.region = region
        self.instance_id = instance_id
        self.client = cvm_client.CvmClient(self.credential, self.region)

    def is_running(self) -> bool:
        """Return whether the server is running."""
        description = self.describe_instance()
        return description.InstanceSet[0].InstanceState == "RUNNING"

    def poll_latest_operation(
        self, poll_interval: int = 1, max_retry: int = 50
    ) -> bool:
        """
        Poll the latest operation from Tencent Cloud API until it is finished.
        Return whether the operation is successful.
        """
        for _ in range(max_retry):
            description = self.describe_instance()
            if description.InstanceSet[0].LatestOperationState == "SUCCESSFUL":
                return True
            elif description.InstanceSet[0].LatestOperationState == "FAILED":
                return False
            sleep(poll_interval)
        return False

    def describe_instance(self) -> models.DescribeInstancesResponse:
        """
        DescribeInstance request.
        """
        req = models.DescribeInstancesRequest()
        req.InstanceIds = [self.instance_id]
        resp = self.client.DescribeInstances(req)
        return resp

    def start(self) -> bool:
        """Start the server, returns server IP address."""
        if self.is_running():
            raise RuntimeError("Server is already running.")
        req = models.StartInstancesRequest()
        req.InstanceIds = [self.instance_id]
        resp = self.client.StartInstances(req)
        return self.poll_latest_operation()

    def stop(self) -> bool:
        """Stop the server with param SOFT_FIRST and SOFT_CHARGING."""
        if not self.is_running():
            raise RuntimeError("Server is already stopped.")
        req = models.StopInstancesRequest()
        req.InstanceIds = [self.instance_id]
        req.StopType = "SOFT_FIRST"
        req.StoppedMode = "SOFT_CHARGING"
        resp = self.client.StopInstances(req)
        return self.poll_latest_operation()

    def get_ip(self) -> str:
        if not self.is_running():
            return None
        description = self.describe_instance()
        return description.InstanceSet[0].PublicIpAddresses[0]
