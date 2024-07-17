
function checkUpdata() {
    // 检查缓冲区是否有文档(通过时间戳)
    if (document.getElementById('time-stamp').innerText != '-1'){
        // 若有文件, 则向服务器发起更新请求
        fetch('/editor', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        }).then(response => {
            if (response.ok) {
                return response.json();
            }
            else {
                throw new Error('Err');
            }
            
        }).then(data => {
            // 获取最新版本后, 将其写入缓冲区
            // 缓冲区版本落后才需要改, 否则不需要更改, 同时降低计时器的频次
            const timestamp = document.getElementById('time-stamp');
            if (parseInt(timestamp.innerText) < parseInt(data.time_stamp)) {
                timestamp.innerText = data.time_stamp;            
                const content = data.document.join('\n');
                const editor = document.getElementById('editor');
                editor.value = content; 
                clearInterval(mainTainIntervalId);
                mainTainIntervalId = setInterval(checkUpdata, 1500);
            }
            else{
                clearInterval(mainTainIntervalId);
                mainTainIntervalId = setInterval(checkUpdata, 10000);

            }



        }).catch(error => {
            console.log('Error ',error);
        })

    }
}


// 设置一个定时器, 每1.5秒执行一次, 该定时器时刻检查需不需要更新缓冲区的文档
let mainTainIntervalId = setInterval(checkUpdata, 1500);


// 点击上传按钮之后, 发送请求到Flask服务器, 触发本地文件选择系统
// 在根据id获取元素之后, 监听该元素的点击行为
document.getElementById('upload-file-link').addEventListener('click', function() {
    const login_status = document.getElementById('login-status');
    if (login_status.innerText === '1') {
        fetch('/uploadfile', {
            method: 'POST',
        })
        .then(response => {
            if (response.ok) {
                // 如果需要，可以进行页面重定向
                // 呼出响应模态框, 更改必要的信息
                // 更改模态框通知内容
                const cont_ele = document.getElementById('inform-content');
                cont_ele.innerText = '文件上传成功！';

                // 显示模态框
                // 创建 Bootstrap 模态框实例
                const modalElement = document.getElementById('informModal');
                const modal = new bootstrap.Modal(modalElement);

                // 显示模态框
                modal.show();

                // 唤醒共享列表更新函数, 更新列表信息
                updateDocLst();

            } else {
                const cont_ele = document.getElementById('inform-content');
                cont_ele.innerText = '文件上传失败！';

                // 显示模态框
                // 创建 Bootstrap 模态框实例
                const modalElement = document.getElementById('informModal');
                const modal = new bootstrap.Modal(modalElement);

                // 显示模态框
                modal.show();
                
            }
        })
        .catch(error => {
            console.error('发生错误', error);
        });        
    }
    else {
        // 呼出提示响应框, 说明还没有登录

        // 更改模态框通知内容
        const cont_ele = document.getElementById('inform-content');
        cont_ele.innerText = '登录后才能上传文件';

        // 显示模态框
        // 创建 Bootstrap 模态框实例
        const modalElement = document.getElementById('informModal');
        const modal = new bootstrap.Modal(modalElement);

        // 显示模态框
        modal.show()
    }

});



// 监听登录按钮的点击行为, 将登录信息转发到Flask服务器, 最后发送到真正的服务器
document.getElementById('loginbtn').addEventListener('click', function() {
    var forminfo = document.getElementById('login-form');
    
    if (forminfo.checkValidity() === false){
        forminfo.reportValidity();
        return;
    }
    // 将按钮设置为不可用, 避免用户多次重复登录操作
    var loginbtn = document.getElementById('loginbtn');
    loginbtn.disabled = true;
    loginbtn.innerText = '登录中...';

    const formData = new FormData(forminfo);
    fetch('/login', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (response.ok) {
            // 关闭登录框后, 呼出登录成功的响应框
            document.getElementById('close-login-modal').click();

            const cont_ele = document.getElementById('inform-content');
            cont_ele.innerText = '登录成功!';
            const modalElement = document.getElementById('informModal');
            const modal = new bootstrap.Modal(modalElement);
            modal.show();

            // 初始化共享文档列表, 视角默认为他人共享
            const login_status = document.getElementById('login-status');
            login_status.innerText = '1';
            // 将上传修改按钮设置为可用
            document.getElementById('upload-patch-btn').disabled = false;

            // 将头像下拉菜单改为用户名和ID(点击行为变为注销)
            var user_name = forminfo.elements['username'].value;
            var loginswitch = document.getElementById('login-switch');
            loginswitch.innerText = user_name + '(已登录)';
            loginswitch.removeAttribute('data-bs-toggle');
            loginswitch.removeAttribute('data-bs-target');
            loginswitch.style.cursor = 'not-allowed';

            // 更新共享列表
            updateDocLst();
            
        } else {
            // 关闭登录窗口
            document.getElementById('close-login-modal').click();
            loginbtn.disabled = false;
            loginbtn.innerText = 'Login';
            // 呼出登录失败的响应框
            const cont_ele = document.getElementById('inform-content');
            cont_ele.innerText = '登录失败, 请确认服务器信息';

            // 显示模态框
            // 创建 Bootstrap 模态框实例
            const modalElement = document.getElementById('informModal');
            const modal = new bootstrap.Modal(modalElement);

            // 显示模态框
            modal.show()
        }
    })
    .catch(error => {
        document.getElementById('close-login-modal').click();
        console.error('发生错误', error);
    })
});

