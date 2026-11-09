"""The AWS calls the platform makes, checked against botocore's own API models with the Stubber: wrong
parameter names, missing required fields or bad types fail here, without an AWS account."""

import boto3
import pytest
from botocore.stub import ANY, Stubber

from paved.serving.agentcore import AgentCoreRouter, ConversationSplitter, bucket
from paved.serving.bedrock import BedrockConverseLLM, ensure_inference_profile
from paved.serving.sagemaker import SageMakerDeployer, SageMakerRouter

REGION = "eu-central-1"


def _client(name):
    return boto3.client(name, region_name=REGION, aws_access_key_id="x", aws_secret_access_key="x")


def test_canary_moves_sagemaker_variant_weights():
    sm = _client("sagemaker")
    router = SageMakerRouter(sm, "pricing-conversion")
    with Stubber(sm) as st:
        for cand in (0.05, 0.0, 1.0):
            st.add_response(
                "update_endpoint_weights_and_capacities",
                {"EndpointArn": "arn:aws:sagemaker:eu-central-1:1:endpoint/pricing-conversion"},
                {
                    "EndpointName": "pricing-conversion",
                    "DesiredWeightsAndCapacities": [
                        {"VariantName": "champion", "DesiredWeight": round(1 - cand, 4)},
                        {"VariantName": "candidate", "DesiredWeight": cand},
                    ],
                },
            )
        router.shift("r1", 0.05)
        router.rollback("r1")
        router.promote("r1")
        st.assert_no_pending_responses()


def test_shadow_uses_a_shadow_variant_with_data_capture_and_team_tags(pricing_workload):
    sm = _client("sagemaker")
    d = SageMakerDeployer(sm, "paved-capture")
    with Stubber(sm) as st:
        st.add_response(
            "create_endpoint_config",
            {"EndpointConfigArn": "arn:aws:sagemaker:eu-central-1:1:endpoint-config/x"},
            {
                "EndpointConfigName": ANY,
                "ProductionVariants": ANY,
                "ShadowProductionVariants": ANY,
                "DataCaptureConfig": ANY,
                "Tags": ANY,
            },
        )
        d.shadow_config(pricing_workload, "r1", "m-champ", "m-cand")
        st.assert_no_pending_responses()


def test_endpoint_config_requests_are_valid_for_the_api(pricing_workload):
    sm = _client("sagemaker")
    calls = []
    sm.meta.events.register(
        "provide-client-params.sagemaker.CreateEndpointConfig", lambda params, **_: calls.append(params)
    )
    d = SageMakerDeployer(sm, "paved-capture")
    with Stubber(sm) as st:
        st.add_response(
            "create_endpoint_config", {"EndpointConfigArn": "arn:aws:sagemaker:eu-central-1:1:endpoint-config/x"}
        )
        st.add_response(
            "create_endpoint_config", {"EndpointConfigArn": "arn:aws:sagemaker:eu-central-1:1:endpoint-config/y"}
        )
        d.shadow_config(pricing_workload, "r1", "m-champ", "m-cand")
        d.canary_config(pricing_workload, "r1", "m-champ", "m-cand")
    shadow, canary = calls
    assert shadow["ShadowProductionVariants"][0]["ModelName"] == "m-cand"
    assert [v["InitialVariantWeight"] for v in canary["ProductionVariants"]] == [1.0, 0.0]
    assert {"Key": "team", "Value": "pricing"} in shadow["Tags"]
    assert shadow["DataCaptureConfig"]["EnableCapture"] is True


def test_each_agent_release_gets_a_tagged_application_inference_profile(agent_workload):
    br = _client("bedrock")
    with Stubber(br) as st:
        st.add_response(
            "create_inference_profile",
            {
                "inferenceProfileArn": "arn:aws:bedrock:eu-central-1:1:application-inference-profile/abc",
                "status": "ACTIVE",
            },
            {
                "inferenceProfileName": "cs-automation-cs-email-agent-r1",
                "description": ANY,
                "modelSource": {
                    "copyFrom": "arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-sonnet-4-5"
                },
                "tags": [
                    {"key": "team", "value": "cs-automation"},
                    {"key": "workload", "value": "cs-email-agent"},
                    {"key": "release", "value": "r1"},
                ],
            },
        )
        arn = ensure_inference_profile(
            br, agent_workload, "r1", "arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-sonnet-4-5"
        )
    assert arn.endswith("/abc")


