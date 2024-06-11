import argparse
from flask import Flask, render_template, request
import json
import subprocess
import threading

app  = Flask(__name__)

@app.route("/")
def homePage():
    with open ("./README.md","r",encoding="utf-8") as file_:
        file = file_.read()
    return render_template("./index.html", file_content = file, user_status_operation = "登录")

# 接下来定义每个接口要做的任务




if __name__ == "__main__":
    app.run(host="127.0.0.1", port = 10001)
    pass