from patch import get_patch, apply_patch_cover
import redis
from gRPC import DisServ_pb2
from gRPC import DisServ_pb2_grpc
from gRPC.atomScript import LuaScript
import os
import yaml
from concurrent import futures
import threading

# 1. 所有message类的定义在DisDerv_pb2中, 当要返回指定信息时，可以根据这些类初始化指定对象
# 2. 继承了servicer类之后, 需要完成service中定义的实现
# 3. 消息的解析方法参照DisDerv_pb2


'''
初始化信息类示例:
item = DisServ_pb2.single_patch_item(op = xxx, start_line = xxx, cont_line = xxx, cont = xxx)
访问信息类成员示例:
item.op
item.cont_line
etc...
'''


class server(DisServ_pb2_grpc.DisServServicer):
    def __init__(self):
        # 初始化服务器
        super(server, self).__init__()
        # 配置文件默认在src目录下
        self.server_conf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),"serCfg.yaml")
        with open(self.server_conf_path, 'r', encoding='utf-8') as f:
            cfg = yaml.load(f.read(), Loader=yaml.FullLoader)
        self.redisCli = redis.Redis(host=cfg["redis"]["host"],port=cfg["redis"]["port"],db=cfg["redis"]["db"])

        # 共享文档的路径
        self.share_path = cfg["share_path"]

        # 每个文档允许在内存中实时存储的补丁数量(k)
        self.k = cfg["num_patches"]

        # 初始化Lua脚本
        self.initial_scripts()

        # 确保用户ID分配操作的原子性
        self.ID_Info_mtx = threading.Lock()

        # 进行必要的redis初始化
        self.check_database()

    def initial_scripts(self):
        scripts = LuaScript()
        self.update_patch = self.redisCli.register_script(scripts.update_patch)
        self.init_share_doc = self.redisCli.register_script(scripts.init_share_doc)
        self.recall_doc = self.redisCli.register_script(scripts.recall_doc)


    def check_database(self):
        '''
        检查数据库中是否存在预设的键, 若没有则进行创建, 并初始化
        '''
        # 对10W量级以下的用户量, 单台服务器的内存量足以支撑以下Redis键值对的运作
        # 用户最大ID值--> max_usr_ID:: int
        # 用户列表--> usrlst(redis哈希表类型):: usr_ID:usr_name(str) 
        # 用户在线列表--> online_usr(redis集合类型):: usr_ID(int64) #没有必要维护在线状态
        # 共享文档列表--> share_doc(redis哈希表类型):: document_info(序列化):timestamp(int64)
        # 文档patch列表索引--> doc_patch(redis哈希表类型):: document_info(序列化):patchlistid
        # 文档patch列表--> patchlistid(redis列表类型):: patch(序列化)
        # 本地文档副本时间戳--> dup_doc_ver(redis哈希表类型):: document_info(序列化):timestamp(int64)
        # 最大patch列表ID值--> max_patch_list_ID:: int
        if not self.redisCli.exists("max_usr_ID"):
            self.redisCli.set("max_usr_ID", 0)
        if not self.redisCli.exists("usrlst"):
            self.redisCli.hset("usrlst"," "," ")
        if not self.redisCli.exists("share_doc"):
            self.redisCli.hset("share_doc", " ", " ")
        if not self.redisCli.exists("doc_patch"):
            self.redisCli.hset("doc_patch", " ", " ")
        if not self.redisCli.exists("dup_doc_ver"):
            self.redisCli.hset("dup_doc_ver", " ", " ")
        if not self.redisCli.exists("max_patch_list_ID"):
            self.redisCli.set("max_patch_list_ID",0)
        

        
        
    def upload_patch(self, request, context):
        # 完善自己的实现: 可以解析request，之后返回对应的类型
        '''
        request: patch类型信息,包含 <时间戳time_stamp, 申请客户信息appli_usr, 申请修改文档信息appli_doc, patch列表items>
        response: boolen_res类型信息, 象征性回复
        '''
        # 0. 首先检查对应的文档是否存在, 若不存在返回false, 暗示该文档已被移除
        # 1. 查询对应的patch时间戳, 匹配则进入下一步, 否则直接拒绝
        # 2. 成功写入, 则将该修改进行广播(在后续客户端每隔一段时间的轮询中进行)
        # * 要确保写入操作是原子的
        
        req_doc_info_serial = request.appli_doc.SerializeToString()
        
        
        if not self.redisCli.hexists("share_doc", req_doc_info_serial):
            return DisServ_pb2.boolen_res(accept_status = False)
        else:
            patch_serial = request.SerializeToString()
            time_stamp = request.time_stamp
            patch_Lst_ID = self.redisCli.hget("doc_patch", req_doc_info_serial)
            #-------原子操作区-------#
            # 传入share_doc键, 传入文档的info(序列化), 传入当前patch时间戳; 
            # 传入patch_Lst_ID键, 传入当前patch(序列化)
            # 
            self.redisCli.evalsha(self.update_patch, 2, "share_doc", patch_Lst_ID, 
                                  req_doc_info_serial, time_stamp, patch_serial)
            #------------------------#
            return DisServ_pb2.boolen_res(accept_status = True)

    def login(self, request, context):
        '''
        客户申请登录
        request: usr_info类型信息, 其中usr_ID字段若为-1,则说明从来登录过, 需要为其分配一个ID
        '''
        # 1. 查请求信息, 看是否登录过
        # 2. 若没有登录过, 则为其分配一个ID
        user_ID = request.usr_ID
        if user_ID == -1:
            #--------原子操作区-------#
            with self.ID_Info_mtx:
                curMaxID = self.redisCli.get("max_usr_ID")
                user_ID = curMaxID + 1
                self.redisCli.incr("max_usr_ID")
                self.redisCli.hset("usrlst", user_ID, request.usr_name)
            #------------------------#

        return DisServ_pb2.login_res(login_status = True, usr_ID = user_ID)

    
    def logout(self, request, context):
        '''
        客户申请离线(实际并没有什么用处, 所以闲置了)
        request: usr_info类型信息
        '''
        # 1. 将该用户从在线用户列表中移除
        # 2. 即便是该用户存在着尚未召回的共享文档, 也允许该用户离线
        # 3. 将该用户移入离线用户列表, 并写入离线时间(若超过一定时间仍未重新登录, 则判定为不活跃用户)
        return DisServ_pb2.boolen_res(accept_status = True)
        return super().logout(request, context)
    
    def upload_document(self, request, context):
        '''
        request: document类型信息
        '''
        # *因为普通文档大小较小, 这里不使用流式服务
        # *注意在上传文件的时候要初始化补丁列表
        # 1. 先在share文件夹下新建一个文件, 命名格式为(用户ID-文件描述符-文件名)
        # 2. 之后接收数据, 将数据写入文件, 写入完毕后, 初始化对应的补丁列表
        # 3. 返回确认


        # 先检查有没有上传过同一个文件
        doc_info_serial = request.doc_info.SerializeToString()
        if self.redisCli.hexists("share_doc",doc_info_serial):
            return DisServ_pb2.boolen_res(accept_status = False)
        doc_info = request.doc_info
        doc_name = "-".join([str(doc_info.doc_ownerID), doc_info.doc_descriptor, doc_info.doc_name])
        doc_path = os.path.join(self.share_path, doc_name)
        
        with open(doc_path,"w",encoding="utf-8") as doc:
            doc.write('\n'.join(request.content))
        
        # 文件写入成功, 接下来开始原子操作:
        # 1. 共享文档列表share_doc添加该新文件, 时间戳更新为0
        # 2. 访问max_patch_list_ID, 为其分配一个patch列表ID, 之后进行自增
        # 3. 创建一个列表类型的键值对patch-<ID>
        #-----------原子操作区--------#
        # 传入share_doc键, 将当前文档info(序列化)传入
        # 传入max_patch_list_ID键, 获取patch_ID
        # 传入doc_patch键, 将获取的patch_ID插入(这里只要获取patch_ID就行,因为空列表是无意义的)
        # 传入dup_doc_ver键, 对其进行初始化
        self.redisCli.evalsha(self.init_share_doc, 4, "share_doc", "max_patch_list_ID", "doc_patch","dup_doc_ver",
                              doc_info_serial)
        #----------------------------#
        return DisServ_pb2.boolen_res(accept_status = True)
    

    def recall_document(self, request, context):
        '''
        request: document_info类型信息
        '''
        # 1. 将该文档文件从服务器删除
        # 2. 将文档信息从共享列表中移除
        # 3. 将补丁列表删除后, 将文档从doc_patch删除
        # 4. 通知其他用户, 我已经撤回了该文件, 该文件不可在线修改(在后续请求补丁的时候通知)

        file_name = "-".join([str(request.doc_ownerID), request.doc_descriptor, request.doc_name])
        file_path = os.path.join(self.share_path, file_name)

        # 这里可能会有点问题: 当有客户在请求当前文档时, 删除失败
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                doc_info = request.SerializeToString()
                if not self.redisCli.hexists("share_doc", doc_info):
                    return DisServ_pb2.boolen_res(accept_status = False)

                # 这里不做原子操作的话, 有脏读取的风险
                #---------原子操作区---------#
                # 传入share_doc键, 传入doc_info(序列化), 删除doc_info(序列化)
                # 传入doc_patch键, 根据doc_info获取对应的列表ID, 删除列表后再删除该域
                # 传入dup_doc_ver键, 对其进行删除
                self.redisCli.evalsha(self.recall_doc, 2, "share_doc", "doc_patch",
                                    doc_info)
                #---------------------------#
                return DisServ_pb2.boolen_res(accept_status = True)
            except PermissionError:
                # 删除失败, 返回失败标识
                return DisServ_pb2.boolen_res(accept_status = False)

    def request_for_document(self, request, context):
        '''
        request: document_info类型信息
        '''
        # 1. 这里首先检查请求文档还存不存在(直接通过相关数据找目录)
        # 2. 存在的话, 将文档读入, 转化为document类型
        # 3. 这里的异常情况那可太多了, 后期有时间的时候应该再考虑考虑
        file_name = "-".join([str(request.doc_ownerID), request.doc_descriptor, request.doc_name])
        file_path = os.path.join(self.share_path, file_name)
        if os.path.exists(file_path):
            try:
                file_content = []
                with open(file_path, "r", encoding="utf-8") as doc:
                    # 这里在读文件时自动去掉末尾所有空白字符, 在客户端进行diff操作时, 也应该遵循一样的原则
                    for line in doc:
                        file_content.append(line.strip())
                
                doc_info_serial = request.SerializeToString()
                if self.redisCli.hexists("share_doc", doc_info_serial) and self.redisCli.hexists("dup_doc_ver", doc_info_serial):
                # 说明还没被删除, 赶紧传输
                    ts = self.redisCli.hget("dup_doc_ver", doc_info_serial)
                    return DisServ_pb2.document(doc_info = request, time_stamp = ts, content = file_content)
                    
            except PermissionError:
                pass
        # doc_info = DisServ_pb2.document_info(doc_name="NULL",doc_descriptor="NULL",doc_ownerID=-1)
        # 时间戳为-1说明该文件已经无了
        return DisServ_pb2.document(time_stamp=-1)
        
    
    def request_for_patch(self, request, context):
        '''
        request类型: patch
        '''
        # * 需要找出客户当前版本与目前最新版本之间的所有补丁
        # * 即使产生污染读的情况也没关系, 因为后续客户还会进行轮询, 以保持文档的一致性
        # * 可能需要应付在请求补丁时, 发生文件变动(意外丢失文件或者文件被撤销共享)而产生的异常

        # 首先一口气获取所有patch
        ts = request.time_stamp
        doc_info = request.appli_doc.SerializeToString()
        patch_key = self.redisCli.hget("doc_patch", doc_info)
        patches = self.redisCli.lrange(patch_key,0,-1)

        # 之后, 根据时间戳的条件, 流式地发布时间戳超前于客户版本的补丁
        for patch in patches:
            patch = DisServ_pb2.patch().ParseFromString(patch)
            if patch.time_stamp > ts:
                yield patch
        
        return
    

    def request_for_sharelist(self, request, context):
        '''
        request类型: 象征性的boolen_res
        '''
        # 一键获取当前share_doc的所有键(list)
        fields = self.redisCli.hkeys("share_doc")

        doc_lst = []
        # 打包成doc_lst类型信息
        for item in fields:
            cur_info = DisServ_pb2.document_info()
            cur_info.ParseFromString(item)
            doc_lst.append(cur_info)
        return DisServ_pb2.doc_list(doc_info_list = doc_lst)

    



# def is_same_doc(doc_info1:DisServ_pb2.document_info, doc_info2:DisServ_pb2.document_info):
#     return doc_info1.doc_name == doc_info2.doc_name and doc_info1.doc_descriptor == doc_info2.doc_descriptor and doc_info1.doc_ownerID == doc_info2.doc_ownerID