def _converse_response(tool_input, usage=(1200, 60, 2800, 0), latency=850):
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": "t1", "name": "x", "input": tool_input}}],
            }
        },
        "stopReason": "tool_use",
        "usage": {
            "inputTokens": usage[0],
            "outputTokens": usage[1],
            "totalTokens": sum(usage[:2]),
            "cacheReadInputTokens": usage[2],
            "cacheWriteInputTokens": usage[3],
        },
        "metrics": {"latencyMs": latency},
    }


def test_the_converse_adapter_sends_caching_guardrail_and_cost_metadata_and_parses_tool_output(agent_workload):
    rt = _client("bedrock-runtime")
    sent = []
    rt.meta.events.register("provide-client-params.bedrock-runtime.Converse", lambda params, **_: sent.append(params))
    llm = BedrockConverseLLM(
        rt,
        "arn:aws:bedrock:eu-central-1:1:application-inference-profile/abc",
        "You help SIXT customers.",
        ("gr-1", "3"),
        agent_workload,
        {"deposit_refund": "after", "breakdown": "during"},
    )
    with Stubber(rt) as st:
        st.add_response("converse", _converse_response({"intent": "deposit_refund", "confidence": 0.93}))
        st.add_response(
            "converse",
            _converse_response({"text": "Your deposit is released within 7 days.", "claims": {"refund_days": 7}}),
        )
        c, u = llm.classify("my deposit is still blocked", {"inquiry_id": "q1"})
        r, _ = llm.draft_reply("deposit_refund", {"refund_days": 7}, {"inquiry_id": "q1"})
    assert (c.intent, c.phase) == ("deposit_refund", "after")
    assert (u.input_tokens, u.cache_read_tokens, u.latency_ms) == (1200, 2800, 850.0)
    assert r.claims == {"refund_days": 7}
    req = sent[0]
    assert req["system"][-1] == {"cachePoint": {"type": "default"}}
    assert req["guardrailConfig"] == {"guardrailIdentifier": "gr-1", "guardrailVersion": "3"}
    assert req["requestMetadata"]["team"] == "cs-automation"
    assert req["toolConfig"]["toolChoice"] == {"tool": {"name": "classify"}}


def test_an_intent_outside_the_taxonomy_is_refused(agent_workload):
    rt = _client("bedrock-runtime")
    llm = BedrockConverseLLM(rt, "arn:x", "p", None, agent_workload, {"breakdown": "during"})
    with Stubber(rt) as st:
        st.add_response("converse", _converse_response({"intent": "refund_everything", "confidence": 1.0}))
        with pytest.raises(ValueError, match="unknown intent"):
            llm.classify("hi", {"inquiry_id": "q"})


def test_agentcore_router_points_endpoints_at_versions_and_splits_by_conversation():
    ac = _client("bedrock-agentcore-control")
    split = ConversationSplitter()
    router = AgentCoreRouter(ac, "csAgent-abcdefghij", "4", "5", split)
    ok = {
        "liveVersion": "5",
        "targetVersion": "5",
        "agentRuntimeEndpointArn": "arn:e",
        "agentRuntimeArn": "arn:r",
        "status": "READY",
        "createdAt": "2026-11-09T10:00:00Z",
        "lastUpdatedAt": "2026-11-09T10:00:00Z",
    }
    with Stubber(ac) as st:
        st.add_response(
            "update_agent_runtime_endpoint",
            ok,
            {
                "agentRuntimeId": "csAgent-abcdefghij",
                "endpointName": "canary",
                "agentRuntimeVersion": "5",
                "clientToken": ANY,
            },
        )
        st.add_response(
            "update_agent_runtime_endpoint",
            ok,
            {
                "agentRuntimeId": "csAgent-abcdefghij",
                "endpointName": "live",
                "agentRuntimeVersion": "5",
                "clientToken": ANY,
            },
        )
        router.shift("r1", 0.25)
        share = sum(split.endpoint_for(f"conv-{i}") == "canary" for i in range(20000)) / 20000
        assert abs(share - 0.25) < 0.02
        assert split.endpoint_for("conv-7") == split.endpoint_for("conv-7")
        router.shift("r1", 0.5)  # widening the split moves no endpoint
        router.promote("r1")
        st.assert_no_pending_responses()
    assert 0 <= bucket("x") < 1
