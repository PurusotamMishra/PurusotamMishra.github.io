# import sys
# sys.setrecursionlimit(1000)
# import jwt
# import ast
# import datetime
# import os
# import logging

# from helpers.redis_helper import RedisHelper
# # from config_loader import redis_config as conf
# from config_loader import system_config
# conf = system_config.reload_config()
# tenant_id = conf['system']['tenant_id']


# class TokenAuth:
#     __instance = None

#     @staticmethod
#     def get_instance():
#         """ Static access method. """
#         if TokenAuth.__instance is None:
#             TokenAuth()
#         return TokenAuth.__instance

#     def __init__(self):
#         """ Virtually private constructor. """
#         TokenAuth.__instance = self
#         # co_data = system_config.reload_config()
#         self.tenant_id = tenant_id

#     async def redis_manage(self, token, comp_id, secret=None, flag=False):
#         try:
#             key = self.tenant_id + "_token_" + comp_id
#             if secret and flag:
#                 with RedisHelper() as robj:
#                     robj.delete_key(key)
#             else:
#                 # Store data in a consistent format
#                 data = str({'token': token, 'secret': secret}).encode('utf-8')
#                 with RedisHelper() as robj:
#                     robj.set_key(key, data)
#         except Exception as e:
#             logging.error("# Error while storing token: {} #".format(str(e)))
#             raise Exception(str(e))

#     @staticmethod
#     def build_resp_obj(source, status_msg, status_code):
#         fmt = "%Y-%m-%dT%H:%M:%S"
#         stamp = datetime.datetime.now().strftime(fmt)
#         resp = {"data": source, "status": status_msg, "status_code": status_code, "TStamp": stamp}
#         return resp

#     async def generate_token(self, subject, secret, comp_id, expiry=30):
#         """
#            Generates the Auth Token
#            :return: dict
#        """
#         try:
#             comp_id = str(comp_id)
#             key = self.tenant_id + "_token_" + comp_id
#             with RedisHelper() as robj:
#                 stored_token = robj.get_key(key)
            
#             if stored_token:
#                 try:
#                     # Handle binary data properly
#                     token_str = stored_token.decode('utf-8')
#                     token_data = ast.literal_eval(token_str)
#                     token = token_data['token']
#                 except (UnicodeDecodeError, ValueError) as e:
#                     logging.error(f"Error decoding stored token: {e}")
#                     # If we can't decode the stored token, generate a new one
#                     token = None
            
#             if not stored_token or not token:
#                 iat = datetime.datetime.now()
#                 payload = {
#                     'iat': iat,
#                     'sub': subject
#                 }
#                 token = jwt.encode(
#                     payload,
#                     '{}'.format(secret),
#                     algorithm='HS256'
#                 )
#                 # Store the new token
#                 await self.redis_manage(token=token, comp_id=comp_id, secret=secret)
            
#             return self.build_resp_obj(token, "Token generated successfully", 200)
#         except Exception as e:
#             logging.error("# Error in token generation: {} #".format(str(e)))
#             return self.build_resp_obj(str(e), "Failed to generate token", 500)

#     async def validate_token(self, token):

#         """
#                Validate the Auth Token
#                :return: True/False
#        """
#         try:
#             try:
#                 token, comp_id = token.split("|||")
#             except ValueError as e:
#                 token = token.split("|||")
#                 comp_id = token.pop(-1)
#                 token = "|||".join(token)
#             with RedisHelper() as robj:
#                 token_dct = robj.get_key(self.tenant_id + "_token_" + comp_id)
#             if token_dct:
#                 try:
#                     token_dct = ast.literal_eval(token_dct.decode())
#                     secret = token_dct['secret']
#                     if secret:
#                         token_detail = jwt.decode(token, secret, 'HS256')
#                         result = dict()
#                         result['CreatedOn'] = datetime.datetime.utcfromtimestamp(token_detail["iat"]).isoformat()
#                         # result['Expires'] = datetime.datetime.utcfromtimestamp(token_detail["exp"]).isoformat()
#                         result['IsValid'] = True
#                         return result
#                     else:
#                         return False
#                 except jwt.ExpiredSignatureError:
#                     await self.expire_token(token, comp_id)
#                     return False
#                     # 'Signature expired. Please log in again.'
#                 except jwt.InvalidTokenError:
#                     await self.expire_token(token, comp_id)
#                     return False
#             else:
#                 logging.debug('No token found')
#                 return False
#         except Exception as e:
#             logging.error("Error in validating jwt token: {}".format(e))
#             # return 'Invalid token. Please log in again.'

#     async def expire_token(self, token, comp_id):
#         """
#            Expire the provide Auth Token
#            :return: True/False
#         """
#         try:
#             await self.redis_manage(token=token, comp_id=comp_id, secret='delete', flag=True)
#             return self.build_resp_obj("success", "Token expired", 200)
#         except Exception:
#             return False
