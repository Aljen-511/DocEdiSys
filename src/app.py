from flask import Flask, render_template
from flask import request, make_response, jsonify, abort
import json
from patch import get_patch, apply_patch_cover
import threading
import os
from tkinter import filedialog
import sys


cur_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(cur_dir, "gRPC"))

from client import client
from gRPC import DisServ_pb2

app  = Flask(__name__)

Client_ = client()

@app.route("/")
def homePage():
    cur_dir_path = os.path.dirname(os.path.abspath(__file__))
    help_path = os.path.join(cur_dir_path, "templates/welcomePage.txt")
    with open (help_path,"r",encoding="utf-8") as file_:
        file = file_.read()
    return render_template("./index.html", file_content = file)

# 重定向到说明页面, 这里的说明页面是Markdown转换的html, 所以首次加载时间可能稍长
@app.route("/help")
def helpPage():
    return render_template("./README.html")

@app.route("/logout", methods= ["POST"])
def logout():
    if Client_.ser_ip is not None:
        Client_.logout()
    return make_response("ok")


@app.route("/uploadfile", methods=["POST"])
def upload_doc():
    file_path = filedialog.askopenfilename()
    if Client_.upload_doc(file_path):
        response = make_response("ok")
        return response
    else:
        abort(404)
    



@app.route("/login", methods = ["POST"])
def login():
    usr_name = request.form.get("username")
    ser_IP = request.form.get("serIP")
    ser_Port = request.form.get("serPort")
    if Client_.login(ser_IP, ser_Port, usr_name):
        response = make_response("ok")
        Client_.keepCatching = True
        maintainor = threading.Thread(target=Client_.version_maintain)
        maintainor.start()
        return response
    else:
        abort(404)
    


@app.route("/shareDoc", methods=["GET"])
def get_doc_lst():
    # 这里需要返回格式化的json
    docs = Client_.get_share_doc()

    if docs is not None:
        return jsonify(docs),200
    else:
        # 为空说明意外断联, 需要给点反馈
        abort(404)



@app.route("/editor", methods=['POST','GET'])
def obtain_doc():
    # 这里调用client的方法获取文件
    # 注意上下文的切换
    if request.method == 'POST':
        doc_info = request.get_json()['doc_info']
        doc_info_dict = json.loads(doc_info)
        res = Client_.access_document(doc_info_dict = doc_info_dict)
        if len(res) == 0:
            abort(404)
        else: 
            doc_content, time_stamp = res
            return jsonify(document = doc_content, doc_name = doc_info_dict["doc_name"], time_stamp = time_stamp), 200
    elif request.method == 'GET':
        # 调用access_document的get_update功能, 进行缓冲区的更新
        res =  Client_.access_document(doc_info_dict=None)
        if len(res) != 0:
            doc_content, time_stamp = res
            return jsonify(document = doc_content, time_stamp = time_stamp),200
        else:
            abort(404)

@app.route("/patch", methods=["POST"])
def upload_patch():
    with Client_.edit_mtx:
        doc_info = Client_.cur_edit_doc
        old_doc_cont = Client_.cur_edit_doc_cont
    doc_data = request.get_json()
    doc_cont_int = doc_data["content"] #字符串类型, 需要分开一下
    doc_cont = doc_cont_int.splitlines()
    doc_time_stamp = int(doc_data["time_stamp"]) #确保变为整形 
    old_ts = int(Client_.redisCli.hget("dup_doc_ver", doc_info))
    if old_ts != doc_time_stamp:
        abort(404)
    res = Client_.calc_upload_patch(old_cont=old_doc_cont,new_cont=doc_cont,
                              time_stamp=old_ts+1, doc_indicator_serial=doc_info)
    if res:
        return make_response("ok")
    else:
        abort(404)


    Client_.upload_patch(patch)

    pass
# 接下来定义每个接口要做的任务

# 1. 在js文件中, 实现ctrl+s上传补丁的操作
# 2. 这里实现上传文档之后

@app.route("/recall", methods=["POST"])
def recall():
    data = request.get_json()
    doc_info_dict = json.loads(data['doc_info'])
    if Client_.recall_doc(doc_info_dict):
        return make_response("ok")
    else:
        abort(404)


if __name__ == "__main__":
    
    app.run(host="127.0.0.1", port = 10001, debug=True)
    pass