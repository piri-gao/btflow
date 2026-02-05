import sys
import os
from btflow import (
    Sequence, 
    Selector, 
    Log, 
    display
)

# 路径补丁
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def build_demo_tree():
    """构建一个稍微复杂点的树来展示可视化效果"""
    # 根节点：Sequence (带记忆)
    # 图标解释: [-] 代表 Sequence (顺序执行)
    root = Sequence(name="MainProcess", memory=True)
    
    # 1. 第一阶段
    node_a = Log(name="SayHello", message="Hello")
    
    # 2. 第二阶段：Selector (带记忆)
    # 图标解释: [?] 代表 Selector (选择执行/Fallback)
    decision_node = Selector(name="ReasoningLogic", memory=True)
    plan_a = Log(name="TryPlanA", message="Plan A")
    plan_b = Log(name="FallbackPlanB", message="Plan B")
    decision_node.add_children([plan_a, plan_b])
    
    # 3. 第三阶段
    node_c = Log(name="Summarize", message="Summary")
    
    # 组装
    root.add_children([node_a, decision_node, node_c])
    
    return root

if __name__ == "__main__":
    print("🎨 正在构建行为树...")
    root = build_demo_tree()
    
    print("\n=== 🌳 方式 1: ASCII 文本树 (终端直接看) ===")
    # 🚨 使用 ascii_tree，并且需要手动 print
    print(display.ascii_tree(root))
    
    print("\n=== 🖼️ 方式 2: 生成 PNG 图片 (需要 Graphviz) ===")
    try:
        # 这会在当前目录生成 bt_demo.png
        # 🚨 修复点：如果你没装 Graphviz 软件，这步会报错，但这不影响上面的 ASCII 树
        display.render_dot_tree(root, name="bt_demo", with_blackboard_variables=False)
        print("✅ 图片已生成: bt_demo.png (及 .dot source)")
    except Exception as e:
        print(f"⚠️ 无法生成图片 (可能是系统缺少 Graphviz): {e}")
        print("💡 但上面的 ASCII 树已经成功生成了！")
