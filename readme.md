# Microsoft Remote Desktop Proxy（微软远程桌面代理）

一个简单的 RDP 代理工具，可将本地 Windows 电脑通过公网服务器暴露出来，实现远程桌面连接（无需公网 IP）。

--- 

## 使用方法

 1. 公网服务器上运行：

  python server.py --token 你的密钥 --tunnel-port 9999 --rdp-port 13389



 2. 本地 Windows 电脑上运行：

  python client.py --server 公网服务器IP --port 9999 --token 你的密钥



 3. 远程连接：

  打开 mstsc，连接地址填 公网服务器IP:13389，输入本地电脑的 Windows 用户名密码。



  注意事项：

- 本地电脑需要先开启远程桌面（系统设置 -> 远程桌面 -> 启用）

- 公网服务器防火墙需要放行 9999 和 13389 端口

- --token 两边要一致，随便设一个字符串就行

- 客户端断线会自动重连，20秒一次心跳保活






