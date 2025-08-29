# This file runs a health check for the LLM, used on litellm/proxy

import asyncio
import logging
import random
from typing import List, Optional, TYPE_CHECKING

import litellm

logger = logging.getLogger(__name__)
from litellm.constants import HEALTH_CHECK_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from litellm.proxy._types import UserAPIKeyAuth

ILLEGAL_DISPLAY_PARAMS = [
    "messages",
    "api_key",
    "prompt",
    "input",
    "vertex_credentials",
    "aws_access_key_id",
    "aws_secret_access_key",
]

MINIMAL_DISPLAY_PARAMS = ["model", "mode_error"]


def _get_random_llm_message():
    """
    Get a random message from the LLM.
    """
    messages = ["Hey how's it going?", "What's 1 + 1?"]

    return [{"role": "user", "content": random.choice(messages)}]


def _clean_endpoint_data(endpoint_data: dict, details: Optional[bool] = True):
    """
    Clean the endpoint data for display to users.
    """
    endpoint_data.pop("litellm_logging_obj", None)
    return (
        {k: v for k, v in endpoint_data.items() if k not in ILLEGAL_DISPLAY_PARAMS}
        if details is not False
        else {k: v for k, v in endpoint_data.items() if k in MINIMAL_DISPLAY_PARAMS}
    )


def filter_deployments_by_id(
    model_list: List,
) -> List:
    seen_ids = set()
    filtered_deployments = []
    deployments_without_id = []

    for deployment in model_list:
        _model_info = deployment.get("model_info") or {}
        _id = _model_info.get("id") or None
        if _id is None:
            # Keep deployments without ID - don't filter them out
            deployments_without_id.append(deployment)
            continue

        if _id not in seen_ids:
            seen_ids.add(_id)
            filtered_deployments.append(deployment)

    # Return both filtered deployments with ID and all deployments without ID
    return filtered_deployments + deployments_without_id


async def run_with_timeout(task, timeout):
    try:
        return await asyncio.wait_for(task, timeout)
    except asyncio.TimeoutError:
        task.cancel()
        # Only cancel child tasks of the current task
        current_task = asyncio.current_task()
        for t in asyncio.all_tasks():
            if t != current_task:
                t.cancel()
        try:
            await asyncio.wait_for(task, 0.1)  # Give 100ms for cleanup
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass
        return {"error": "Timeout exceeded"}


