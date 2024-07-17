# DocEdiSys
一个实现多人在线编辑的轻量级文档系统
A light document system that inplements multi-user edition online.



- 5.28:
> 开始任务，主要是实现框架规划


- 6.4:
> 完成两个文本对比的核心函数：
> - `get_patch`: 解析`diff`工具生成的对比格式，转为可应用的报文`patch`
> - `apply_patch_cover`:解析`patch`，将更改应用于旧版本文本

- 6.5:
> 开始规划基于grpc的程序框架

- 6.6:
> 基本完成前期规划以及设计任务, 准备开始实现
> 

- 6.15:
> 基本完成第一个版本, 但是有一些初期设想的功能还没实现
> 进入测试阶段
> 





-------------------------------------

```html
以下是系统的构建说明
```

####   无论在哪种环境下, 本项目都依赖于`Redis`数据库, 因此, 请先确定在本地安装了`Redis`数据库, 并确保其处于服务状态
####  此外为了保证不发生键值冲突, 最好为本系统安排一个隔离的`Redis`分区, 并在初次运行系统前, 使用`FLUSHALL`命令清空内存



#### 项目文件结构及参数和运行说明

1. 在下载完本项目之后, 文件结构如下
```html
DocEdiSys-O-|
			|--src---O-|
			|		   |--*app.py
			|		   |--*client.py
			|		   |--*server.py
			|		   |--*patch.py
			|          |--templates---O-|
			|		   |--static---O-|
			|          |--gRPC---O-|
			|          |           |--*__init__.py
			|          |           |--*atomScript.py
			|          |           |--*DisServ.proto
			|          |           |--*DisServ_pb2.py
			|          |           |--*DisServ_pb2_grpc.py
			|		   |        
			|		   |--cfg---O-|
			|		    		  |--*cliCfg.yaml
			|		    		  |--*serCfg.yaml
			|
			|
			|
			|--*requirements.txt
			|--*README.md
```

其中, 主要程序为`app.py`和`server.py`, `cfg`文件夹下的两个文件是管理配置的：

- `cliCfg.yaml`管理客户端的一些参数，这些参数以及含义如下：
> - `redis`:与Redis相关的配置
> 		- `host`: Redis服务器所在地址
> 		- `port`: Redis服务器所在端口
> 		- `db`: 客户端程序所使用的Redis服务器数据分区
> - `cache_path`: 当从客户拉取副本时, 副本文件的寄存路径
> - `server_ip`, `server_port`: 在客户端中已废弃选项
> - `basic_maintain_loop`: 维护文件一致性的循环线程周期, 默认为0.05秒
> - `max_update_period_nums`: 最近编辑列表中, 文件等待检查更新的最大周期数, 默认值为`100`, 即5秒


- `serCfg.yaml`管理服务器的一些配置参数，这些参数以及含义如下：
> - `redis`:与Redis相关的配置
> 		- `host`: Redis服务器所在地址
> 		- `port`: Redis服务器所在端口
> 		- `db`: 服务器程序所使用的Redis服务器数据分区
> - `share_path`: 用户上传共享文档副本的寄存路径
> - `num_patches`: 每个共享文档保留在内存中的`patch`列表长度上限，默认值为`20`
> - `listen_port`: 服务器启用`gRPC`服务时的监听端口
> - `threshold`: 最新补丁与文档版本的最大差值， 当最新补丁版本与文档版本差值超过这个值时, 才会对文档执行一次写回操作
> 


2. 在确保环境和依赖都无误后, 终端进入工作目录(`/src`)下，修改对应的配置，之后运行以下两个语句，可以分别启动服务器和客户端

```bash
python app.py
python server.py
```


3. 客户端在完成启动后， 浏览器输入`localhost:10001`即可访问编辑应用页面，并进行相关操作

4. 系统的使用说明详见**帮助文档**(通过点击应用页面左上角访问)


#### 环境配置说明

本项目所需依赖都在**requirement.txt**文件中，在项目根目录下使用命令：

```bash
pip install -r requirements.txt
```

可以很方便地导入所需的模块, 在此之前, **请确保使用的`python`解释器版本高于3.10.8**

但是，为了不污染环境，强烈推荐在**Windows**环境下为本项目创建一个虚拟环境，并确保在运行之前激活该虚拟环境(**Windows**下虚拟环境的建立参见**Anaconda**的相关文档, 此处不再赘述), 总之，在**Windows**环境下的配置是较为轻松的

而**Linux**发行版本众多，各个版本的python虚拟环境创建方式也略有差异，此处也不再过多说明(其中可能存在一些坑，比如在CentOS环境下利用pyenv创建高于3.10.8的环境时，需要额外安装并编译最新的openssl模块，但好在，这些都有相应的教程与解决方案)