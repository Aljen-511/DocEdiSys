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