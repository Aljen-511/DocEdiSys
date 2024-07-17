import difflib
from gRPC import DisServ_pb2


# delete的东西没必要传?有必要, 那可太有必要了, 因为可能存在回滚操作的需求
def get_patch(oldtxt:list[str], newtxt:list[str])->list[DisServ_pb2.single_patch_item]:
    '''
    #### INPUT 
    oldtxt: 更改前的文本行列表
    newtxt: 更改后的文本行列表
    要求二者不能同时为空
    #### OUTPUT
    alter_dict(patch): 以列表形式存储的更改信息(有序)
    '''
    diff_gen = difflib.unified_diff(oldtxt, newtxt)
    # 跳过前面两个entry
    try:
        for i in range(2):
            next(diff_gen)
    # 说明两个文本没有变化, 就返回一个空列表
    except StopIteration:
        return []


    alter_dict = []
    '''
    op: INSERT(0), DELETION(1) insert代表在原本的strt_line之前进行插入, deletion代表对strt_line进行删除
    strt_line: 操作的起始行号
    cont_line: 内容的行数
    cont: 修改的内容
    '''
    # 转移状态编号
    '''
    Norm:0
    Ins:1
    Del:2
    Push2Norm:3
    Ins2Del:4
    Del2Ins:5
    '''
    state_trans = [
        {' ':0, '+':1, '-':2},
        {' ':3, '+':1, '-':4},
        {' ':3, '+':5, '-':2},
    ]
    for item in diff_gen:
        # 第一项必然是变更的信息
        # 获取变更的范围
        #---以下模块没有问题
        substr_strt = 4
        txt_range = []
        for i in range(4, len(item)):
            if item[i] == ',':
                txt_range.append(int(item[substr_strt:i]))
                substr_strt = i + 1
            if item[i] == '+':
                txt_range.append(int(item[substr_strt:i]))
                substr_strt = i + 1
            if item[i] == '@':
                txt_range.append(int(item[substr_strt:i]))
                break
        #---

        # 开始按照行号信息，遍历接下来的项
        cur_old_line = txt_range[0]
        cur_new_line = txt_range[2]
        txt_range[1] += txt_range[0] - 1
        txt_range[3] += txt_range[2] - 1
        old_state = 0
        buffer = []

        for line_content in diff_gen:

            cur_state = state_trans[old_state][line_content[0]]
            if cur_state == 0:
                # 无事发生，更新行数即可
                cur_new_line += 1
                cur_old_line += 1
            elif cur_state == 1:
                # 只更新新文件行数
                buffer.append(line_content[1:])
                cur_new_line += 1
            elif cur_state == 2:
                # 相比旧文件的删除，只更新旧文件的行数 
                buffer.append(line_content[1:])
                cur_old_line += 1
            elif cur_state == 3:
                # ins或者del模式的push操作
                alter_item = DisServ_pb2.single_patch_item(cont_line = len(buffer),cont = buffer)
                if old_state == 1:
                    alter_item.op = 0
                    alter_item.start_line = cur_new_line - alter_item.cont_line
                    

                elif old_state == 2:
                    alter_item.op = 1
                    alter_item.start_line = cur_new_line
                    

                alter_dict.append(alter_item)
                cur_state = 0
                buffer = []
                cur_new_line += 1
                cur_old_line += 1

            elif cur_state == 4:
                alter_item = DisServ_pb2.single_patch_item(
                    op=0,
                    start_line = cur_new_line - len(buffer),
                    cont_line=len(buffer),
                    cont=buffer
                )
                buffer = []
                buffer.append(line_content[1:])
                alter_dict.append(alter_item)
                cur_state = 2
                # 操作与2一致
                cur_old_line += 1

            elif cur_state == 5:
                alter_item = DisServ_pb2.single_patch_item(
                    op=1,
                    start_line = cur_new_line,
                    cont_line = len(buffer),
                    cont = buffer
                )
                buffer = []
                buffer.append(line_content[1:])
                alter_dict.append(alter_item)
                cur_state = 1
                # 操作与1一致
                cur_new_line += 1
            
            if cur_old_line > txt_range[1] and cur_new_line > txt_range[3]:
                # 强制break，并且将更改都写入列表                           
                if len(buffer) != 0:
                    # 说明最后一个更改是插入
                    if cur_state == 1 or line_content[0] == '+':
                        alter_item = DisServ_pb2.single_patch_item(
                            op=0,
                            start_line = cur_new_line - len(buffer),
                            cont_line=len(buffer),
                            cont=buffer
                        )
                        alter_dict.append(alter_item)
                    # 说明最后一个更改是删除
                    elif cur_state == 2 or line_content[0] == '-':
                        alter_item = DisServ_pb2.single_patch_item(
                            op=1,
                            start_line = cur_new_line,
                            cont_line = len(buffer),
                            cont = buffer
                        )
                        alter_dict.append(alter_item)
                    buffer = []
                break
            old_state = cur_state

    return alter_dict


    
# 覆盖写方法
def apply_patch_cover(patch:list[DisServ_pb2.single_patch_item], file_str:list[str])->list[str]:
    '''
    #### Input
    patch: get_patch的返回值, single_patch_item的列表
    file_str: 待修改的文本
    #### Output
    字符串列表/None
    返回None时说明patch与原来的文件对不上
    
    >  
    这里需要注意: 输入的patch, 在开始行号上必须是递增的
    eg. ... --> insert 2 lines, starts from line 2 --> delete 3 lines, starts from line 9 --> ... √
        ... --> insert 1 lines, starts from line 7 --> delete 3 lines, starts from line 1 --> ... X
    '''

    # patched_file: 存放修改后的新文件的缓冲区
    patched_file = []
    # new_line_nums: 新文件正在等待操作的行号
    new_line_nums = 1
    # line_nums: 旧文件在等待操作的行号
    line_nums = 0

    for alter in patch:
        # 进行头部对齐操作
        if new_line_nums < alter.start_line:
            delta = alter.start_line - new_line_nums
            patched_file.extend(file_str[line_nums:line_nums+delta])
            line_nums += delta
            new_line_nums = alter.start_line
        
        # 执行插入操作
        if alter.op == 0:
            patched_file.extend(alter.cont)
            new_line_nums += alter.cont_line
        # 执行删除操作
        elif alter.op == 1:
            line_nums += alter.cont_line
            # 删除了超过原文件行数范围的内容，说明patch文件出错
            if line_nums > len(file_str):
                return None
    
    # 如果文件末尾没有任何改动, 则将旧文件剩余内容原封不动留给新文件
    if line_nums < len(file_str):
        patched_file.extend(file_str[line_nums:])

    return patched_file


def roll_back_from_patch(latest_patch:list[DisServ_pb2.single_patch_item], file_str:list[str]):
    '''
    #### Input
    latest_patch: 最近一次的补丁
    file_str: 最新版本的文档字符串列表
    #### Output
    old_file: 回滚后的上一个版本文档
    '''
    # 由于是从新版本回滚到旧版本, 需要从最后一个patch回溯, 所以需要从file_str的末尾开始,
    # 向开端处遍历
    latest_patch.reverse()
    for alter in latest_patch:
        start_line = alter.start_line - 1
        num_line = alter.cont_line
        # 执行插入的逆操作, 删除
        if alter.op == 0:
            del file_str[start_line:start_line+num_line]
        # 执行删除的逆操作, 插入
        elif alter.op == 1:
            # file_str[start_line:start_line+num_line] = alter['content'][:]
            alter.cont.reverse()
            for line in alter.cont:
                file_str.insert(start_line,line)
    
    return file_str.copy()





            
            
            
        