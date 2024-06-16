import os
import sys
cur_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(cur_dir, "gRPC"))
from patch import get_patch, apply_patch_cover
import redis
from gRPC import DisServ_pb2
from gRPC import DisServ_pb2_grpc
from gRPC.atomScript import LuaScript
import grpc

import yaml
from concurrent import futures
import threading
import time

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
        # 配置文件默认在src的cfg目录下
        self.server_conf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),"cfg/serCfg.yaml")
        with open(self.server_conf_path, 'r', encoding='utf-8') as f:
            cfg = yaml.load(f.read(), Loader=yaml.FullLoader)
        self.redisCli = redis.Redis(host=cfg["redis"]["host"],port=cfg["redis"]["port"],db=cfg["redis"]["db"])

        # 共享文档的路径
        self.share_path = cfg["share_path"]

        # 每个文档允许在内存中实时存储的补丁数量下限(k)
        self.k = cfg["num_patches"]

        # 文档版本与最新补丁相差超过该阈值, 才会写入修改
        self.threshold = cfg["threshold"]

        # 规定服务器的监听端口
        self.serPort = cfg["listen_port"]

        # 初始化Lua脚本
        self.initial_scripts()

        # 确保用户ID分配操作的原子性
        self.ID_Info_mtx = threading.Lock()

        # 确保文件批量写入补丁操作和请求文件操作的互斥
        self.doc_mtx = threading.Lock()

        # 进行必要的redis初始化
        self.check_database()

        maintain_th = threading.Thread(target=self.maintain_th)
        maintain_th.start()

    def initial_scripts(self)-> None:
        '''
        初始化并注册Lua脚本
        '''
        scripts = LuaScript()
        self.update_patch = self.redisCli.register_script(scripts.update_patch)
        self.init_share_doc = self.redisCli.register_script(scripts.init_share_doc)
        self.recall_doc = self.redisCli.register_script(scripts.recall_doc)


    def check_database(self)-> None:
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
            keys = ["share_doc", patch_Lst_ID]
            args = [req_doc_info_serial, time_stamp, patch_serial]
            self.update_patch(keys=keys, args=args)
            #------------------------#

            # 无需关心是否成功写入, 因为服务器总是会发布最新的一致补丁
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
                user_ID = int(curMaxID) + 1
                self.redisCli.incr("max_usr_ID")
                self.redisCli.hset("usrlst", user_ID, request.usr_name)
            #------------------------#

        return DisServ_pb2.login_res(login_status = True, usr_ID = user_ID)

    
    def logout(self, request, context):
        '''
        客户申请离线(实际并没有什么用处, 所以闲置了, 仅做了象征性的实现)
        request: usr_info类型信息
        '''
        # 1. 将该用户从在线用户列表中移除
        # 2. 即便是该用户存在着尚未召回的共享文档, 也允许该用户离线
        # 3. 将该用户移入离线用户列表, 并写入离线时间(若超过一定时间仍未重新登录, 则判定为不活跃用户)
        return DisServ_pb2.boolen_res(accept_status = True)
        
    
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
            # -做检查, 查看本地文件是否还存在, 若不存在, 就需要接收
            # -若存在, 就算了
            return DisServ_pb2.boolen_res(accept_status = True)
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
        keys = ["share_doc","max_patch_list_ID", "doc_patch","dup_doc_ver"]
        args = [doc_info_serial]
        self.init_share_doc(keys=keys, args=args)
        #----------------------------#
        # 再检查一遍, 若成功写入就返回成功, 若没有则返回错误
        if self.redisCli.hexists("share_doc", doc_info_serial):
            return DisServ_pb2.boolen_res(accept_status = True)
        else:
            return DisServ_pb2.boolen_res(accept_status = False)
    

    def recall_document(self, request, context):
        # TODO: 修复下面提到的bug
        #这里有点问题: 在撤回文档之前, 应当确保将最新版本的副本同步到文档拥有者, 在此之前, 应当将某些键锁住#
        #返回的类型应该更改为document
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
                
                doc_info = request.SerializeToString()
                if not self.redisCli.hexists("share_doc", doc_info):
                    return DisServ_pb2.boolen_res(accept_status = False)

                # 这里不做原子操作的话, 有脏读取的风险
                #---------原子操作区---------#
                # 传入share_doc键, 传入doc_info(序列化), 删除doc_info(序列化)
                # 传入doc_patch键, 根据doc_info获取对应的列表ID, 删除列表后再删除该域
                # 传入dup_doc_ver键, 对其进行删除
                keys = ["share_doc", "doc_patch"]
                args = [doc_info]
                self.recall_doc(keys=keys, args=args)
                #---------------------------#
                os.remove(file_path)
                return DisServ_pb2.boolen_res(accept_status = True)
            except PermissionError:
                # 删除失败, 返回失败标识
                return DisServ_pb2.boolen_res(accept_status = False)

    # 还没debug
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
                # 等待所有将补丁写入的操作完成
                with self.doc_mtx:
                    with open(file_path, "r", encoding="utf-8") as doc:
                        # 这里在读文件时自动去掉末尾所有空白字符, 在客户端进行diff操作时, 也应该遵循一样的原则
                        for line in doc:
                            file_content.append(line.rstrip())
                    
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
        
    
    # 还没debug, 或者说, 没de过真的有上传patch的bug
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
        #--原子操作--(可能需要另写一个Lua脚本确保操作原子性)
        patch_key = self.redisCli.hget("doc_patch", doc_info)
        patches = self.redisCli.lrange(patch_key,0,-1)


        # 之后, 根据时间戳的条件, 流式地发布时间戳超前于客户版本的补丁
        #  😢这里需要修改: 若当前版本的下一个补丁没有出现在补丁列表时, 则返回相应的patch做提醒, 使客户端自主调用
        #     request_for_document获取最新版本的副本

        is_continuous = False
        for patch_ in patches:
            patch = DisServ_pb2.patch()
            patch.ParseFromString(patch_)
            # 判断是否有补丁恰好是当前版本的下一个版本
            if patch.time_stamp == ts + 1:
                is_continuous = True
            # 若已经存在当前版本的下一个补丁, 那么将之后的所有补丁都上传
            if is_continuous and patch.time_stamp > ts:
                yield patch
            # 否则, 说明当前版本太老了, 返回一个时间戳为-1的信息, 提醒用户重新获取副本
            elif patch.time_stamp > ts:
                yield DisServ_pb2.patch(time_stamp = -1)
                break
        
        return
    
    
    def request_for_sharelist(self, request, context):
        '''
        request类型: 象征性的boolen_res
        返回类型: doc_list
        '''
        # 一键获取当前share_doc的所有键(list)
        fields = self.redisCli.hkeys("share_doc")
        doc_lst = []
        # 打包成doc_lst类型信息
        for item in fields:
            # 这里鬼打墙纯属自己坑自己, 因为引入了空键' '
            if item.decode() != ' ':
                cur_info = DisServ_pb2.document_info()
                cur_info.ParseFromString(item)
                doc_lst.append(cur_info)
        return DisServ_pb2.doc_list(doc_info_list = doc_lst)

    def maintain_th(self):
        # 每隔一段时间就调用一次, 尽量使每次间隔都不一样
        time_gaps = [0.3,0.9,2.1,0.9,1.1]
        gap_idx = 0
        while True:
            self.maintain_dup_doc()
            time.sleep(time_gaps[gap_idx])
            gap_idx += 1
            gap_idx %= len(time_gaps)



