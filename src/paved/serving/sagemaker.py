"""SageMaker side of the release path for models.

Shadow: the candidate is a shadow production variant; SageMaker copies requests to it and discards its answers,
and data capture records what it received (the input to the online/offline parity check).
Canary: champion and candidate are production variants on one endpoint; the router moves variant weights.
Every resource carries the team and workload as cost-allocation tags.
"""

from __future__ import annotations

from dataclasses import dataclass

from paved.contract import Workload

CHAMPION, CANDIDATE = "champion", "candidate"


def tags(workload: Workload, release_id: str) -> list[dict]:
    return [
        {"Key": "team", "Value": workload.team},
        {"Key": "workload", "Value": workload.name},
        {"Key": "release", "Value": release_id},
        {"Key": "managed-by", "Value": "paved"},
    ]


def _variant(name: str, model: str, workload: Workload, weight: float) -> dict:
    return {
        "VariantName": name,
        "ModelName": model,
        "InstanceType": workload.serving.instance_type,
        "InitialInstanceCount": workload.serving.instance_count,
        "InitialVariantWeight": weight,
    }


def _capture(bucket: str, workload: Workload) -> dict:
    return {
        "EnableCapture": True,
        "InitialSamplingPercentage": 100,
        "DestinationS3Uri": f"s3://{bucket}/capture/{workload.team}/{workload.name}",
        "CaptureOptions": [{"CaptureMode": "Input"}, {"CaptureMode": "Output"}],
    }


@dataclass
class SageMakerDeployer:
    client: object
    capture_bucket: str

    def create_model(self, workload: Workload, release_id: str, image: str, model_data: str, role_arn: str) -> str:
        name = f"{workload.name}-{release_id}"[:63]
        self.client.create_model(
            ModelName=name,
            PrimaryContainer={"Image": image, "ModelDataUrl": model_data},
            ExecutionRoleArn=role_arn,
            Tags=tags(workload, release_id),
        )
        return name

    def shadow_config(self, workload: Workload, release_id: str, champion_model: str, candidate_model: str) -> str:
        name = f"{workload.name}-{release_id}-shadow"[:63]
        self.client.create_endpoint_config(
            EndpointConfigName=name,
            ProductionVariants=[_variant(CHAMPION, champion_model, workload, 1.0)],
            ShadowProductionVariants=[_variant(CANDIDATE, candidate_model, workload, 1.0)],
            DataCaptureConfig=_capture(self.capture_bucket, workload),
            Tags=tags(workload, release_id),
        )
        return name

    def canary_config(self, workload: Workload, release_id: str, champion_model: str, candidate_model: str) -> str:
        name = f"{workload.name}-{release_id}-canary"[:63]
        self.client.create_endpoint_config(
            EndpointConfigName=name,
            ProductionVariants=[
                _variant(CHAMPION, champion_model, workload, 1.0),
                _variant(CANDIDATE, candidate_model, workload, 0.0),
            ],
            DataCaptureConfig=_capture(self.capture_bucket, workload),
            Tags=tags(workload, release_id),
        )
        return name

    def switch(self, endpoint: str, config: str) -> None:
        self.client.update_endpoint(EndpointName=endpoint, EndpointConfigName=config)


class SageMakerRouter:
    """Moves traffic between the champion and candidate production variants of one endpoint."""

    def __init__(self, client: object, endpoint: str):
        self.client = client
        self.endpoint = endpoint

    def _weights(self, candidate: float) -> None:
        self.client.update_endpoint_weights_and_capacities(
            EndpointName=self.endpoint,
            DesiredWeightsAndCapacities=[
                {"VariantName": CHAMPION, "DesiredWeight": round(1.0 - candidate, 4)},
                {"VariantName": CANDIDATE, "DesiredWeight": round(candidate, 4)},
            ],
        )

    def shift(self, release_id: str, share: float) -> None:
        self._weights(share)

    def rollback(self, release_id: str) -> None:
        self._weights(0.0)

    def promote(self, release_id: str) -> None:
        self._weights(1.0)
