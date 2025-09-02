# 403 Error Logging Analysis in LiteLLM

## Problem Statement

The issue was to find where 403 messages are logged and where this specific message would likely be logged from:

```
Error code: 403 - {'error': {'message': 'litellm.APIError: APIError: OpenAIException - <HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n \nYou don\'t have permission to access "http&#58;&#47;&#47;npe&#46;aigw&#46;<my-co>&#46;com&#47;<my-org>&#47;dev01&#47;oai&#47;v1&#47;chat&#47;completions" on this server.<P>\nReference&#32;&#35;18&#46;8ad02e17&#46;1756833048&#46;1096b0d4\n<P>https&#58;&#47;&#47;errors&#46;edgesuite&#46;net&#47;18&#46;8ad02e17&#46;1756833048&#46;1096b0d4</P>\n</BODY>\n</HTML>. Received Model Group=<prefix>/gpt-5\nAvailable Model Group Fallbacks=None', 'type': None, 'param': None, 'code': '403'}}
```

## Analysis Summary

This error message is the result of a 5-step flow through LiteLLM's exception handling system. The 403 error originates from an HTTP access denied response and gets progressively wrapped and formatted through multiple layers.

## Detailed Flow

### Step 1: Original HTTP 403 Error
- **Source**: Target API endpoint (e.g., OpenAI-compatible service)
- **Content**: HTML access denied page with 403 status code
- **Example**: 
  ```html
  <HTML><HEAD>
  <TITLE>Access Denied</TITLE>
  </HEAD><BODY>
  <H1>Access Denied</H1>
  You don't have permission to access "http://..." on this server.
  </BODY></HTML>
  ```

### Step 2: OpenAI Client Exception
- **Source**: OpenAI Python client library
- **Location**: External dependency (not LiteLLM code)
- **Action**: Receives 403 HTTP response and creates exception
- **Format**: `"Error code: 403 - {'error': {'message': '<HTML_CONTENT>', 'type': 'access_denied', 'param': None, 'code': 'access_denied'}}"`

### Step 3: LiteLLM Exception Mapping
- **Source**: `litellm/litellm_core_utils/exception_mapping_utils.py`
- **Function**: `exception_type()` (lines 172-2000+)
- **Key Logic**:
  ```python
  # Lines 318-319: Set exception provider name
  if custom_llm_provider == "openai":
      exception_provider = "OpenAI" + "Exception"  # = "OpenAIException"
  
  # Lines 526-535: Handle unmapped status codes (including 403)
  else:
      exception_mapping_worked = True
      raise APIError(
          status_code=original_exception.status_code,  # 403
          message=f"APIError: {exception_provider} - {message}",  # "APIError: OpenAIException - ..."
          llm_provider=custom_llm_provider,
          model=model,
          request=getattr(original_exception, "request", None),
          litellm_debug_info=extra_information,
      )
  ```

### Step 4: APIError Class Formatting
- **Source**: `litellm/exceptions.py`
- **Class**: `APIError` (lines 555-590)
- **Key Logic**:
  ```python
  # Line 568: Format the final message
  self.message = "litellm.APIError: {}".format(message)
  ```
- **Result**: `"litellm.APIError: APIError: OpenAIException - {original_message}"`

### Step 5: Router Fallback Information
- **Source**: `litellm/router.py`
- **Function**: `async_function_with_fallbacks_common_utils()` (line 3664+)
- **Key Logic**:
  ```python
  # Lines 3842-3845: Add model group information
  if hasattr(original_exception, "message"):
      original_exception.message += ". Received Model Group={}\nAvailable Model Group Fallbacks={}".format(
          model_group,
          fallback_model_group,
      )
  ```

### Step 6: Proxy Exception Handler
- **Source**: `litellm/proxy/proxy_server.py`
- **Function**: `openai_exception_handler()` (lines 779-795)
- **Key Logic**:
  ```python
  return JSONResponse(
      status_code=int(exc.code) if exc.code else status.HTTP_500_INTERNAL_SERVER_ERROR,
      content={
          "error": {
              "message": exc.message,
              "type": exc.type,
              "param": exc.param,
              "code": exc.code,
          }
      },
      headers=headers,
  )
  ```

## Key Files for 403 Error Handling

| File | Line(s) | Purpose |
|------|---------|---------|
| `litellm/litellm_core_utils/exception_mapping_utils.py` | 318-319 | Sets `exception_provider = "OpenAIException"` |
| `litellm/litellm_core_utils/exception_mapping_utils.py` | 526-535 | Maps 403 status codes to `APIError` |
| `litellm/exceptions.py` | 567-568 | `APIError` class message formatting |
| `litellm/router.py` | 3842-3845 | Adds model group fallback information |
| `litellm/proxy/proxy_server.py` | 779-795 | Creates final JSON error response |

## Exception Type Hierarchy

For 403 errors with OpenAI provider:

1. **No specific 403 handling**: Unlike 401, 404, 429, etc., there's no explicit handling for 403 status codes in the OpenAI provider mapping
2. **Falls to default case**: 403 errors go to the `else` clause that creates a generic `APIError`
3. **Could be improved**: 403 errors could be mapped to `PermissionDeniedError` instead of generic `APIError`

## Logging Locations

The 403 error gets logged at multiple points:

1. **Exception Mapping**: When the original exception is processed
2. **Router Failure Handling**: When fallbacks are attempted/failed
3. **Proxy Logging**: Through the `ProxyLogging` class failure handlers
4. **Final Response**: As the JSON error response to the client

## Potential Improvements

1. **Add explicit 403 handling** in `exception_mapping_utils.py`:
   ```python
   elif original_exception.status_code == 403:
       exception_mapping_worked = True
       raise PermissionDeniedError(
           message=f"PermissionDeniedError: {exception_provider} - {message}",
           llm_provider=custom_llm_provider,
           model=model,
           response=getattr(original_exception, "response", None),
           litellm_debug_info=extra_information,
       )
   ```

2. **Improve HTML content handling** for better error messages when APIs return HTML error pages

3. **Add specific logging** for 403 errors to distinguish them from other API errors

## Test Case

A test case has been created in `test_403_error_investigation.py` that reproduces the exact error format and demonstrates the complete flow from HTTP 403 to final logged message.