// 将当前文本框里的内容和文档的时间戳发送给后端, 让后端调用patch的rpc过程
document.getElementById('upload-patch-btn').addEventListener('click', function() {
    // 如果当前没有正在编辑的文档, 则忽略动作
    if (document.getElementById('time-stamp').innerText != '-1'){
        fetch('/patch',{
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: document.getElementById('editor').value,
                time_stamp: document.getElementById('time-stamp').innerText

            })
        }).then(response => {
            if (!response.ok){
                // 提示用户上传失败
                const cont_ele = document.getElementById('inform-content');
                cont_ele.innerText = '上传失败, 当前文档不是最新版本';
                const modalElement = document.getElementById('informModal');
                const modal = new bootstrap.Modal(modalElement);
                modal.show();
                // 说明版本过老, 那就立刻更新
                checkUpdata();
                throw new Error('Err');
                
            }
            else{
                // 提示用户上传成功
                const cont_ele = document.getElementById('inform-content');
                cont_ele.innerText = '上传成功, 等待服务器处理';
                const modalElement = document.getElementById('informModal');
                const modal = new bootstrap.Modal(modalElement);
                modal.show();
                checkUpdata();               
            }
            
        }).catch(error => {
            console.error('发生错误', error);
        })
    }
});


document.addEventListener('keydown', function(event) {
    if (event.ctrlKey && event.key === 's') {
        event.preventDefault(); // 阻止默认保存操作
        // 判断当前是否有文本正在编辑(时间戳不为-1), 有就模拟点击上传修改
        if (document.getElementById('time-stamp').innerText != '-1'){
            document.getElementById('upload-patch-btn').click();
        }
    }
});

function accessDoc(btn){
    const doc_info = btn.previousElementSibling;
    fetch('/editor',{
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },        
        body: JSON.stringify({
            doc_info: doc_info.innerText
        })
    }).then(response => {
        if (!response.ok){
            const cont_ele = document.getElementById('inform-content');
            cont_ele.innerText = '请求失败, 该文档可能已撤回';

            const modalElement = document.getElementById('informModal');
            const modal = new bootstrap.Modal(modalElement);
            modal.show()
            throw new Error('Err');
        }
        return response.json();
    })
    .then(data => {
            //TODO: 
            //成功获取文档, 将其放在编辑区
            //更改编辑区的标题
            //将时间戳作为隐藏元素放置在标题
            //修改按钮的属性, 使之不可用
            const content = data.document.join('\n');
            const editor = document.getElementById('editor');
            editor.value = content;
            editor.removeAttribute('readonly');
            const title = document.getElementById('title-line');
            title.innerText = data.doc_name;
            const timestamp = document.getElementById('time-stamp');
            timestamp.innerText = data.time_stamp;

            // 判断当前文档是否是自己上传的文档, 若是, 则令撤回按钮可用, 并将文档信息写入到隐藏元素中
            // 这里为了便利, 所有当前正在编辑的文档信息都需要写入隐藏元素
            if (btn.getAttribute('owner') === 'me'){
                document.getElementById('recall-btn').style.display = 'block';
                
            }
            else{
                document.getElementById('recall-btn').style.display = 'none';
                document.getElementById('cur-doc-info').innerText = doc_info.innerText;
            }

    }).catch(error => {
        console.error('发生错误', error);
    });


}

