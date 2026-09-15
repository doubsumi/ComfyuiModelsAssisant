"""
工作流序列化
============
把 GraphBuilder 的输出转成 ComfyUI 认的 UI 格式 JSON。
"""
from __future__ import annotations

import uuid


INTERNAL_FIELDS = {
    "key", "optional",
    "_source", "_path", "_comment",
}


class WorkflowSerializer:
    def serialize(self, build_result: dict) -> dict:
        nodes = [self._strip_internal(n) for n in build_result["nodes"]]
        links = build_result["links"]
        groups = build_result.get("groups", [])

        # 重新排序 order 字段
        for i, n in enumerate(nodes):
            n["order"] = i

        return {
            "id": str(uuid.uuid4()),
            "revision": 0,
            "last_node_id": build_result["lastNodeId"],
            "last_link_id": build_result["lastLinkId"],
            "nodes": nodes,
            "links": links,
            "groups": groups,
            "config": {},
            "extra": {
                "ds": {"scale": 1.0, "offset": [0, 0]},
            },
            "version": 0.4,
        }

    def validate(self, workflow: dict) -> dict:
        """自检工作流的内部一致性。返回 { ok, errors: [], warnings: [] }。"""
        errors: list[str] = []
        warnings: list[str] = []

        nodes = workflow.get("nodes", [])
        links = workflow.get("links", [])

        node_ids = {n["id"] for n in nodes}
        link_ids = {l[0] for l in links}

        # 检查 link 的源和目标是否存在
        for link in links:
            link_id, src_id, src_slot, dst_id, dst_slot, link_type = link
            if src_id not in node_ids:
                errors.append(f"link {link_id}: 源节点 {src_id} 不存在")
            if dst_id not in node_ids:
                errors.append(f"link {link_id}: 目标节点 {dst_id} 不存在")

        # 检查每个 input.link 是否有对应的 link
        for node in nodes:
            for inp in node.get("inputs", []):
                link = inp.get("link")
                if link is not None and link not in link_ids:
                    errors.append(
                        f"节点 {node['id']} 的 input '{inp['name']}' 引用了不存在的 link {link}"
                    )

        # 检查每个 output.links 是否有对应的 link
        for node in nodes:
            for out in node.get("outputs", []):
                for link in out.get("links", []):
                    if link not in link_ids:
                        errors.append(
                            f"节点 {node['id']} 的 output '{out['name']}' 引用了不存在的 link {link}"
                        )

        # 检查 node id 唯一性
        if len(node_ids) != len(nodes):
            errors.append("节点 ID 有重复")

        # 检查 link id 唯一性
        if len(link_ids) != len(links):
            errors.append("link ID 有重复")

        return {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
        }

    # ------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------
    def _strip_internal(self, node: dict) -> dict:
        """移除内部字段，保留 ComfyUI 需要的结构。"""
        out = {}
        for k, v in node.items():
            if k in INTERNAL_FIELDS:
                continue
            if k == "inputs":
                out["inputs"] = [
                    {kk: vv for kk, vv in inp.items() if kk not in INTERNAL_FIELDS}
                    for inp in v
                ]
            elif k == "outputs":
                out["outputs"] = [
                    {kk: vv for kk, vv in output.items() if kk not in INTERNAL_FIELDS}
                    for output in v
                ]
            else:
                out[k] = v
        return out