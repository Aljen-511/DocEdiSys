import difflib

# delete的东西没必要传?有必要, 那可太有必要了, 因为可能存在回滚操作的需求
def get_patch(oldtxt:list[str], newtxt:list[str])->list[dict]:
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
    for i in range(2):
        next(diff_gen)

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
                alter_item = {
                    'cont_line':len(buffer),
                    'content':buffer
                }
                if old_state == 1:
                    alter_item['op'] = 0
                    alter_item['start_line'] = cur_new_line - alter_item['cont_line']
                    

                elif old_state == 2:
                    alter_item['op'] = 1
                    alter_item['start_line'] = cur_new_line
                    

                alter_dict.append(alter_item)
                cur_state = 0
                buffer = []
                cur_new_line += 1
                cur_old_line += 1

            elif cur_state == 4:
                alter_item = {
                    'op':0,
                    'cont_line':len(buffer),
                    'content':buffer,
                    'start_line':cur_new_line - len(buffer)
                }
                buffer = []
                buffer.append(line_content[1:])
                alter_dict.append(alter_item)
                cur_state = 2
                # 操作与2一致
                cur_old_line += 1
            elif cur_state == 5:
                alter_item = {
                    'op':1,
                    'cont_line':len(buffer),
                    'content':buffer,
                    'start_line':cur_new_line
                }
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
                        alter_item = {
                            'op':0,
                            'cont_line':len(buffer),
                            'content':buffer,
                            'start_line':cur_new_line - len(buffer)
                        }
                        alter_dict.append(alter_item)
                    # 说明最后一个更改是删除
                    elif cur_state == 2 or line_content[0] == '-':
                        alter_item = {
                            'op':1,
                            'cont_line':len(buffer),
                            'content':buffer,
                            'start_line':cur_new_line
                        }
                        alter_dict.append(alter_item)
                    buffer = []
                break
            old_state = cur_state

    return alter_dict


    
# 覆盖写方法
def apply_patch_cover(patch:list[dict], file_str:list[str])->list[str]:
    '''
    #### Input
    patch: get_patch的返回值
    file_str: 待修改的文本
    #### Output
    字符串列表/None
    返回None时说明patch与原来的文件对不上
    '''
    '''
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
        if new_line_nums < alter['start_line']:
            delta = alter['start_line'] - new_line_nums
            patched_file.extend(file_str[line_nums:line_nums+delta])
            line_nums += delta
            new_line_nums = alter['start_line']
        
        # 执行插入操作
        if alter['op'] == 0:
            patched_file.extend(alter['content'])
            new_line_nums += alter['cont_line'] 
        # 执行删除操作
        elif alter['op'] == 1:
            line_nums += alter['cont_line']
            # 删除了超过原文件行数范围的内容，说明patch文件出错
            if line_nums > len(file_str):
                return None
    
    # 如果文件末尾没有任何改动, 则将旧文件剩余内容原封不动留给新文件
    if line_nums < len(file_str):
        patched_file.extend(file_str[line_nums:])

    return patched_file


def roll_back_from_patch(latest_patch:list[dict], file_str:list[str]):
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
        start_line = alter['start_line'] - 1
        num_line = alter['cont_line']
        # 执行插入的逆操作, 删除
        if alter['op'] == 0:
            del file_str[start_line:start_line+num_line]
        # 执行删除的逆操作, 插入
        elif alter['op'] == 1:
            # file_str[start_line:start_line+num_line] = alter['content'][:]
            alter['content'].reverse()
            for line in alter['content']:
                file_str.insert(start_line,line)
    
    return file_str.copy()




    pass

if __name__ == "__main__":
    t1="the test txt.\nsecond line.\nthirdline."
    t2="the test txt.\nsecond line.\nthirdline....\nchanged."
    t1 = '''Hello, this is an example.
This is the first line of text.
This is the second line of text.
newline
newline
newline
newline
newline
newline
newline
newline
newline
'''
    t2 = '''just a new begin.
