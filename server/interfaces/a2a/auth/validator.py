from fastmcp.server.dependencies import AccessToken
from fastmcp.server.auth import TokenVerifier
import os
import logging
# from auth.token_helper import TokenAuth as token


class CustomTokenVerifier(TokenVerifier):
    """
    Custom logic to verify the tokens. 
    This will verify the tokens issued from Console Manage Tokens service.
    """
    async def verify_token(self, token: str) -> AccessToken | None:
        valid_token = await check_token(token, ["search"])
        if valid_token:
            return AccessToken(token=token, scopes=["search"], client_id="mcp-client")
        else:
            return None


async def state_append(kwargs, value):
    if "state" in kwargs:
        kwargs["state"].append(value)
    else:
        kwargs["state"] = [value]
    return kwargs

async def check_token(ssid, _capability):
    """
    Veirfies the token is valid and has the required capabilities.
    Args:
        ssid: The token to verify
        _capability: The capabilities to verify
    Returns:
        True if the token is valid and has the required capabilities, False otherwise
    """
    MY_TOKEN = os.getenv('PUBLIC_TOKEN', '')
    if ssid == MY_TOKEN:
        return True
    else:
        return False
    # TODO: Implement the logic to verify the token and capabilities
    # db_obj = AsyncPostgresService(1, 'session.check_token')
    # query = "select subject, capabilities from token_management where token_id=%(ssid)s and " \
    #         "%(_capability)s && ARRAY[capabilities]"
    # validate_token = await db_obj.read_query(query=query,
    #                                         result_flag=True, params={'ssid': ssid, '_capability': _capability})
    # db_obj.close()
    # if validate_token:
    #     sessiondata = pickle.dumps(validate_token[0])
    #     with RedisHelper() as robj:
    #         robj.set_key_expiry(cons.SESSION_KEY_PREFIX + ssid, value=sessiondata, time=int(900))
    #     return True
    # else:
    #     logging.warning("session failed of the user")
    #     return False

# TODO: Implement the logic to verify the jwt token
# async def check_jwt(usr_token):
#     valid_f = token()
#     isvalid = await valid_f.validate_token(usr_token)
#     if isvalid:
#         return True
#     else:
#         logging.info("token authentication failed")
#         return False