document.getElementById('recall-btn').addEventListener('click', function(){
    const doc_info = document.getElementById('cur-doc-info').innerText;
    fetch('/recall',{
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            doc_info: doc_info
        })
        }).then(response => {
            if (!response.ok){
                const cont_ele = document.getElementById('inform-content');
                cont_ele.innerText = '请求失败, 服务器可能繁忙';

                const modalElement = document.getElementById('informModal');
                const modal = new bootstrap.Modal(modalElement);
                modal.show()
                throw new Error('Err');
            }else{
                // 将撤回按钮继续隐藏
                document.getElementById('recall-btn').style.display = 'none';
                // 清空文本框, 将其设置为只读, 之后将时间戳和文档信息都清空
                document.getElementById('editor').value = '当前编辑区为空😶';
                document.getElementById('editor').setAttribute('readonly', 'true');
                document.getElementById('title-line').innerText = '#文档信息';
                document.getElementById('time-stamp').innerText = '-1';
                document.getElementById('cur-doc-info').innerText = '';

                // 弹出提示框
                const cont_ele = document.getElementById('inform-content');
                cont_ele.innerText = '撤回成功: 该文档已从共享列表移除';
                
                const modalElement = document.getElementById('informModal');
                const modal = new bootstrap.Modal(modalElement);
                modal.show();

                // 更新文档列表
                updateDocLst();



            }
        }).catch(error => {
            console.error('发生错误', error);
        })
})


function updateDocLst(){
    fetch('/shareDoc', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    }).then(response => {
        if (response.ok) {
            return response.json();
        }
        else{
            throw new Error('发生错误');
        }
        
    })
    .then(data => {
        const mylist = document.getElementById('my-share-list');
        const sharelist = document.getElementById('share-list');
        //先清空列表
        mylist.replaceChildren();
        sharelist.replaceChildren();
        // 遍历后端返回的文档信息, 逐个添加到列表中
        const mydocs = data.my_share_docs;
        mydocs.forEach(item => {
            var whole_container = document.createElement('div');
            whole_container.setAttribute('class', 'item-card card-body d-flex justify-content-between align-items-center p-1');
            
            var badge = document.createElement('div');
            badge.setAttribute('class', 'badge bg-warning rounded-pill');
            badge.innerText = 'ID: ' + String(item.doc_ownerID);
            whole_container.appendChild(badge);

            var name = document.createElement('div');
            name.setAttribute('class', 'doc-info');
            name.innerText = item.doc_name;
            whole_container.appendChild(name);

            var hidden_doc_info = document.createElement('label');
            hidden_doc_info.style.display = 'none';
            hidden_doc_info.innerText = JSON.stringify(item);;
            whole_container.appendChild(hidden_doc_info);


            
            var btn = document.createElement('button');
            btn.setAttribute('class', 'btn edit-button');
            btn.setAttribute('type', 'button');
            btn.setAttribute('owner','me');
            btn.innerText = '编辑';
            btn.onclick = function(event){
                accessDoc(event.target);
            }
            whole_container.appendChild(btn);
            mylist.appendChild(whole_container);


        });
        const sharedocs = data.share_docs;
        sharedocs.forEach(item => {
            var whole_container = document.createElement('div');
            whole_container.setAttribute('class', 'item-card card-body d-flex justify-content-between align-items-center p-1');
            
            var badge = document.createElement('div');
            badge.setAttribute('class', 'badge bg-warning rounded-pill');
            badge.innerText = 'ID: '+ String(item.doc_ownerID);
            whole_container.appendChild(badge);

            var name = document.createElement('div');
            name.setAttribute('class', 'doc-info');
            name.innerText = item.doc_name;
            whole_container.appendChild(name);

            var hidden_doc_info = document.createElement('label');
            hidden_doc_info.style.display = 'none';
            hidden_doc_info.innerText = JSON.stringify(item);;
            whole_container.appendChild(hidden_doc_info);


           
            var btn = document.createElement('button');
            btn.setAttribute('class', 'btn edit-button');
            btn.setAttribute('type', 'button');
            btn.setAttribute('owner','other');
            btn.innerText = '编辑';
            btn.onclick = function(event){
                accessDoc(event.target);
            }
            whole_container.appendChild(btn);
            sharelist.appendChild(whole_container);


        });


    });
}

