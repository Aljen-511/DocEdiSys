from patch import get_patch, apply_patch_cover
from gRPC import DisServ_pb2
from gRPC import DisServ_pb2_grpc

# server职能
# 1. 维护用户列表(set)
# 2. 记录所有在线文档的最近k个patch
# 3. 正常下线之前，我需要告知所有用户我下线了(或者等待用户发现我意外下线了,自动终止他们对当前文档的编辑)
# 4. 维护在线用户列表(set)
# 5. 维护在线文档列表(set)
# 6. 维护文档共享列表(set)
# 7. 维护在线文档时间戳列表
# 


# rpc方法:
# ------server持有--------
# 1. accept_login()做好用户登录工作，返回必要的共享文档列表
# 2. upload_document()接收用户上传的共享文档信息，广播给所有在线用户文档描述符
# 3. recall_document()召回用户上传的共享文档，撤销所有正在使用该文档用户的使用权
# 4. request_for_document()某用户请求对某文档进行操作
# 5. upload_patch()把用户自己对某文档的patch上传到patch列表
# 6. obtain_newest_duplication()在用户发现服务器的patch无法覆盖自身的修改范围时，请求从文档拥有者获取最新的patch
# 7. forcing_consistency()文档拥有者掉线并重新上线之后，强制用自己的旧版本覆盖所有持有者的副本(代价极高)
# -------client持有--------
# 1. fork_duplication()将本地的文档和对应时间戳备份发送给共享文档请求者
# 
# redis的修改期限改为1分钟5次或者10分钟20次



##### redis存储序列化message类型与反序列化后取值示例
'''
import redis
import my_message_pb2  # 导入自动生成的 Protocol Buffers 代码

# 连接到 Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# 创建自定义消息对象
message = my_message_pb2.MyMessage()
message.id = 123
message.name = "Hello, gRPC!"

# 将消息对象序列化为字节流
serialized_message = message.SerializeToString()

# 将序列化后的字节流存储在 Redis 中
redis_client.set('my_message', serialized_message)

# 从 Redis 中获取存储的字节流
stored_message_bytes = redis_client.get('my_message')

# 将获取的字节流反序列化为消息对象
stored_message = my_message_pb2.MyMessage()
stored_message.ParseFromString(stored_message_bytes)

print("ID:", stored_message.id)
print("Name:", stored_message.name)
'''



'''
# 服务器端直接终止流的示例
def client_stream_example():
    channel = grpc.insecure_channel('localhost:50051')
    stub = streaming_service_pb2_grpc.StreamServiceStub(channel)
    try:
        response_iterator = stub.ServerStream(streaming_service_pb2.ClientRequest(message="Hello"))
        for response in response_iterator:
            print("Received message from server:", response.response)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.CANCELLED:
            print("Server stream cancelled by the server")
        else:
            print("Unexpected error:", e)
'''
class client():
    def  __init__(self) -> None:
        pass