# TODO: 实现一个线程, 时刻维护服务器文件副本的版本, 这事实上是一个极度消耗性能的操作, 同时也会使服务器的
#       应答能力下降, 因为互斥此时服务器无法处理上传文件的业务
    def maintain_dup_doc(self):
        # 1. 获取文件列表-->2. 获取补丁列表-->3. 迭代式地写入

        doc_infos_serial = self.redisCli.hkeys("share_doc")
        # 与获取文件的操作互斥
        with self.doc_mtx:
            # 对所有文件, 遍历其补丁列表
            for doc_info_serial in doc_infos_serial:
                if doc_info_serial.decode() != " ":
                    cur_ts = int(self.redisCli.hget("dup_doc_ver", doc_info_serial))
                    patchLstID = self.redisCli.hget("doc_patch",doc_info_serial)
                    patchLst_serial = self.redisCli.lrange(patchLstID, 0, -1)
                    # 批量转成patch

                    # 这里有很大的问题！！！！！ 但是已经做了初步的修改
                    patchLst = []
                    for patch in patchLst_serial:
                        single_patch = DisServ_pb2.patch()
                        single_patch.ParseFromString(patch)
                        patchLst.append(single_patch)
                    
                    try:
                        gap = patchLst[-1].time_stamp - cur_ts
                        # 满足阈值条件, 开始写入
                        if gap > self.threshold:
                            doc_info = DisServ_pb2.document_info().ParseFromString(doc_info_serial)
                            file_path = os.path.join(self.share_path, 
                                                    "-".join(str(doc_info.doc_ownerID), doc_info.doc_descriptor, doc_info.doc_name))
                            
                            if os.path.exists(file_path):
                                # 若文件存在, 开始进行补丁的写入
                                raw_file = []
                                with open(file_path, "r", encoding="utf-8") as file:
                                    raw_file.append(line.rstrip() for line in file)
                                for i in range(len(patchLst)-gap, len(patchLst)):
                                    raw_file = apply_patch_cover(patchLst[i], raw_file)
                                with open(file_path, "w", encoding="utf-8") as file:
                                    file.write('\n'.join(raw_file))
                                self.redisCli.hset("dup_doc_ver", doc_info_serial, patchLst[-1].time_stamp)

                                # 开始维护补丁列表的数量
                                if len(patchLst) > self.k:
                                    self.redisCli.ltrim(patchLstID, -self.k, -1) 
                            else:
                                # TODO: 等待实现错误提示, 以及文件恢复的操作(后续有时间再做)
                                # 文件恢复的操作应该留在请求补丁处, 之后通过某种机制, 确保只有一个用户发送副本
                                pass
                    except IndexError:
                        # 说明逻辑错误了, 原子操作失效, 补丁列表已经清空, 但文档信息还在
                        pass



if __name__ == "__main__":
    ServerHandel = server()
    Server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    SerPort = ServerHandel.serPort
    DisServ_pb2_grpc.add_DisServServicer_to_server( ServerHandel,Server)
    Server.add_insecure_port('[::]:'+str(SerPort))
    Server.start()
    Server.wait_for_termination()
    pass