Hello, this is a different example.
This is the first line of text.
another new insert.
This is the second line of text.
I just want to append a new line in after the initial fourth line.
newline
newline
newline
newline
newline
newline
newline
newline
newline
aaa
'''
    t1 = '''<!DOCTYPE html>
<html lang="zh-CN">
    <head>
        <meta charset="UTF-8" />
        <title> my llm Translator</title>
    </head>

    <link href="../static/main.css" rel="stylesheet">
    <link href="../static/bootstrap-3.3.7-dist/css/bootstrap.min.css" rel="stylesheet">
    <body>
        <div class="bg" align="left">
            
            <span class="bi bi-translate" style="margin-left: 10px;margin-right: 10px;">
                <img src="../static/translate.svg"  width="50px" height="50px" fill="currentColor">
            </span>
            <p style="font-size:50px;color:bone">Machine Translator</p>    
        </div>
        
        <div class="container">
            <div class="row">
                <div class="col-sm-6", style="height: 50px;"></div> 
                <!-- 占位容器 -->
            </div>
            <div class="row">
                <div class="col-sm-6">
                    <textarea class="form-control" style="font-size: 20px;" rows="12" id = "input" placeholder="文本输入框(目前只支持中翻英)"></textarea>
                </div>
                <div class="col-sm-6">
                    <textarea class="form-control" style="font-size: 20px;" rows="12" readonly id = "output" placeholder="结果输出框(目前只支持中翻英)"></textarea>
                </div>
            </div>
            <div class="row">
                <div class="col-sm-6", style="height: 25px;"></div><!-- 占位容器 -->
                <div class="col-md-12 text-center">
                    <button type="button" class="btn btn-default btn-lg btn-success " id = "gen_trans">生成翻译</button>
                </div>
            </div>

        
        </div>

        <script src="../static/jquery-2.2.1.min.js"></script>
        <script src="../static/main.js"></script>
        </body>

</html>

