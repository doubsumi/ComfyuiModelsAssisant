"""
图构建器
========
从 GraphPattern + GenerateRequest 实例化出具体的节点图。
输出：{ nodes: [...], links: [...], groups: [...], lastNodeId, lastLinkId }
"""
from __future__ import annotations

import random
import uuid
from copy import deepcopy
from typing import Any, Optional


class BuildError(Exception):
    pass


class GraphBuilder:
    def __init__(self):
        pass

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------
    def build(self, pattern: dict, request: dict) -> dict:
        # 1. 深拷贝节点定义，分配 node id
        node_id_map: dict[str, int] = {}
        working_nodes: list[dict] = []
        pool = pattern.get("nodeIdPool", {})
        base_id = int(pool.get("base", 1))
        lora_id = int(pool.get("lora", 1000))
        optional_id = int(pool.get("optional", 2000))

        # 先分配 base 节点 id
        next_base_id = base_id
        for spec in pattern.get("nodes", []):
            key = spec.get("key")
            if not key:
                continue
            is_optional = "optional" in spec
            if is_optional:
                continue  # 稍后处理
            node_id_map[key] = next_base_id
            next_base_id += 1

        # 2. 处理 optional 节点：根据 request.optionalInputs 决定是否激活
        optional_inputs = request.get("optionalInputs") or {}
        active_optional_keys: set[str] = set()
        for spec in pattern.get("nodes", []):
            if "optional" not in spec:
                continue
            opt_key = spec["optional"]
            if opt_key in optional_inputs:
                node_id_map[spec["key"]] = optional_id
                active_optional_keys.add(spec["key"])
                optional_id += 1

        # 3. 实例化基础节点
        for spec in pattern.get("nodes", []):
            key = spec.get("key")
            if not key:
                continue
            if "optional" in spec and key not in active_optional_keys:
                continue
            node = self._instantiate_node(spec, node_id_map[key])
            working_nodes.append(node)

        # 4. 处理 optional 节点填充：图片文件名
        for node in working_nodes:
            spec_key = self._find_key_by_id(node_id_map, node["id"])
            if spec_key in active_optional_keys:
                opt_key = self._find_optional_key(pattern, spec_key)
                if opt_key and opt_key in optional_inputs:
                    node["widgets_values"][0] = optional_inputs[opt_key]

        # 5. 注入模型文件名
        self._inject_models(working_nodes, pattern, request, node_id_map)

        # 6. 注入参数
        self._inject_params(working_nodes, pattern, request, node_id_map)

        # 7. 注入提示词
        self._inject_prompts(working_nodes, pattern, request, node_id_map)

        # 8. 处理 LoRA 插入：先建立基础连接，再处理 LoRA
        loras = request.get("loras") or []
        links = self._build_links_with_lora(
            working_nodes, pattern, node_id_map, loras, lora_id
        )

        # 9. 计算 last_node_id / last_link_id
        last_node_id = max((n["id"] for n in working_nodes), default=0)
        last_link_id = max((l[0] for l in links), default=0)

        return {
            "nodes": working_nodes,
            "links": links,
            "groups": pattern.get("groups", []),
            "lastNodeId": last_node_id,
            "lastLinkId": last_link_id,
        }

    # ------------------------------------------------------------
    # 节点实例化
    # ------------------------------------------------------------
    def _instantiate_node(self, spec: dict, node_id: int) -> dict:
        node = {
            "id": node_id,
            "type": spec["type"],
            "pos": list(spec.get("pos", [0, 0])),
            "size": list(spec.get("size", [200, 100])),
            "flags": dict(spec.get("flags", {})),
            "order": 0,
            "mode": spec.get("mode", 0),
            "inputs": [],
            "outputs": [],
            "properties": dict(spec.get("properties", {})),
            "widgets_values": list(spec.get("widgets_values", [])),
        }
        if "title" in spec:
            node["title"] = spec["title"]

        # inputs
        for i, inp in enumerate(spec.get("inputs", [])):
            input_def = {
                "name": inp["name"],
                "type": inp["type"],
                "link": None,
            }
            if "widget" in inp:
                input_def["widget"] = {"name": inp["widget"]["name"]}
            if "shape" in inp:
                input_def["shape"] = inp["shape"]
            node["inputs"].append(input_def)

        # outputs
        for out in spec.get("outputs", []):
            node["outputs"].append({
                "name": out["name"],
                "type": out["type"],
                "links": [],
            })
            if "shape" in out:
                node["outputs"][-1]["shape"] = out["shape"]

        return node

    # ------------------------------------------------------------
    # 模型注入
    # ------------------------------------------------------------
    def _inject_models(
        self,
        nodes: list[dict],
        pattern: dict,
        request: dict,
        node_id_map: dict[str, int],
    ) -> None:
        model_map = request.get("models") or {}
        for inj in pattern.get("modelInjections", []):
            key = inj["key"]
            role = inj["role"]
            widget_index = inj["widgetIndex"]
            file_name = model_map.get(role)
            if not file_name:
                continue
            node = self._find_node(nodes, node_id_map.get(key))
            if node is None:
                continue
            # 扩展 widgets_values 长度以容错
            while len(node["widgets_values"]) <= widget_index:
                node["widgets_values"].append(None)
            node["widgets_values"][widget_index] = file_name

    # ------------------------------------------------------------
    # 参数注入
    # ------------------------------------------------------------
    def _inject_params(
        self,
        nodes: list[dict],
        pattern: dict,
        request: dict,
        node_id_map: dict[str, int],
    ) -> None:
        params = request.get("params") or {}
        for inj in pattern.get("paramInjections", []):
            key = inj["key"]
            param_name = inj["param"]
            widget_index = inj["widgetIndex"]
            if param_name not in params:
                continue
            value = params[param_name]
            if param_name == "seed" and (value is None or value == -1):
                value = random.randint(0, 2**31 - 1)
            node = self._find_node(nodes, node_id_map.get(key))
            if node is None:
                continue
            while len(node["widgets_values"]) <= widget_index:
                node["widgets_values"].append(None)
            node["widgets_values"][widget_index] = value

    # ------------------------------------------------------------
    # 提示词注入
    # ------------------------------------------------------------
    def _inject_prompts(
        self,
        nodes: list[dict],
        pattern: dict,
        request: dict,
        node_id_map: dict[str, int],
    ) -> None:
        prompt_map = request.get("prompt") or {}
        for inj in pattern.get("promptInjections", []):
            key = inj["key"]
            role = inj["role"]
            widget_index = inj["widgetIndex"]
            text = prompt_map.get(role, "")
            node = self._find_node(nodes, node_id_map.get(key))
            if node is None:
                continue
            while len(node["widgets_values"]) <= widget_index:
                node["widgets_values"].append("")
            node["widgets_values"][widget_index] = text

    # ------------------------------------------------------------
    # 连接构建（含 LoRA 动态插入）
    # ------------------------------------------------------------
    def _build_links_with_lora(
        self,
        nodes: list[dict],
        pattern: dict,
        node_id_map: dict[str, int],
        loras: list[dict],
        lora_id_start: int,
    ) -> list[list]:
        links: list[list] = []
        next_link_id = 1

        def add_link(src_key: str, src_slot: int, dst_key: str, dst_slot: int, link_type: str) -> int:
            nonlocal next_link_id
            src_node_id = node_id_map.get(src_key)
            dst_node_id = node_id_map.get(dst_key)
            if src_node_id is None or dst_node_id is None:
                return -1
            link_id = next_link_id
            next_link_id += 1
            links.append([link_id, src_node_id, src_slot, dst_node_id, dst_slot, link_type])
            src_node = self._find_node(nodes, src_node_id)
            if src_node and src_slot < len(src_node["outputs"]):
                src_node["outputs"][src_slot]["links"].append(link_id)
            dst_node = self._find_node(nodes, dst_node_id)
            if dst_node and dst_slot < len(dst_node["inputs"]):
                dst_node["inputs"][dst_slot]["link"] = link_id
            return link_id

        active_keys = set(node_id_map.keys())

        # 1. 收集 LoRA 插入点
        lora_insert = pattern.get("loraInsertion")
        lora_from_key = lora_insert["fromKey"] if lora_insert else None
        lora_to_key = lora_insert["toKey"] if lora_insert else None
        lora_to_slot = lora_insert["toSlot"] if lora_insert else None

        # 2. 遍历所有 connections，跳过 loraInsertion 描述的那条（由 LoRA 逻辑处理）
        for conn in pattern.get("connections", []):
            from_key = conn["fromKey"]
            to_key = conn["toKey"]
            opt_tag = conn.get("optional")

            # optional 连接：对应节点未激活则跳过
            if opt_tag:
                opt_spec_key = self._find_optional_node_key(pattern, opt_tag)
                if opt_spec_key is None or opt_spec_key not in active_keys:
                    continue

            if from_key not in active_keys or to_key not in active_keys:
                continue

            # 如果这条连接正好是 loraInsertion 描述的，跳过（后面单独处理）
            if (lora_from_key and lora_to_key
                    and from_key == lora_from_key
                    and to_key == lora_to_key
                    and conn["toSlot"] == lora_to_slot):
                continue

            add_link(
                from_key, conn["fromSlot"],
                to_key, conn["toSlot"],
                conn["type"],
            )

        # 3. 处理 LoRA 插入点
        if not lora_insert:
            return links

        from_key = lora_insert["fromKey"]
        from_slot = lora_insert["fromSlot"]
        to_key = lora_insert["toKey"]
        to_slot = lora_insert["toSlot"]

        # 插入点两端必须都激活
        if from_key not in active_keys or to_key not in active_keys:
            return links

        # 从 from 节点的 output 推断 link type
        link_type = self._get_output_type(nodes, from_key, from_slot, node_id_map)

        # 无 LoRA：直接连 from → to
        if not loras:
            add_link(from_key, from_slot, to_key, to_slot, link_type)
            return links

        # 有 LoRA：链式插入
        node_pos = lora_insert.get("nodePos", [0, 0])
        node_size = lora_insert.get("nodeSize", [450, 170])

        prev_key = None
        for i, lora in enumerate(loras):
            lora_node_id = lora_id_start + i
            node_key = f"__lora_{i}__"
            node_id_map[node_key] = lora_node_id

            lora_node = {
                "id": lora_node_id,
                "type": "LoraLoaderModelOnly",
                "pos": [node_pos[0] + i * 50, node_pos[1] + i * 50],
                "size": list(node_size),
                "flags": {},
                "order": 0,
                "mode": 0,
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": None},
                    {"name": "lora_name", "type": "COMBO",
                     "widget": {"name": "lora_name"}, "link": None},
                    {"name": "strength_model", "type": "FLOAT",
                     "widget": {"name": "strength_model"}, "link": None},
                ],
                "outputs": [
                    {"name": "MODEL", "type": "MODEL", "links": []},
                ],
                "properties": {"Node name for S&R": "LoraLoaderModelOnly"},
                "widgets_values": [
                    lora["file"],
                    float(lora.get("weight", 1.0)),
                ],
            }
            nodes.append(lora_node)

            if prev_key is None:
                add_link(from_key, from_slot, node_key, 0, "MODEL")
            else:
                add_link(prev_key, 0, node_key, 0, "MODEL")
            prev_key = node_key

        # 最后一个 LoRA → 目标节点
        add_link(prev_key, 0, to_key, to_slot, "MODEL")

        return links

    def _get_output_type(
        self,
        nodes: list[dict],
        key: str,
        slot: int,
        node_id_map: dict[str, int],
    ) -> str:
        """从节点的 output 拿到 link 类型。找不到时默认 MODEL。"""
        node_id = node_id_map.get(key)
        node = self._find_node(nodes, node_id)
        if node and slot < len(node["outputs"]):
            return node["outputs"][slot].get("type", "MODEL")
        return "MODEL"

    # ------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------
    def _find_node(self, nodes: list[dict], node_id: Optional[int]) -> Optional[dict]:
        if node_id is None:
            return None
        for n in nodes:
            if n["id"] == node_id:
                return n
        return None

    def _find_key_by_id(self, node_id_map: dict[str, int], node_id: int) -> Optional[str]:
        for k, v in node_id_map.items():
            if v == node_id:
                return k
        return None

    def _find_optional_key(self, pattern: dict, spec_key: str) -> Optional[str]:
        for spec in pattern.get("nodes", []):
            if spec.get("key") == spec_key and "optional" in spec:
                return spec["optional"]
        return None

    def _find_optional_node_key(self, pattern: dict, opt_tag: str) -> Optional[str]:
        for spec in pattern.get("nodes", []):
            if spec.get("optional") == opt_tag:
                return spec.get("key")
        return None