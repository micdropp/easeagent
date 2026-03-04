"""Function Calling tool definitions for the EaseAgent cognitive layer.

Each tool is described as an OpenAI-compatible JSON Schema dict so that
both DashScope and Ollama can consume them via the ``tools`` parameter.
"""

from __future__ import annotations

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "control_light",
            "description": (
                "控制指定房间的灯光。可以开关灯、调节亮度和色温。"
                "色温范围: 2700K(暖光) ~ 6500K(冷白光)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "room_id": {
                        "type": "string",
                        "description": "房间ID，如 zone_a, meeting_1",
                    },
                    "device_id": {
                        "type": "string",
                        "description": "具体灯具ID。不填则控制房间内所有灯具",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["on", "off", "adjust"],
                        "description": "on=开灯, off=关灯, adjust=调节参数",
                    },
                    "brightness": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "亮度百分比(0~100)",
                    },
                    "color_temp": {
                        "type": "integer",
                        "minimum": 2700,
                        "maximum": 6500,
                        "description": "色温(K)，2700暖光~6500冷白光",
                    },
                },
                "required": ["room_id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_curtain",
            "description": (
                "控制指定房间的电动窗帘。可以开合窗帘或设置开合百分比。"
                "position 为 0 表示全关（遮光），100 表示全开。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "room_id": {
                        "type": "string",
                        "description": "房间ID，如 zone_a, meeting_1",
                    },
                    "device_id": {
                        "type": "string",
                        "description": "具体窗帘电机ID。不填则控制房间内所有窗帘",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["open", "close", "stop", "set_position"],
                        "description": (
                            "open=全开, close=全关, stop=停止, "
                            "set_position=设置到指定位置"
                        ),
                    },
                    "position": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "开合百分比(0=全关, 100=全开)，仅 set_position 时需要",
                    },
                },
                "required": ["room_id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_ac",
            "description": "控制指定房间的空调。可以开关空调、调节温度和模式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "room_id": {
                        "type": "string",
                        "description": "房间ID",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["on", "off", "adjust"],
                        "description": "on=开启, off=关闭, adjust=调节参数",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "目标温度(摄氏度)，通常16~30",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["cool", "heat", "auto", "fan"],
                        "description": "cool=制冷, heat=制热, auto=自动, fan=送风",
                    },
                },
                "required": ["room_id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_screen",
            "description": (
                "控制显示屏内容。可以显示迎宾画面、日程安排、公告、"
                "数据看板或自定义消息。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "screen_id": {
                        "type": "string",
                        "description": "屏幕设备ID",
                    },
                    "content_type": {
                        "type": "string",
                        "enum": [
                            "welcome",
                            "schedule",
                            "announcement",
                            "dashboard",
                            "custom",
                        ],
                        "description": (
                            "welcome=迎宾, schedule=日程, "
                            "announcement=公告, dashboard=看板, custom=自定义"
                        ),
                    },
                    "message": {
                        "type": "string",
                        "description": "自定义消息内容或附加文案",
                    },
                    "target_employee": {
                        "type": "string",
                        "description": "针对特定员工的个性化内容(员工ID)",
                    },
                },
                "required": ["screen_id", "content_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_fresh_air",
            "description": (
                "控制新风系统。根据CO2浓度、温湿度和室外条件调节新风档位。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["off", "low", "medium", "high", "max"],
                        "description": "新风档位",
                    },
                    "reason": {
                        "type": "string",
                        "description": "调节原因，用于日志记录和可追溯性",
                    },
                },
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee_preference",
            "description": (
                "查询员工的环境偏好设置。返回该员工在特定情境下的"
                "灯光、温度、色温等偏好。用于个性化调节设备。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "员工ID",
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "当前情境，如'独自办公'、'开会'、'午休'等"
                        ),
                    },
                },
                "required": ["employee_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notify_feishu",
            "description": "通过飞书发送通知给指定员工。",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "目标员工ID",
                    },
                    "message": {
                        "type": "string",
                        "description": "通知消息内容",
                    },
                    "msg_type": {
                        "type": "string",
                        "enum": ["text", "card", "toilet_status"],
                        "description": "消息类型",
                    },
                },
                "required": ["employee_id", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_preference_memory",
            "description": (
                "当观察到员工手动调整设备(说明Agent设置不合适)时，"
                "记录这个偏好行为到记忆系统，用于未来决策优化。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "员工ID",
                    },
                    "observation": {
                        "type": "string",
                        "description": "观察到的偏好行为描述，如'手动把灯调暗了'",
                    },
                    "context": {
                        "type": "string",
                        "description": "行为发生时的情境",
                    },
                },
                "required": ["employee_id", "observation"],
            },
        },
    },
]


def get_tool_names() -> list[str]:
    """Return the list of available tool names."""
    return [t["function"]["name"] for t in TOOL_DEFINITIONS]