async def _proxy_health_check(
    model_params: dict,
    mode: Optional[str] = None,
    user_api_key_dict: Optional["UserAPIKeyAuth"] = None,
) -> dict:
    """
    Perform health check through proxy request processing to ensure hooks are called.
    This is used when custom authentication or other hooks need to be executed.
    """
    try:
        from litellm.proxy.common_request_processing import ProxyBaseLLMRequestProcessing
        
        # Get proxy_logging_obj from proxy_server if available
        proxy_logging_obj = None
        try:
            from litellm.proxy.proxy_server import proxy_logging_obj as plo
            proxy_logging_obj = plo
        except ImportError:
            # If not available, create a minimal one
            from litellm.proxy.utils import ProxyLogging
            proxy_logging_obj = ProxyLogging()
        
        # Prepare the request data for health check
        health_check_data = {
            "model": model_params.get("model"),
            "messages": model_params.get("messages", _get_random_llm_message()),
            "max_tokens": 1,  # Minimal tokens for health check
            "temperature": 0,  # Consistent results
        }
        
        # Add any additional params that might be needed
        for key in ["api_key", "api_base", "api_version"]:
            if key in model_params:
                health_check_data[key] = model_params[key]
        
        # Create a minimal request processor
        request_processor = ProxyBaseLLMRequestProcessing(data=health_check_data)
        
        # Create a mock request object
        class MockRequest:
            def __init__(self):
                self.headers = {}
                self.method = "POST"
                self.url = type('MockURL', (), {'path': '/health'})()
                self.client = type('MockClient', (), {'host': 'localhost'})()
                self.state = type('MockState', (), {'route_cache': {}})()
                self.query_params = {}
        
        mock_request = MockRequest()
        
        if user_api_key_dict is None:
            # Create a basic user API key dict for health checks
            from litellm.proxy._types import UserAPIKeyAuth
            user_api_key_dict = UserAPIKeyAuth(
                api_key="health-check",
                user_id="health-check",
                user_role="proxy_admin",
                models=[],
                team_id=None,
            )
        
        # Process through proxy pre-call logic to execute hooks
        processed_data, logging_obj = await request_processor.common_processing_pre_call_logic(
            request=mock_request,
            general_settings={},
            user_api_key_dict=user_api_key_dict,
            proxy_logging_obj=proxy_logging_obj,
            proxy_config=type('MockProxyConfig', (), {})(),  # Empty proxy config
            route_type="acompletion",
        )
        
        # Now call the health check with processed data
        result = await litellm.ahealth_check(
            model_params=processed_data,
            mode=mode,
            prompt=processed_data.get("messages", [{"role": "user", "content": "test"}])[0].get("content", "test"),
            input=["test from litellm"],
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Proxy health check failed: {e}")
        # Fallback to direct health check if proxy processing fails
        return await litellm.ahealth_check(
            model_params=model_params,
            mode=mode,
            prompt="test from litellm",
            input=["test from litellm"],
        )


def _should_use_proxy_health_check() -> bool:
    """
    Determine if health checks should route through proxy hooks.
    Returns True if there are custom callbacks/hooks that need to be executed.
    """
    try:
        # Check if there are any custom callbacks configured
        if litellm.callbacks and len(litellm.callbacks) > 0:
            from litellm.integrations.custom_logger import CustomLogger
            
            # Check if any callbacks have async_pre_call_hook defined
            for callback in litellm.callbacks:
                if isinstance(callback, CustomLogger):
                    if (
                        hasattr(callback, 'async_pre_call_hook') and 
                        callback.__class__.async_pre_call_hook != CustomLogger.async_pre_call_hook
                    ):
                        return True
                        
        return False
    except Exception:
        # If we can't determine, err on the side of caution and don't use proxy
        return False


async def _perform_health_check(
    model_list: list, 
    details: Optional[bool] = True,
    user_api_key_dict: Optional["UserAPIKeyAuth"] = None
):
    """
    Perform a health check for each model in the list.
    Now supports routing through proxy hooks when custom authentication is needed.
    """
    use_proxy_health_check = _should_use_proxy_health_check()
    logger.debug(f"Using proxy health check: {use_proxy_health_check}")

    tasks = []
    for model in model_list:
        litellm_params = model["litellm_params"]
        model_info = model.get("model_info", {})
        mode = model_info.get("mode", None)
        litellm_params = _update_litellm_params_for_health_check(
            model_info, litellm_params
        )
        timeout = model_info.get("health_check_timeout") or HEALTH_CHECK_TIMEOUT_SECONDS

        if use_proxy_health_check:
            # Route through proxy to execute hooks
            task = run_with_timeout(
                _proxy_health_check(
                    model_params=litellm_params,
                    mode=mode,
                    user_api_key_dict=user_api_key_dict,
                ),
                timeout,
            )
        else:
            # Use direct health check (original behavior)
            task = run_with_timeout(
                litellm.ahealth_check(
                    model_params=litellm_params,
                    mode=mode,
                    prompt="test from litellm",
                    input=["test from litellm"],
                ),
                timeout,
            )

        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    healthy_endpoints = []
    unhealthy_endpoints = []

    for is_healthy, model in zip(results, model_list):
        litellm_params = model["litellm_params"]

        if isinstance(is_healthy, dict) and "error" not in is_healthy:
            healthy_endpoints.append(
                _clean_endpoint_data({**litellm_params, **is_healthy}, details)
            )
        elif isinstance(is_healthy, dict):
            unhealthy_endpoints.append(
                _clean_endpoint_data({**litellm_params, **is_healthy}, details)
            )
        else:
            unhealthy_endpoints.append(_clean_endpoint_data(litellm_params, details))

    return healthy_endpoints, unhealthy_endpoints


def _update_litellm_params_for_health_check(
    model_info: dict, litellm_params: dict
) -> dict:
    """
    Update the litellm params for health check.

    - gets a short `messages` param for health check
    - updates the `model` param with the `health_check_model` if it exists Doc: https://docs.litellm.ai/docs/proxy/health#wildcard-routes
    """
    litellm_params["messages"] = _get_random_llm_message()
    _health_check_model = model_info.get("health_check_model", None)
    if _health_check_model is not None:
        litellm_params["model"] = _health_check_model
    return litellm_params


async def perform_health_check(
    model_list: list,
    model: Optional[str] = None,
    cli_model: Optional[str] = None,
    details: Optional[bool] = True,
    user_api_key_dict: Optional["UserAPIKeyAuth"] = None,
):
    """
    Perform a health check on the system.

    Returns:
        (bool): True if the health check passes, False otherwise.
    """
    if not model_list:
        if cli_model:
            model_list = [
                {"model_name": cli_model, "litellm_params": {"model": cli_model}}
            ]
        else:
            return [], []

    if model is not None:
        _new_model_list = [
            x for x in model_list if x["litellm_params"]["model"] == model
        ]
        if _new_model_list == []:
            _new_model_list = [x for x in model_list if x["model_name"] == model]
        model_list = _new_model_list

    model_list = filter_deployments_by_id(
        model_list=model_list
    )  # filter duplicate deployments (e.g. when model alias'es are used)
    healthy_endpoints, unhealthy_endpoints = await _perform_health_check(
        model_list, details, user_api_key_dict
    )

    return healthy_endpoints, unhealthy_endpoints
