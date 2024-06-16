import grpc._channel
from patch import get_patch, apply_patch_cover
from gRPC import DisServ_pb2
from gRPC import DisServ_pb2_grpc
import redis
import hashlib
import yaml
import os
import time
import threading
import grpc
from google.protobuf.json_format import  ParseDict


# 客户端基本不用考虑多线程和互斥的事情, 真好😎
class client():
    def  __init__(self):

        self.cli_conf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cfg/cliCfg.yaml")
        with open(self.cli_conf_path, 'r', encoding="utf-8") as f:
            cfg = yaml.load(f.read(),Loader=yaml.FullLoader)
        self.redisCli = redis.Redis(host=cfg["redis"]["host"], port=cfg["redis"]["port"],db=cfg["redis"]["db"])
        
        # 副本缓存路径
        self.cache_path = cfg["cache_path"]
        # 存储服务器的端口和IP
        self.ser_ip = None
        self.ser_port = None

        # 版本维护线程的单循环周期
        self.basic_maintain_loop = cfg["basic_maintain_loop"]
        # 文档的最大等待更新周期数
        self.max_periods = cfg["max_update_period_nums"]

        
        # 最近的编辑文档的更新周期列表
        self.latest_doc = {}
        # 最近编辑文档的剩余等待更新的最小周期数
        self.duration_left = {}
        # 数据库的必要初始化
        self.check_database()

        # 当前正在编辑的文档(信息)
        self.cur_edit_doc = None #(unique_doc_indicator序列化)
        # 当前正在编辑的文档(内容)
        self.cur_edit_doc_cont = None

        # 当前正在编辑文档的互斥锁: 保证应用补丁操作和上传补丁操作的互斥, 以及其他敏感操作的互斥
        self.edit_mtx = threading.Lock()
        # 共享文档读写的互斥锁: 保证没有脏读取(共享文档在应用完补丁之后, 才会被读取到编辑区)
        self.share_mtx = threading.Lock()
        
        # 创建与服务器的连接
        self.channel = None

        # 当前用户名
        self.usr_name = None
        # 当前用户ID
        self.usr_ID = None



        # 是否继续对服务器的补丁轮询, 当主动断开与服务器的连接时置为False
        self.keepCatching = True

        pass
    
    def check_database(self)->None:
        '''
        检查数据库中是否存在预设的键, 若没有则进行创建, 并初始化
        
        - 本地文件副本版本列表(通过doc_info查询时间戳)--> dup_doc_ver(哈希表类型):: document_info(序列化): timestamp
        - 对应服务器的IP--> profile_info(哈希表类型):: ser_ip(字符串类型的ipv4地址): user_info(序列化)
        - 本地共享文档列表--> sharing_doc(哈希表类型):: document_info(序列化): 文档路径(字符串)
        - ***这一项直接由内存中的哈希表维护***最近编辑文件列表--> latest_doc(哈希表类型):: document_info(序列化): 更新周期数(int) 
        - ***由内存中的哈希表维护***文件列表的剩余等待周期--> duration_left:: document_info(序列化): 还剩下的更新周期
        
        更正: 这里的doc_info都是加上服务器IP信息的doc_info(序列化的unique_doc_indicator), 否则会引发混乱
        '''
        # 鉴于修改操作的高频程度, 这里决定将当前正在编辑的文档内容放入内存
        if not self.redisCli.exists("dup_doc_ver"):
            self.redisCli.hset("dup_doc_ver", " ", " ")
        if not self.redisCli.exists("profile_info"):
            self.redisCli.hset("profile_info"," ", " ")
        if not self.redisCli.exists("sharing_doc"):
            self.redisCli.hset("sharing_doc"," "," ")
        else:
            doc_info_lst = self.redisCli.hkeys("sharing_doc")
            for doc_info_serial in doc_info_lst:
                if doc_info_serial.decode() != " ":
                    self.latest_doc[doc_info_serial] = 1
                    self.duration_left[doc_info_serial] = 1
        
            
    def login(self, serverIP:str, serverPort:int, usr_name:str)-> bool:
        self.channel = grpc.insecure_channel(":".join([serverIP,str(serverPort)]))

        if self.redisCli.hexists("profile_info",serverIP):
            usr_ID = int(self.redisCli.hget("profile_info", serverIP))
        else:
            usr_ID = -1
        usr_info = DisServ_pb2.usr_info(usr_name = usr_name, usr_ID = usr_ID)
        stub = DisServ_pb2_grpc.DisServStub(self.channel)
        # 尝试请求服务, 若失败说明断联
        try:
            login_res = stub.login(usr_info)
        except grpc.RpcError as error_code:
            return False
        
        if login_res.login_status:
            self.redisCli.hset("profile_info", serverIP, login_res.usr_ID)
            self.usr_name = usr_name
            self.usr_ID = login_res.usr_ID
            self.ser_ip = serverIP
            self.ser_port = serverPort
            return True
        return False





    # 负责访问某个文档(文档信息从共享列表中得知, 被前端调用, 这里应该禁止访问正在编辑的文档)
    def access_document(self, doc_info_dict:dict = None)-> list[str]:
        '''
        该函数只负责返回指定的文档, 至于上下文的切换任务则不在其职能范围之内-->最后考虑了一下, 还是决定在这里完成上下文切换
        上下文切换任务包含: 更换当前正在编辑的文档、将正在编辑的文档归档、将返回的文档设置为正在编辑文档
                            将返回的文档放入最近编辑文档队列(latest_doc和duration_left)
        '''
        # - 若该文档在本地有副本(缓存或者本地共享文档), 则直接读取并返回
        # - 若该文档在本地没有副本, 则直接调用gRPC: request_for_document, 之后: 
        #   - 若是本地共享文件意外丢失的情况, 则发出提示, 已根据副本恢复原文件
        #   - 否则不做任何提示

        # 这里的doc_info真的是document_info类型的信息(序列化)
        # 若为None, 说明是触发了前端的更新事件
        if doc_info_dict is None:
            with self.edit_mtx:
                if self.cur_edit_doc_cont is not None:
                    return [self.cur_edit_doc_cont, int(self.redisCli.hget("dup_doc_ver", self.cur_edit_doc))]
                return []

        doc_info = ParseDict(doc_info_dict, DisServ_pb2.document_info())
        doc_indicator = DisServ_pb2.unique_doc_indicator(doc_info = doc_info, ser_IP = self.ser_ip)
        doc_info_serial = doc_indicator.SerializeToString()
        
        # 特殊的情况: 请求的是当前文档, 这时, 直接读取内存内容即可(前端可以依据这个按照一定的时间间隔模拟点击事件即可)
        if doc_info_serial == self.cur_edit_doc:
            with self.edit_mtx:
                return [self.cur_edit_doc_cont, int(self.redisCli.hget("dup_doc_ver", self.cur_edit_doc))]

        # 若存在副本, 则获取该副本的路径, 获取锁读取后返回
        if self.redisCli.hexists("dup_doc_ver", doc_info_serial):
            if self.redisCli.hexists("sharing_doc", doc_info_serial):
                file_path = self.redisCli.hget("sharing_doc", doc_info_serial).decode()
            else:
                file_path = os.path.join(self.cache_path, '-'.join([str(doc_info.doc_ownerID),
                                                                    doc_info.doc_descriptor,
                                                                    doc_info.doc_name]))
            file_cont = []
            with self.share_mtx:
                with open(file_path, "r", encoding="utf-8") as file:
                    file_cont = [line.rstrip() for line in file]
            time_stamp = self.redisCli.hget("dup_doc_ver", doc_info_serial)
            res = [file_cont,int(time_stamp)]
        # 若不存在则调用RPC方法获取文档(注意要处理异常情况)
        else:
            stub = DisServ_pb2_grpc.DisServStub(self.channel)
            try:
                document = stub.request_for_document(doc_info)
            except grpc.RpcError:
                return []
            # 说明该文档已被撤回, 或者服务器意外丢失了副本
            if document.time_stamp == -1:
                return []
            else:
                file_path = os.path.join(self.cache_path, '-'.join([str(doc_info.doc_ownerID),
                                                                    doc_info.doc_descriptor,
                                                                    doc_info.doc_name]))
                with open(file_path, "w", encoding="utf-8") as file:
                    file.write('\n'.join(document.content))
                # 注册信息
                self.redisCli.hset("dup_doc_ver", doc_info_serial ,document.time_stamp)
                res = [document.content,document.time_stamp]

        # 开始上下文切换
        with self.edit_mtx:
            if self.cur_edit_doc is not None:

                if self.redisCli.hexists("sharing_doc", self.cur_edit_doc):
                    file_path = self.redisCli.hget("sharing_doc", self.cur_edit_doc).decode()
                else:                
                    cur_doc_indicator = DisServ_pb2.unique_doc_indicator()
                    cur_doc_indicator.ParseFromString(self.cur_edit_doc)
                    cur_info = cur_doc_indicator.doc_info
                    file_path = os.path.join(self.cache_path, '-'.join([str(cur_info.doc_ownerID),
                                                                        cur_info.doc_descriptor,
                                                                        cur_info.doc_name]))
                with open(file_path, "w", encoding="utf-8") as file:
                    file.write("\n".join(self.cur_edit_doc_cont))
                self.cur_edit_doc = doc_info_serial
                self.cur_edit_doc_cont = res[0]

            else:
                self.cur_edit_doc = doc_info_serial
                self.cur_edit_doc_cont = res[0]
            
            # 若该文档已在最近编辑列表里, 且正在更新, 就什么也不要动, 避免发生线程的冲突
            if self.cur_edit_doc in self.duration_left and self.duration_left[self.cur_edit_doc] == 0:
                pass
            else:
             # 请求文档在最近编辑列表里, 且剩余更新周期数非0, 那么就强制修改更新周期数, 使其更新;
             # 或者请求文档不在最近编辑列表里, 那么将其加入最近编辑列表, 并迫使其更新     
                self.latest_doc[self.cur_edit_doc] = 1
                self.duration_left[self.cur_edit_doc] = 1
           
        return res
    

    # 负责上传文档
    def upload_doc(self, file_path:str)->bool:
        if not os.path.exists(file_path):
            return False
        # 读取文件本体
        doc_file = []
        with open(file_path, "r", encoding="utf-8") as doc:
            doc_file = [line.rstrip() for line in doc]
        
        # 禁止上传空文本,这会使文件的标识失效, 同时也会使哈希运算失效
        if len(doc_file) == 0:
            return False   
             
        # 获取文件描述符
        # 创建一个哈希对象
        hash_func = hashlib.new("sha256")
        # 逐块读取文件并更新哈希对象
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_func.update(chunk)
        # 返回哈希值的十六进制表示
        descriptor = hash_func.hexdigest()  


        file_name = os.path.basename(file_path)
        # 创建document对象
        doc_info_ = DisServ_pb2.document_info(doc_name = file_name, 
                                              doc_descriptor = descriptor,
                                              doc_ownerID = self.usr_ID)
        doc = DisServ_pb2.document(doc_info = doc_info_,
                                    time_stamp = 0, 
                                   content = doc_file)

        # 注意这里的所有键都是unique_doc_indicator类型的
        doc_indicator = DisServ_pb2.unique_doc_indicator(ser_IP = self.ser_ip, doc_info = doc_info_)
        doc_indicator_serial = doc_indicator.SerializeToString()
        # 注册本地信息
        self.redisCli.hset("sharing_doc", doc_indicator_serial, file_path)
        self.redisCli.hset("dup_doc_ver", doc_indicator_serial, 0)

        # 开始准备调用gRPC服务, 将文件上传(首先需要登录并且创建channel)
        if self.channel is not None:
            stub = DisServ_pb2_grpc.DisServStub(self.channel)
            response = stub.upload_document(doc)
            if not response.accept_status:
                # 上传失败, 撤回已注册的信息
                self.redisCli.hdel("sharing_doc",doc_indicator_serial)
                self.redisCli.hdel("dup_doc_ver", doc_indicator_serial)
                return False
            else:
                # 将其纳入最近编辑文档队列中
                self.latest_doc[doc_indicator_serial] = 10
                self.duration_left[doc_indicator_serial] = 10
                return True

        return False
    
    def recall_doc(self, doc_info_dict:dict)->bool:
        doc_info = ParseDict(doc_info_dict, DisServ_pb2.document_info())
        try:
            stub = DisServ_pb2_grpc.DisServStub(self.channel)
            res = stub.recall_document(doc_info)
            if res.accept_status:# 成功后需要做上下文管理
                file_path = self.redisCli.hget("sharing_doc", self.cur_edit_doc)
                file_path = file_path.decode()
                with self.edit_mtx:
                    with(open(file_path, "w", encoding="utf-8")) as file:
                        file.write("\n".join(self.cur_edit_doc_cont))
                    self.redisCli.hdel("sharing_doc", self.cur_edit_doc)
                    self.redisCli.hdel("dup_doc_ver", self.cur_edit_doc)
                    del self.duration_left[self.cur_edit_doc]
                    del self.latest_doc[self.cur_edit_doc]
                    self.cur_edit_doc = None
                    self.cur_edit_doc_cont = None
            return res.accept_status
            
        except grpc.RpcError:
            return False
 
    def version_maintain(self)->None:
        '''
        - 该函数用来维护文档版本的一致, 会在一定的时隙过后向服务器请求patch
        - 如果判定某个文档更新频率过低, 就会将其踢出最近文档队列, 直到该文档再一次被打开
        - 要注意: 自己上传的共享文档永远不会被踢出队列, 但是其更新时隙可能会变得较大; 当前在编辑的文档也不会被踢出队列
        '''
        
        # *这是一个永远运行的线程, 其单循环的周期为0.05s, 这也是文档执行更新动作的最小周期(实际由于各种损耗, 要略大于0.05s)
        # *当检测到有某个在最近编辑文件列表里的文档等待期满, 就调用请求补丁线程, 并根据请求结果重新设定等待期

        while self.keepCatching:
            # 遍历所有最近编辑文档
            t0 = time.time()
            # 这里的doc_info_serial自然是序列化后的unique_doc_indicator类信息
            for doc_info_serial, left_periods in self.duration_left.items():
                
                if left_periods == 1:
                    # 若等待期结束, 则开始调用gRPC过程, 请求更新
                    self.duration_left[doc_info_serial] = 0 #设置为0, 避免在还没完成更新的时候, 再一次调用更新线程
                    update_thread = threading.Thread(target=self.single_request_patch_thread, args=(doc_info_serial,))
                    update_thread.start()

                else:
                    self.duration_left[doc_info_serial] -= 1
            delta_t = time.time() - t0
            if delta_t < self.basic_maintain_loop:
                time.sleep(self.basic_maintain_loop - delta_t)
        
        # 决定断开服务后, 冷却一下, 尽可能使所有派生出去的线程都运行完毕  
        time.sleep(0.4)

    def single_request_patch_thread(self, doc_info_serial:str)->None:
        '''
        - 请求补丁的线程, 对于文档doc_info_serial, 向服务器请求补丁, 以保持文档的一致性
        '''
        # 这里给到的doc_info_serial都是序列化之后的unique_doc_indicator
        stub = DisServ_pb2_grpc.DisServStub(self.channel)
        doc_indicator = DisServ_pb2.unique_doc_indicator()
        doc_indicator.ParseFromString(doc_info_serial)
        doc_info = doc_indicator.doc_info
        # 这里传的应该是patch
        time_stamp = self.redisCli.hget("dup_doc_ver", doc_info_serial)
        request_info = DisServ_pb2.patch(time_stamp = int(time_stamp), appli_doc=doc_info)
        patches_gen = stub.request_for_patch(request_info)
        patches = []
        for patch in patches_gen:
            patches.append(patch)

        # 说明最近一段时间没有什么更新, 直接把等待周期超级加倍(或者+5s)
        if len(patches) == 0:
            if self.latest_doc[doc_info_serial] >= self.max_periods:
                # 已经1分钟没有更新, 且既不在共享列表, 也不是当前编辑文档的文件, 将会被移除
                if self.latest_doc[doc_info_serial] >= self.max_periods*12 \
                    and not self.redisCli.hexists("sharing_doc",doc_info_serial)\
                        and self.cur_edit_doc != doc_info_serial:
                    
                    del self.latest_doc[doc_info_serial]
                    del self.duration_left[doc_info_serial]
                # 已经1分钟没有更新, 但在共享列表里或者是当前编辑文档
                else:
                    self.latest_doc[doc_info_serial] += self.max_periods
                    self.duration_left[doc_info_serial] = self.max_periods
            # 正常情况, 超级加倍
            else:
                self.latest_doc[doc_info_serial] = max(self.latest_doc[doc_info_serial]*2, self.max_periods)
                self.duration_left[doc_info_serial] = self.latest_doc[doc_info_serial]

            

        elif patches[0].time_stamp == -1:
            # 这种情况一般发生在共享文档之上, 或者掉线很久的当前编辑文档之上
            # 这说明当前版本落后太多辣, 直接调用request_for_document方法,
            # 获取更新的版本, 并完成善后工作, 替换掉老的版本, 完成某些数据的更新
            try:
                document = stub.request_for_document(doc_info)
                if self.cur_edit_doc == doc_info_serial:
                    with self.edit_mtx:
                        self.cur_edit_doc_cont = document.content
                        self.redisCli.hset("dup_doc_ver", doc_info_serial ,document.time_stamp)
                    
                else:
                    # 获取路径和锁之后, 对文档进行更新, 同时将时间戳进行更新
                    if self.redisCli.hexists("sharing_doc", doc_info_serial):
                        file_path = self.redisCli.hget("sharing_doc", doc_info_serial)
                    else:
                        file_name = '-'.join([str(doc_info.doc_ownerID),
                                            doc_info.doc_descriptor,
                                            doc_info.doc_name])
                        file_path = os.path.join(self.cache_path, file_name)
                    with self.share_mtx:
                        with open(file_path, "w", encoding="utf-8") as file :
                            file.write('\n'.join(document.content))
                        self.redisCli.hset("dup_doc_ver", doc_info_serial ,document.time_stamp)
                    pass
                self.latest_doc[doc_info_serial] = 1
                self.duration_left[doc_info_serial] = 1
            
            except grpc._channel._InactiveRpcError:
                pass

        else:
            # 开始应用补丁, 要分三种情况: 双非/当前正在编辑文档/在共享列表里的文档
            skip_reading = False
            if doc_info_serial == self.cur_edit_doc:
            # 若是当前正在编辑的文档, 则直接在申请到锁之后, 开始写入
                with self.edit_mtx:
                    # 申请完锁之后依然没被换下
                    # 仍需判断时间戳是否满足要求, 因为...
                    if doc_info_serial == self.cur_edit_doc:
                        for patch in patches:
                            self.cur_edit_doc_cont = apply_patch_cover(patch.items, self.cur_edit_doc_cont)
                            self.redisCli.hset("dup_doc_ver", doc_info_serial,patch.time_stamp)
                        skip_reading = True


            # 若是普通的共享文件或者临时文件(或者是刚被换下的文档), 则读取文档所在的路径, 申请到锁之后进行读写
            if not skip_reading:    
                if self.redisCli.hexists("sharing_doc", doc_info_serial):
                    file_path = self.redisCli.hget("sharing_doc", doc_info_serial)
                else:
                    file_name = '-'.join([str(doc_info.doc_ownerID),
                                        doc_info.doc_descriptor,
                                        doc_info.doc_name])
                    file_path = os.path.join(self.cache_path,file_name)                    
                file_cont = []
                with self.share_mtx:
                    with open(file_path, "r", encoding="utf-8") as file:
                        file_cont.append(line.rstrip() for line in file)
                    for patch in patches:
                        file_cont = apply_patch_cover(patch.items, file_cont)
                        self.redisCli.hset("dup_doc_ver", patch.time_stamp)
                    with open(file_path, "w", encoding="utf-8") as file:
                        file.write('\n'.join(file_cont))
            try:
                if self.latest_doc[doc_info_serial] < 10:
                    self.latest_doc[doc_info_serial] = 20
                    self.duration_left[doc_info_serial] = 20
                else:
                    self.latest_doc[doc_info_serial] /= 10
                    self.duration_left[doc_info_serial] = self.latest_doc[doc_info_serial]
            # 两个字典可能在主动退出登录的时候被清理
            except TypeError:
                pass

    
    def get_share_doc(self) -> list[list[list]]:
        '''
        从服务器获取所有文档信息, 同时将文档进行分组(依据归属者), 方便前端显示
        规定第一组为其他人的共享文档, 第二组为自己的共享文档
        {
        "my_share_docs":[...],
        "share_docs":[...]
        }
        '''
        try:
            stub = DisServ_pb2_grpc.DisServStub(self.channel)
            docs = stub.request_for_sharelist(DisServ_pb2.boolen_res(accept_status=True))
            # 这里将文档信息分好组, 再交付给前端
            res = {"my_share_docs":[],"share_docs":[]}
            # 我为什么不一步到位? 直接转成字典返还给调用者
            # 注意, 这里由于json无法解析字节流, 所以没必要传字节流了, 直接传一个字典过去就行
            # 然后在前端直接用文本格式存储, 回传后端的时候直接调用ParseDict转换为message即可

            
            for doc in docs.doc_info_list :
                item = {"doc_ownerID":doc.doc_ownerID,
                        "doc_name":doc.doc_name,
                        "doc_descriptor":doc.doc_descriptor}
                if doc.doc_ownerID == self.usr_ID:
                    res["my_share_docs"].append(item)
                else:
                    res["share_docs"].append(item)
            return res
        # 说明意外断联
        except grpc.RpcError:
            return None



    def logout(self)->None:
        '''
        - 关闭client的连接, 停止文件编辑, 将必要的数据进行归档, 收拾残局
        - 事实上并不是真正的退出登录, 严格来讲是没有用户系统的, 服务器不需要知道在线状态, 这里只是主动断开
          连接, 方便切换服务器, 或者安全地退出系统
        '''
        # 停止版本维护线程
        self.keepCatching = False
        # 
        # 将当前正在编辑的文档归档
        if self.cur_edit_doc is not None:
            # 如果是自己的共享文档, 则将当前的内容写入文件的真正地址
            # 如果是别人的共享文档, 则写入缓存地址
            if self.redisCli.hexists("sharing_doc", self.cur_edit_doc):
                file_path = self.redisCli.hget("sharing_doc", self.cur_edit_doc)
            else:
                doc_indicator = DisServ_pb2.unique_doc_indicator().ParseFromString(self.cur_edit_doc)
                doc_info = doc_indicator.doc_info
                file_path = os.path.join(self.cache_path, '-'.join(str(doc_info.doc_ownerID),
                                                                   doc_info.doc_descriptor,
                                                                   doc_info.doc_name))
            with self.edit_mtx:
                with open(file_path, "w", encoding="utf-8") as file:
                    file.write('\n'.join(self.cur_edit_doc_cont))
                self.cur_edit_doc = None
                self.cur_edit_doc_cont = None
        
        self.usr_name = None
        self.usr_ID = None
        self.ser_ip = None
        self.ser_port = None
        self.latest_doc = {}
        self.duration_left = {}
        
    def calc_upload_patch(self,old_cont:list[str], 
                          new_cont:list[str], 
                          time_stamp:int,
                          doc_indicator_serial
    )->bool:
        doc_indicator = DisServ_pb2.unique_doc_indicator()
        doc_indicator.ParseFromString(doc_indicator_serial)
        doc_info = doc_indicator.doc_info

        patch_items = get_patch(oldtxt=old_cont, newtxt=new_cont)
        if len(patch_items) == 0:
            return True
        usr_info = DisServ_pb2.usr_info(usr_name = self.usr_name, usr_ID=self.usr_ID)

        submit_patch = DisServ_pb2.patch(time_stamp = time_stamp,
                                         appli_usr = usr_info,
                                         appli_doc = doc_info,
                                         items = patch_items)
        # try:
        stub = DisServ_pb2_grpc.DisServStub(self.channel)
        res = stub.upload_patch(submit_patch)
        return res.accept_status
        # except grpc.RpcError:


        



    # 实际上下面这个函数没什么用, 该函数的功能被上面的access_document完美覆盖, 所以废弃掉原本的设计
    # def request_doc(self, doc_info_serial):

    #     pass