'''
    t2 = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文档在线编辑器</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="self_define.css">

</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary custom-navbar" style="height: 80px;">
        <div class="container-fluid">
            <a class="navbar-brand" href="#" style="font-weight: bold;font-size: 28px;">DocEdiSys</a>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav mx-auto" style="display: inline-block;padding: 8px;border-radius: 40px;background-color:  #FFFFFA;">
                    
                    <li class="nav-item">
                        <a class="nav-link" href="#" style="color: #007bff;font-weight: bold;padding-left: 10px;padding-right: 20px;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="currentColor" class="bi bi-cloud-arrow-up" viewBox="0 0 16 16" style="margin-right: 15px;margin-left: 15px;">
                                <path fill-rule="evenodd" d="M8 0a5.53 5.53 0 0 0-3.594 1.342c-.766.66-1.321 1.52-1.464 2.383C1.266 4.095 0 5.555 0 7.318 0 9.366 1.708 11 3.781 11H7.5V5.707L5.354 7.854a.5.5 0 1 1-.708-.708l3-3a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1-.708.708L8.5 5.707V11h4.188C14.502 11 16 9.57 16 7.773c0-1.636-1.242-2.969-2.834-3.194C12.923 1.999 10.69 0 8 0zm-.5 14.5V11h1v3.5a.5.5 0 0 1-1 0z"/>
                            </svg>
                            上传文件
                        </a>
                    </li>
                </ul>
                <div class="d-flex", style="margin-right: 20px;">
                    <div class="dropdown">
                        <a class="d-flex align-items-center text-white text-decoration-none" href="#" id="dropdownMenuButton" data-bs-toggle="dropdown" aria-expanded="false">
                            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" fill="currentColor" class="bi bi-person-circle" viewBox="0 0 16 16">
                                <path d="M8 0a8 8 0 1 0 8 8 8 8 0 0 0-8-8zm0 3a2.5 2.5 0 1 1-2.5 2.5A2.5 2.5 0 0 1 8 3zm0 9c1.5 0 4 0 4 1v1H4v-1c0-1 2.5-1 4-1z"/>
                            </svg>
                        </a>
                        <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userDropdown">
                            <li><a class="dropdown-item" href="#">{{user_status_operation}}</a></li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    </nav>
    <div class="container-fluid mt-5">
        <div class="row">
        <!-- 左侧列，占据3列（占据屏幕宽度的1/4） -->
        <div class="col-md-3 left-container">
          <!-- 上部容器 -->
          <div class="top-container mb-3">
            <textarea name="share_list" class="form-control" rows="8" style="resize: vertical;" placeholder="🥳文档共享列表"></textarea>
            <!-- 这里放置上部容器的内容 -->
          </div>
          <!-- 下部容器 -->
          <div class="bottom-container">
            <textarea name="alter_list" class="form-control" rows="10" style="resize: vertical;" placeholder="🥳日志列表"></textarea>
            <!-- 这里放置下部容器的内容 -->
          </div>
        </div>
        <!-- 右侧列，占据9列（占据屏幕宽度的3/4） -->
        <div class="col-md-9 right-container d-flex justify-content-center">
            <!-- 这里放置右侧大容器的内容 -->
            <form method="post">
                <div class="mb-3"> <!-- 这里是用来调整与下面的保存按钮的间距 -->
                  
                    <div class="titile-line">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-code-slash" viewBox="0 0 16 16" style="margin-right: 20px;">
                            <path d="M10.478 1.647a.5.5 0 1 0-.956-.294l-4 13a.5.5 0 0 0 .956.294l4-13zM4.854 4.146a.5.5 0 0 1 0 .708L1.707 8l3.147 3.146a.5.5 0 0 1-.708.708l-3.5-3.5a.5.5 0 0 1 0-.708l3.5-3.5a.5.5 0 0 1 .708 0zm6.292 0a.5.5 0 0 0 0 .708L14.293 8l-3.147 3.146a.5.5 0 0 0 .708.708l3.5-3.5a.5.5 0 0 0 0-.708l-3.5-3.5a.5.5 0 0 0-.708 0z"/>
                        </svg>  
                        #文档标题
                    </div>
                    <textarea name="file_content" class="form-control" rows="20" cols="120" style="resize: vertical;" placeholder="🥳文档编辑区" ></textarea>
                    
                </div>
                <button type="submit" class="btn btn-primary" style="margin-top: 10px;">保存</button>
            </form>
          

        </div>
      </div>
    </div>

    <!-- <div class="container mt-5">
        <form method="post">
            <div class="mb-3">
                <textarea name="file_content" class="form-control" rows="10">{{ file_content }}</textarea>
            </div>
            <button type="submit" class="btn btn-primary">保存</button>
        </form>
    </div> -->

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    
</body>
</html>
'''
    # res_gen = difflib.unified_diff(t1.splitlines(),t2.splitlines())
    # res_gen.__next__();res_gen.__next__
    # for item in res_gen:
    #     print(item)



    # res = get_patch(t1.splitlines(),t2.splitlines())

    # for item in res:
    #     print(f"{'Insert' if item['op'] == 0 else 'Delete'}: {item['cont_line']} lines, starts from line: {item['start_line']}")
    #     for cont in item['content']:
    #         print(cont)

    # res = get_patch(t1.splitlines(),t2.splitlines())
    # for item in res:
    #     print(f"{'Insert' if item['op'] == 0 else 'Delete'}: {item['cont_line']} lines, starts from line: {item['start_line']}")
    #     for cont in item['content']:
    #         print(cont)


    res = get_patch(t1.splitlines(), t2.splitlines())
    patched = apply_patch_cover(res, t1.splitlines())
    with open("test.txt", "w", encoding="utf-8") as file:
        file.write('\n'.join(patched))


    # res = get_patch(t1.splitlines(), t2.splitlines())
    # with open("test.txt","w",encoding="utf-8") as file:
    #     for item in res:
    #         file.write(f"{'Insert' if item['op'] == 0 else 'Delete'}: {item['cont_line']} lines, starts from line: {item['start_line']}\n")
    #         file.write("\n".join(item["content"])+"\n")
            
            
            
        