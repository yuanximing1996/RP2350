# RP2350 六路继电器 MQTT 控制

本项目用于通过 MQTT 控制 Waveshare RP2350 Relay 6CH 继电器板。

设备启动后会连接 Wi-Fi 和 MQTT 服务器，订阅控制主题，接收继电器控制指令，并向状态主题上报继电器状态和在线心跳。

## 文件说明

- `main.py`：主程序，负责 Wi-Fi、MQTT、继电器控制和心跳上报。
- `config.py`：Wi-Fi 和 MQTT 连接配置。
- `lib/umqtt/`：MicroPython 使用的 MQTT 客户端库。

## 配置方式

上传到设备前，先复制 `config.example.py` 为 `config.py`，然后修改 `config.py`：

```python
wifi_ssid = '你的Wi-Fi名称'
wifi_password = '你的Wi-Fi密码'

mqtt_server = b'你的MQTT服务器地址'
mqtt_port = 1883
mqtt_client_id = b'RP2350yuanximing'
mqtt_keepalive = 60

mqtt_username = b'你的MQTT用户名'
mqtt_password = b'你的MQTT密码'
```

如果 MQTT 服务器不需要用户名和密码，可以设置为：

```python
mqtt_username = None
mqtt_password = None
```

## MQTT 主题

设备订阅的控制主题：

```text
rp2350/relay6ch/yuanximing/set
```

设备发布的状态主题：

```text
rp2350/relay6ch/yuanximing/state
```

## 控制指令

向下面这个主题发布 JSON 消息：

```text
rp2350/relay6ch/yuanximing/set
```

打开 1 路继电器：

```json
{"data":{"CH1":1}}
```

关闭 1 路继电器：

```json
{"data":{"CH1":0}}
```

打开 6 路继电器：

```json
{"data":{"CH6":1}}
```

关闭全部继电器：

```json
{"data":{"ALL":0}}
```

打开全部继电器：

```json
{"data":{"ALL":1}}
```

一次性下发多路：

```json
{"data":{"CH1":1,"CH2":0,"CH3":1}}
```

查询当前状态：

```json
{"cmd":"get_state"}
```

支持的通道：

- `CH1`
- `CH2`
- `CH3`
- `CH4`
- `CH5`
- `CH6`
- `ALL`

取值说明：

- `1`：打开
- `0`：关闭

## 状态上报

设备执行控制指令后，或执行查询指令后，会向状态主题发布状态：

```text
rp2350/relay6ch/yuanximing/state
```

示例：

```json
{"CH1":1,"CH2":0,"CH3":1,"CH4":0,"CH5":0,"CH6":0}
```

设备启动并成功连接 MQTT 后，会发布：

```json
{"status":"online"}
```

启动时还会发布一次全量状态：

```json
{"CH1":0,"CH2":0,"CH3":0,"CH4":0,"CH5":0,"CH6":0}
```

查询当前状态：

```json
{"CH1":1,"CH2":0,"CH3":1,"CH4":0,"CH5":0,"CH6":0}
```

错误返回示例（非法指令）：

```json
{"error":"invalid_json","CH1":0,"CH2":0,"CH3":0,"CH4":0,"CH5":0,"CH6":0}
```

如果设备连续 60 秒没有收到 MQTT 控制消息，也会再次发布在线心跳：

```json
{"status":"online"}
```

串口日志会显示：

```text
Online heartbeat: heartbeat
Published: {"status":"online"} -> rp2350/relay6ch/yuanximing/state
```

## 正常启动日志

正常运行时，串口日志类似：

```text
Relays initialized (OFF)
Connection successful!
IP address: 192.168.x.x
MQTT connection successful!
Subscribe to topic: rp2350/relay6ch/yuanximing/set
Online heartbeat: startup
Published: {"status":"online"} -> rp2350/relay6ch/yuanximing/state
```

收到控制指令后，日志类似：

```text
CH1 set to ON
Published: {"CH1":1} -> rp2350/relay6ch/yuanximing/state
```

## 常见问题

### `Error connecting to MQTT: 4 bad username or password`

表示 MQTT 服务器拒绝了当前用户名或密码。

请检查：

- `config.py` 里的 `mqtt_username`
- `config.py` 里的 `mqtt_password`
- MQTT 服务器中是否存在该用户
- 该用户是否有连接权限
- 该用户是否有订阅和发布当前主题的权限

### `Error: -1`

部分 MicroPython 固件在 MQTT 非阻塞读取时，如果当前没有新消息，可能会抛出 `OSError(-1)`。

当前 `main.py` 已经对这种情况做了处理，会忽略这个“暂无消息”的状态并继续运行。

### 连接成功，但时间一长发消息没反应

程序已经加入 MQTT ping 保活和自动重连逻辑。

如果 socket 连接异常，程序会自动：

- 断开旧连接
- 重新连接 MQTT
- 重新订阅控制主题
- 重新发布 online 状态

## 上传到设备

需要上传到 RP2350 板子的内容：

- `main.py`
- `config.py`，由 `config.example.py` 复制并填写真实配置
- `lib/umqtt/`

上传完成后，重启设备或运行 `main.py`。
