"""Microsoft 365 Agents SDK local wrapper; anonymous Playground only, no send path."""

import asyncio
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from aiohttp import web
from microsoft_agents.activity import Activity, Attachment
from microsoft_agents.hosting.aiohttp import CloudAdapter, start_agent_process
from microsoft_agents.hosting.core import AgentApplication, MemoryStorage
from microsoft_agents.hosting.core.rest_channel_service_client_factory import (
    RestChannelServiceClientFactory,
)

from follow_the_money.cases import TraceRequest
from follow_the_money.contracts import FtmError
from follow_the_money.mcp_server import case_summary
from follow_the_money.security import local_url
from follow_the_money.service import TraceService

HELP = "Local research demo. Commands: trace bitcoin syn_seed_a; trace tron syn_tron_seed; case <case-id>. Traces use replay only and pause for human review in the local UI. No command approves, sends a request, or establishes ownership."


def review_card(case: dict, reviewer_url="http://127.0.0.1:8501") -> dict:
    local_url(reviewer_url)
    state = case.get("state") or {}
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "Research case awaiting human review",
                "weight": "Bolder",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Case", "value": case["case_id"]},
                    {"title": "Status", "value": case["status"]},
                    {
                        "title": "Evidence SHA-256",
                        "value": state.get("evidence_sha256", "pending"),
                    },
                ],
            },
            {
                "type": "TextBlock",
                "text": "Inspect transaction citations and critic outcomes. Approval is recorded only in the authenticated local reviewer UI. Nothing is sent.",
                "wrap": True,
            },
        ],
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": "Open local human review",
                "url": reviewer_url,
            }
        ],
    }


class LocalReplyFactory(RestChannelServiceClientFactory):
    """Use the SDK's anonymous reply buffer; prohibit connector/OAuth operations."""

    def __init__(self):
        super().__init__(None, token_service_endpoint="http://127.0.0.1:9/disabled")

    async def create_connector_client(self, *args, **kwargs):
        raise PermissionError("Outbound connectors are disabled in the local demo")

    async def create_user_token_client(
        self, context, claims_identity, use_anonymous=False
    ):
        if not use_anonymous or context.activity.is_agentic_request():
            raise PermissionError("Only anonymous buffered local replies are supported")
        return await super().create_user_token_client(context, claims_identity, True)


class DisabledConnections:
    """SDK connection protocol for the local demo; every token request fails closed."""

    def get_connection(self, *args, **kwargs):
        raise PermissionError("OAuth and external connections are disabled")

    get_default_connection = get_connection
    get_token_provider = get_connection
    get_token_provider_from_activity = get_connection
    get_default_connection_configuration = get_connection


def create_agent(service: TraceService):
    adapter = CloudAdapter(channel_service_client_factory=LocalReplyFactory())
    agent = AgentApplication(
        storage=MemoryStorage(),
        adapter=adapter,
        start_typing_timer=False,
        connection_manager=DisabledConnections(),
    )
    lock = asyncio.Lock()

    @agent.activity("message")
    async def message(context, _):
        # A card submission or source document cannot become an approval command.
        activity = context.activity
        if activity.value or activity.attachments:
            await context.send_activity(
                "Submissions and attachments are not accepted here. Use the authenticated human review UI."
            )
            return
        text = activity.text or ""
        parts = text.split()
        try:
            if len(text) > 500:
                raise ValueError
            async with lock:
                if len(parts) == 3 and parts[0] == "trace":
                    if not activity.id or len(activity.id) > 200:
                        raise ValueError
                    request = TraceRequest(
                        chain=parts[1],
                        seed=parts[2],
                        request_id=str(
                            uuid5(
                                NAMESPACE_URL,
                                f"ftm-playground:{activity.conversation.id}:{activity.id}",
                            )
                        ),
                    )
                    case = await asyncio.to_thread(
                        service.start_case, request, actor="local-playground"
                    )
                elif len(parts) == 2 and parts[0] == "case":
                    case = await asyncio.to_thread(service.get_case, parts[1])
                else:
                    await context.send_activity(HELP)
                    return
            summary = case_summary(case)
            await context.send_activity(
                f"Case {summary['case_id']}: {summary['status']}. Retained claims shown: {len(summary['claims'])}; withdrawn: {summary['withdrawn_claims']}. Research leads only."
            )
            await context.send_activity(
                Activity(
                    type="message",
                    attachments=[
                        Attachment(
                            content_type="application/vnd.microsoft.card.adaptive",
                            content=review_card(case),
                        )
                    ],
                )
            )
        except (ValueError, FtmError):
            await context.send_activity(
                "Request rejected or replay unavailable. Use the documented commands and inspect the local audit."
            )

    @agent.error
    async def error(context, _):
        await context.send_activity(
            "Local operation failed. Inspect the workspace and recover through the reviewer UI."
        )

    return agent


def create_local_app(service: TraceService) -> web.Application:
    """Only synchronous local replies: no callback to an activity's service URL."""
    agent = create_agent(service)

    @web.middleware
    async def boundary(request, handler):
        try:
            local_url("http://" + request.host)
            if request.remote not in {"127.0.0.1", "::1"}:
                raise ValueError
            if request.headers.get("Origin") not in (None, "http://" + request.host):
                raise ValueError
            if request.method == "POST":
                body = await request.json()
                if (
                    body.get("deliveryMode") != "expectReplies"
                    or body.get("channelId") != "emulator"
                ):
                    raise ValueError
                if body.get("serviceUrl"):
                    url = urlsplit(body["serviceUrl"])
                    local_url(f"{url.scheme}://{url.netloc}")
                conversation = body.get("conversation", {}).get("id")
                if (
                    not isinstance(conversation, str)
                    or not 1 <= len(conversation) <= 200
                ):
                    raise ValueError
        except (ValueError, TypeError, AttributeError):
            return web.json_response({"error": "local_playground_only"}, status=403)
        return await handler(request)

    app = web.Application(middlewares=[boundary], client_max_size=65536)

    async def messages(request):
        return await start_agent_process(request, agent, agent.adapter)

    async def health(_):
        return web.json_response(
            {"mode": "anonymous_local_playground", "sends_external_messages": False}
        )

    app.router.add_post("/api/messages", messages)
    app.router.add_get("/health", health)
    return app


def run_local(service: TraceService, *, port=3978):
    web.run_app(create_local_app(service), host="127.0.0.1", port=port, access_log=None)