document.getElementById('my-share-btn').addEventListener('click', function() {
    const login_status = document.getElementById('login-status');
    if (login_status.innerText === '1') {
        // 若已登录, 则允许切换视图操作, 否则不做任何响应
        const mylistEle = document.getElementById('my-share-list');
        const listEle = document.getElementById('share-list');
        // 将我的共享列表显示, 将多人共享列表隐藏
        listEle.style.display = 'none';
        mylistEle.style.display = 'block';
        
    }
});
document.getElementById('share-btn').addEventListener('click', function() {
    const login_status = document.getElementById('login-status');
    if (login_status.innerText === '1') {
        // 若已登录, 则允许切换视图操作, 否则不做任何响应
        const mylistEle = document.getElementById('my-share-list');
        const listEle = document.getElementById('share-list');
        // 将我的共享列表显示, 将多人共享列表隐藏
        mylistEle.style.display = 'none';
        listEle.style.display = 'block';
        
    }
});

document.getElementById('refresh-btn').addEventListener('click',updateDocLst);



window.addEventListener('beforeunload', function (event) {
    this.fetch('/logout', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
});









//因为浏览器无法直接获取文件路径, 因此直接放弃下面的方案

// 下面代码只能获得伪路径, 没办法, 只能绕开浏览器, 直接在后端的Flask框架中进行文件选择了
// copied from CSDN

//     //FX获取文件路径方法
//     function readFileFirefox(fileBrowser) {
//         try {
//             netscape.security.PrivilegeManager.enablePrivilege("UniversalXPConnect");
//         }
//         catch (e) {
//             alert('无法访问本地文件，由于浏览器安全设置。为了克服这一点，请按照下列步骤操作：(1)在地址栏输入"about:config";(2) 右键点击并选择 New->Boolean; (3) 输入"signed.applets.codebase_principal_support" （不含引号）作为一个新的首选项的名称;(4) 点击OK并试着重新加载文件');
//             return;
//         }
//         var fileName=fileBrowser.value; //这一步就能得到客户端完整路径。下面的是否判断的太复杂，还有下面得到ie的也很复杂。
//         var file = Components.classes["@mozilla.org/file/local;1"]
//             .createInstance(Components.interfaces.nsILocalFile);
//         try {
//             // Back slashes for windows
//             file.initWithPath( fileName.replace(/\//g, "\\\\") );
//         }
//         catch(e) {
//             if (e.result!=Components.results.NS_ERROR_FILE_UNRECOGNIZED_PATH) throw e;
//             alert("File '" + fileName + "' cannot be loaded: relative paths are not allowed. Please provide an absolute path to this file.");
//             return;
//         }
//         if ( file.exists() == false ) {
//             alert("File '" + fileName + "' not found.");
//             return;
//         }
 
 
//         return file.path;
//     }
 
 
//     //根据不同浏览器获取路径
//     function getval(obj){
// //判断浏览器
//         var Sys = {};
//         var ua = navigator.userAgent.toLowerCase();
//         var s;
//         (s = ua.match(/msie ([\d.]+)/)) ? Sys.ie = s[1] :
//             (s = ua.match(/firefox\/([\d.]+)/)) ? Sys.firefox = s[1] :
//                 (s = ua.match(/chrome\/([\d.]+)/)) ? Sys.chrome = s[1] :
//                     (s = ua.match(/opera.([\d.]+)/)) ? Sys.opera = s[1] :
//                         (s = ua.match(/version\/([\d.]+).*safari/)) ? Sys.safari = s[1] : 0;
//         var file_url="";
//         if(Sys.ie<="6.0"){
//             //ie5.5,ie6.0
//             file_url = obj.value;
//         }else if(Sys.ie>="7.0"){
//             //ie7,ie8
//             obj.select();
//             file_url = document.selection.createRange().text;
//         }else if(Sys.firefox){
//             //fx
//             //file_url = document.getElementById("file").files[0].getAsDataURL();//获取的路径为FF识别的加密字符串
//             file_url = readFileFirefox(obj);
//         }else if(Sys.chrome){
//             file_url = obj.value;
//         }
//         //alert(file_url);
//         // document.getElementById("text").innerHTML="获取文件域完整路径为："+file_url;
//         console.log("完整路径为: "+file_url)
//     }

