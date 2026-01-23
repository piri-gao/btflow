from py_trees.behaviour import Behaviour
from py_trees.common import Status

from btflow.tools.base import Tool


class ToolNode(Behaviour):
    """
    Behaviour wrapper to allow Tool to be connected as a node in the tree.
    Used by Studio for visual connections and dynamic injection.
    """
    def __init__(self, name: str, tool: Tool):
        super().__init__(name)
        self.tool = tool

    def update(self) -> Status:
        return Status.SUCCESS
